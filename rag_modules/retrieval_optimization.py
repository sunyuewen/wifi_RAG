"""
检索优化模块
负责路由判决、多查询检索、重排序和检索结果优化
"""

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_classic.retrievers import MultiQueryRetriever, ContextualCompressionRetriever
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from config import (
    CHITCHAT_KEYWORDS, TECH_KEYWORDS, CACHE_SIZE_LIMIT,
    MULTI_QUERY_MIN, MULTI_QUERY_MAX, DYNAMIC_TOP_N_QUERY_1,
    DYNAMIC_TOP_N_QUERY_OTHER
)
from .index_construction import get_ensemble_retriever, get_cross_encoder

logger = logging.getLogger(__name__)


# ── LRU 缓存 ──

class LRUCache:
    """LRU 缓存，超限时逐条淘汰最老条目，避免缓存雪崩"""

    def __init__(self, maxsize: int = 1000):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> Optional[int]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: int):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self):
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


ROUTER_CACHE = LRUCache(maxsize=CACHE_SIZE_LIMIT)


# ── 检索结果缓存 ──

class RetrievalResultCache:
    """检索结果缓存，LRU + TTL + DB generation 版本号"""

    def __init__(self, maxsize: int = 200, ttl_seconds: int = 300):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._db_generation = 0

    def _key(self, query: str, query_count: int) -> str:
        return hashlib.md5(f"{query}::{query_count}".encode()).hexdigest()

    def get(self, query: str, query_count: int) -> Optional[list]:
        k = self._key(query, query_count)
        if k in self._cache:
            docs, timestamp, generation = self._cache[k]
            if generation == self._db_generation and (time.time() - timestamp) < self._ttl:
                self._cache.move_to_end(k)
                return docs
            else:
                del self._cache[k]
        return None

    def put(self, query: str, query_count: int, docs: list):
        k = self._key(query, query_count)
        self._cache[k] = (docs, time.time(), self._db_generation)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate(self):
        """DB 更新时调用，递增 generation 使所有缓存条目失效"""
        self._db_generation += 1

    def clear(self):
        self._cache.clear()
        self._db_generation += 1

    def generation(self) -> int:
        return self._db_generation


RETRIEVAL_CACHE = RetrievalResultCache(maxsize=200, ttl_seconds=300)


# ── 带缓存的检索器包装 ──

class CachedEnsembleRetriever(BaseRetriever):
    """包装 ensemble retriever，增加检索结果缓存"""
    base_retriever: object
    query_count: int = 2

    def _get_relevant_documents(self, query: str) -> list:
        return self.base_retriever.invoke(query)

    async def _aget_relevant_documents(self, query: str) -> list:
        cached = RETRIEVAL_CACHE.get(query, self.query_count)
        if cached is not None:
            logger.info(f"检索缓存命中: {query[:30]}...")
            return cached

        docs = await self.base_retriever.ainvoke(query)
        RETRIEVAL_CACHE.put(query, self.query_count, docs)
        return docs


# ── 路由判决 ──

def quick_route_judgment(query: str) -> int:
    """
    本地快速路由判决，避免调用LLM

    Returns:
        0: 闲聊
        1: 技术查询
        -1: 无法确定，需要LLM判断
    """
    query_lower = query.lower()

    chitchat_score = sum(1 for kw in CHITCHAT_KEYWORDS if kw in query_lower)
    tech_score = sum(1 for kw in TECH_KEYWORDS if kw in query_lower)

    if chitchat_score >= 2 and tech_score == 0:
        return 0
    elif tech_score >= 2:
        return 1
    elif len(query) < 5:
        return 0

    return -1


async def llm_route_judgment(query: str, api_key: str) -> int:
    """
    使用LLM进行路由判决

    Returns:
        0: 闲聊
        1: 技术查询
    """
    router_prompt = ChatPromptTemplate.from_template(
        "你是一个极其聪明的流量分发中枢。请分析用户的最新输入：\n"
        "用户输入：{query}\n"
        "判断规则：\n"
        "1. 如果用户是在打招呼、闲聊、夸奖你、或者问纯通用常识（例如'你好'、'你是谁'、'今天天气'），请严格只回复数字：0\n"
        "2. 如果用户在询问具体的专业知识、技术细节、硬件参数、解释某概念，请严格只回复数字：1\n"
        "你的回复（仅限数字 0 或 1）："
    )
    router_llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=0.0
    )
    router_chain = router_prompt | router_llm

    route_decision = await router_chain.ainvoke({"query": query})
    route_result = 1 if "1" in route_decision.content.strip() else 0

    return route_result


async def get_route_result(query: str, api_key: str) -> Tuple[int, str]:
    """
    获取路由结果，优先使用缓存，其次本地判决，最后LLM判决

    Returns:
        (route_result, source): route_result 为 0=闲聊/1=技术，source 为 "cache"/"local_rule"/"llm"
    """
    route_result = ROUTER_CACHE.get(query)
    if route_result is not None:
        return route_result, "cache"

    route_result = quick_route_judgment(query)
    if route_result != -1:
        ROUTER_CACHE.put(query, route_result)
        return route_result, "local_rule"

    route_result = await llm_route_judgment(query, api_key)
    ROUTER_CACHE.put(query, route_result)
    return route_result, "llm"


# ── 检索器构建 ──

def create_multi_query_retriever(base_retriever, llm, query_count: int):
    """创建多查询检索器"""
    query_count = min(max(query_count, MULTI_QUERY_MIN), MULTI_QUERY_MAX)
    logger.info(f"MultiQuery 配置: {query_count} 个查询")

    mq_retriever = MultiQueryRetriever.from_llm(
        retriever=base_retriever,
        llm=llm,
        parser_key="lines",
    )

    return mq_retriever


def create_compression_retriever(base_retriever, query_count: int):
    """创建重排序压缩检索器（异步版）"""
    import asyncio
    from langchain_classic.retrievers.document_compressors import CrossEncoderReranker

    dynamic_top_n = DYNAMIC_TOP_N_QUERY_1 if query_count == 1 else DYNAMIC_TOP_N_QUERY_OTHER

    class AsyncCrossEncoderReranker(CrossEncoderReranker):
        """异步 CrossEncoder，将推理移到线程池避免阻塞事件循环"""

        async def acompress_documents(self, documents, query, callbacks=None):
            return await asyncio.to_thread(
                self.compress_documents, documents, query
            )

    compressor_dynamic = AsyncCrossEncoderReranker(
        model=get_cross_encoder(),
        top_n=dynamic_top_n
    )

    compression_retriever = ContextualCompressionRetriever(
        base_compressor=compressor_dynamic,
        base_retriever=base_retriever
    )

    return compression_retriever


def create_rag_retriever(llm, api_key: str, query_count: int = 2):
    """
    创建完整的RAG检索链

    当 query_count=1 时跳过 MultiQuery，直接走 ensemble + rerank
    """
    ensemble_retriever = get_ensemble_retriever()

    # 检索结果缓存层
    cached_retriever = CachedEnsembleRetriever(
        base_retriever=ensemble_retriever,
        query_count=query_count
    )

    # 仅在 query_count > 1 时启用 MultiQuery
    if query_count > 1:
        base_retriever = create_multi_query_retriever(cached_retriever, llm, query_count)
    else:
        base_retriever = cached_retriever

    # 重排序压缩检索器
    compression_retriever = create_compression_retriever(base_retriever, query_count)

    return compression_retriever


def clear_router_cache():
    """清空路由缓存"""
    ROUTER_CACHE.clear()
    logger.info("路由缓存已清空")
