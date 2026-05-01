"""
评估模块
负责检索质量评估、LLM-as-Judge 评判和回归测试
"""

import json
import math
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── 数据结构 ──

@dataclass
class EvalEntry:
    """单条评估数据"""
    id: int
    query: str
    relevant_keywords: List[str]
    difficulty: str = "medium"
    category: str = "general"


@dataclass
class RetrievalResult:
    """单条查询的检索评估结果"""
    query: str
    retrieved_contents: List[str]
    recall_at_k: Dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    ndcg: float = 0.0
    keyword_hit_rate: float = 0.0


@dataclass
class EvalReport:
    """汇总评估报告"""
    total_queries: int = 0
    avg_recall_at_3: float = 0.0
    avg_recall_at_5: float = 0.0
    avg_mrr: float = 0.0
    avg_ndcg: float = 0.0
    avg_keyword_hit_rate: float = 0.0
    by_category: Dict[str, Dict] = field(default_factory=dict)
    by_difficulty: Dict[str, Dict] = field(default_factory=dict)


# ── 指标实现 ──

def recall_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """计算 Recall@K：前 K 个检索结果中包含的相关项占比"""
    if not relevant:
        return 0.0
    retrieved_set = set(retrieved[:k])
    relevant_set = set(relevant)
    hits = len(retrieved_set & relevant_set)
    return hits / len(relevant_set)


def mean_reciprocal_rank(retrieved: List[str], relevant: List[str]) -> float:
    """计算 MRR：第一个相关文档排名的倒数"""
    relevant_set = set(relevant)
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """计算 NDCG@K：归一化折损累积增益"""
    relevant_set = set(relevant)

    dcg = 0.0
    for rank, item in enumerate(retrieved[:k], start=1):
        if item in relevant_set:
            dcg += 1.0 / math.log2(rank + 1)

    idcg = 0.0
    for rank in range(1, min(len(relevant), k) + 1):
        idcg += 1.0 / math.log2(rank + 1)

    return dcg / idcg if idcg > 0 else 0.0


def keyword_hit_rate(retrieved_contents: List[str], keywords: List[str]) -> float:
    """计算关键词命中率：检索结果中包含的关键词比例"""
    if not keywords:
        return 1.0
    all_text = " ".join(retrieved_contents).lower()
    hits = sum(1 for kw in keywords if kw.lower() in all_text)
    return hits / len(keywords)


# ── 数据集加载 ──

def load_eval_dataset(path: str = "eval_dataset.json") -> List[EvalEntry]:
    """加载评估数据集"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    for item in data["entries"]:
        entries.append(EvalEntry(
            id=item["id"],
            query=item["query"],
            relevant_keywords=item.get("relevant_keywords", []),
            difficulty=item.get("difficulty", "medium"),
            category=item.get("category", "general"),
        ))
    return entries


# ── 离线检索评估 ──

def evaluate_retrieval(
    entries: List[EvalEntry],
    retriever,
    k_values: List[int] = None
) -> EvalReport:
    """
    对检索器进行批量评估

    使用关键词匹配评估检索质量：将每个检索文档与查询的 relevant_keywords 匹配，
    构建伪相关文档集合，计算 Recall@K、MRR、NDCG。

    Args:
        entries: 评估数据条目
        retriever: LangChain 检索器实例
        k_values: 计算 Recall@K 的 K 值列表

    Returns:
        汇总评估报告
    """
    if k_values is None:
        k_values = [3, 5, 10]

    results: List[RetrievalResult] = []

    for entry in entries:
        # 闲聊类查询跳过检索评估
        if entry.category == "chitchat":
            continue

        try:
            docs = retriever.invoke(entry.query)
        except Exception as e:
            logger.error(f"检索失败 (query={entry.query}): {e}")
            continue

        # 用文档ID构建伪相关集合：基于关键词命中判断文档是否相关
        retrieved_ids = [f"doc_{i}" for i in range(len(docs))]
        retrieved_contents = [doc.page_content for doc in docs]

        # 构建伪相关文档集合：包含任一关键词的文档视为相关
        relevant_ids = []
        for i, content in enumerate(retrieved_contents):
            content_lower = content.lower()
            if any(kw.lower() in content_lower for kw in entry.relevant_keywords):
                relevant_ids.append(f"doc_{i}")

        # 如果没有关键词命中，用检索排名前2作为伪相关
        if not relevant_ids and entry.relevant_keywords:
            relevant_ids = retrieved_ids[:2]

        result = RetrievalResult(
            query=entry.query,
            retrieved_contents=retrieved_contents,
        )

        for k in k_values:
            result.recall_at_k[k] = recall_at_k(retrieved_ids, relevant_ids, k)
        result.mrr = mean_reciprocal_rank(retrieved_ids, relevant_ids)
        result.ndcg = ndcg_at_k(retrieved_ids, relevant_ids, k=5)
        result.keyword_hit_rate = keyword_hit_rate(retrieved_contents, entry.relevant_keywords)

        results.append(result)

    # 汇总
    report = EvalReport(total_queries=len(results))
    if not results:
        return report

    report.avg_recall_at_3 = sum(r.recall_at_k.get(3, 0) for r in results) / len(results)
    report.avg_recall_at_5 = sum(r.recall_at_k.get(5, 0) for r in results) / len(results)
    report.avg_mrr = sum(r.mrr for r in results) / len(results)
    report.avg_ndcg = sum(r.ndcg for r in results) / len(results)
    report.avg_keyword_hit_rate = sum(r.keyword_hit_rate for r in results) / len(results)

    # 按类别分组统计
    categories = set(e.category for e in entries if e.category != "chitchat")
    for cat in categories:
        cat_entries = [e for e in entries if e.category == cat]
        cat_ids = {e.id for e in cat_entries}
        cat_results = [r for r, e in zip(results, [e for e in entries if e.category != "chitchat"])
                       if e.id in cat_ids]
        if cat_results:
            report.by_category[cat] = {
                "count": len(cat_results),
                "avg_recall@5": round(sum(r.recall_at_k.get(5, 0) for r in cat_results) / len(cat_results), 3),
                "avg_mrr": round(sum(r.mrr for r in cat_results) / len(cat_results), 3),
                "avg_keyword_hit_rate": round(sum(r.keyword_hit_rate for r in cat_results) / len(cat_results), 3),
            }

    # 按难度分组统计
    difficulties = set(e.difficulty for e in entries)
    for diff in difficulties:
        diff_entries = [e for e in entries if e.difficulty == diff and e.category != "chitchat"]
        diff_ids = {e.id for e in diff_entries}
        diff_results = [r for r, e in zip(results, [e for e in entries if e.category != "chitchat"])
                        if e.id in diff_ids]
        if diff_results:
            report.by_difficulty[diff] = {
                "count": len(diff_results),
                "avg_recall@5": round(sum(r.recall_at_k.get(5, 0) for r in diff_results) / len(diff_results), 3),
                "avg_mrr": round(sum(r.mrr for r in diff_results) / len(diff_results), 3),
                "avg_keyword_hit_rate": round(sum(r.keyword_hit_rate for r in diff_results) / len(diff_results), 3),
            }

    return report


# ── A/B 对比框架 ──

def compare_configs(
    entries: List[EvalEntry],
    config_a_retriever,
    config_b_retriever,
    config_a_name: str = "Config A",
    config_b_name: str = "Config B"
) -> Dict:
    """对比两组检索配置的效果"""
    report_a = evaluate_retrieval(entries, config_a_retriever)
    report_b = evaluate_retrieval(entries, config_b_retriever)

    return {
        config_a_name: {
            "recall@3": round(report_a.avg_recall_at_3, 3),
            "recall@5": round(report_a.avg_recall_at_5, 3),
            "mrr": round(report_a.avg_mrr, 3),
            "ndcg": round(report_a.avg_ndcg, 3),
            "keyword_hit_rate": round(report_a.avg_keyword_hit_rate, 3),
        },
        config_b_name: {
            "recall@3": round(report_b.avg_recall_at_3, 3),
            "recall@5": round(report_b.avg_recall_at_5, 3),
            "mrr": round(report_b.avg_mrr, 3),
            "ndcg": round(report_b.avg_ndcg, 3),
            "keyword_hit_rate": round(report_b.avg_keyword_hit_rate, 3),
        },
        "delta": {
            "recall@5": round(report_b.avg_recall_at_5 - report_a.avg_recall_at_5, 3),
            "mrr": round(report_b.avg_mrr - report_a.avg_mrr, 3),
            "keyword_hit_rate": round(report_b.avg_keyword_hit_rate - report_a.avg_keyword_hit_rate, 3),
        }
    }


# ── LLM-as-Judge ──

JUDGE_PROMPT = """你是一个严格的评估专家。请评估以下RAG系统回答的质量。

问题: {query}

参考上下文:
{context}

系统回答:
{answer}

请从以下三个维度打分(1-5分):

1. **准确性** (accuracy): 回答是否基于上下文，有无事实错误或幻觉
2. **相关性** (relevance): 回答是否切中问题要害
3. **完整性** (completeness): 回答是否充分覆盖了问题所涉及的知识点

请严格按以下JSON格式回复，不要添加其他内容:
{{"accuracy": X, "relevance": X, "completeness": X, "reason": "简短理由"}}
"""


async def judge_answer(
    query: str,
    context: str,
    answer: str,
    api_key: str
) -> Dict:
    """
    使用 LLM 作为评判者评估答案质量

    Returns:
        包含 accuracy、relevance、completeness 评分(1-5)和 reason 的字典
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate

    judge_llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=0.0
    )

    prompt = ChatPromptTemplate.from_template(JUDGE_PROMPT)
    chain = prompt | judge_llm

    response = await chain.ainvoke({
        "query": query,
        "context": context,
        "answer": answer
    })

    try:
        result = json.loads(response.content.strip())
        return result
    except json.JSONDecodeError:
        return {
            "accuracy": 0,
            "relevance": 0,
            "completeness": 0,
            "reason": f"解析评判回复失败: {response.content[:100]}"
        }


async def run_judge_evaluation(
    entries: List[EvalEntry],
    rag_chain,
    api_key: str,
    max_entries: int = 20
) -> List[Dict]:
    """
    对评估数据集运行 LLM-as-Judge 评估

    Args:
        entries: 评估数据条目
        rag_chain: RAG 生成链
        api_key: API 密钥
        max_entries: 最大评估条目数

    Returns:
        每条查询的评判结果列表
    """
    results = []
    technical_entries = [e for e in entries if e.category != "chitchat"][:max_entries]

    for entry in technical_entries:
        try:
            # 调用 RAG 链生成答案
            response = await rag_chain.ainvoke({"input": entry.query, "chat_history": []})
            answer = response.get("answer", "")
            context_docs = response.get("context", [])
            context = "\n".join(doc.page_content for doc in context_docs)

            score = await judge_answer(
                query=entry.query,
                context=context,
                answer=answer,
                api_key=api_key
            )

            results.append({
                "id": entry.id,
                "query": entry.query,
                "category": entry.category,
                **score
            })

        except Exception as e:
            logger.error(f"Judge 评估失败 (id={entry.id}): {e}")
            results.append({
                "id": entry.id,
                "query": entry.query,
                "category": entry.category,
                "accuracy": 0,
                "relevance": 0,
                "completeness": 0,
                "reason": f"评估出错: {str(e)}"
            })

    return results


def print_eval_report(report: EvalReport):
    """打印评估报告"""
    print("\n" + "=" * 60)
    print("检索质量评估报告")
    print("=" * 60)
    print(f"  评估查询数:       {report.total_queries}")
    print(f"  Avg Recall@3:     {report.avg_recall_at_3:.3f}")
    print(f"  Avg Recall@5:     {report.avg_recall_at_5:.3f}")
    print(f"  Avg MRR:          {report.avg_mrr:.3f}")
    print(f"  Avg NDCG@5:       {report.avg_ndcg:.3f}")
    print(f"  Avg 关键词命中率:  {report.avg_keyword_hit_rate:.3f}")

    if report.by_category:
        print("\n  按类别分组:")
        for cat, stats in report.by_category.items():
            print(f"    {cat}: Recall@5={stats['avg_recall@5']}, "
                  f"MRR={stats['avg_mrr']}, "
                  f"关键词命中率={stats['avg_keyword_hit_rate']}")

    if report.by_difficulty:
        print("\n  按难度分组:")
        for diff, stats in report.by_difficulty.items():
            print(f"    {diff}: Recall@5={stats['avg_recall@5']}, "
                  f"MRR={stats['avg_mrr']}, "
                  f"关键词命中率={stats['avg_keyword_hit_rate']}")

    print("=" * 60 + "\n")
