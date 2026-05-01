"""
生成集成模块
负责LLM调用、提示词模板、响应生成和流式输出
"""

import logging
from typing import AsyncGenerator, List

from langchain_openai import ChatOpenAI
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains.history_aware_retriever import create_history_aware_retriever
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from config import LLM_MODEL, LLM_BASE_URL, LLM_TEMPERATURE

logger = logging.getLogger(__name__)


def create_llm(api_key: str, streaming: bool = False) -> ChatOpenAI:
    """
    创建语言模型实例

    Args:
        api_key: API密钥
        streaming: 是否启用流式输出

    Returns:
        ChatOpenAI实例
    """
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=api_key,
        base_url=LLM_BASE_URL,
        temperature=LLM_TEMPERATURE,
        streaming=streaming
    )


def create_chitchat_chain(llm: ChatOpenAI, chat_history: List):
    """
    创建闲聊对话链

    Args:
        llm: 语言模型
        chat_history: 聊天历史

    Returns:
        生成器函数
    """
    async def chitchat_generator(query: str) -> AsyncGenerator[str, None]:
        sys_msg = SystemMessage(
            content="你是一个性格幽默、精通无线通信协议的 AI 专家。目前处于闲聊模式。请自然、简短地回应用户，可以适当玩梗。"
        )
        messages = [sys_msg] + chat_history + [HumanMessage(content=query)]

        async for chunk in llm.astream(messages):
            yield chunk.content

    return chitchat_generator


def create_qa_prompt() -> ChatPromptTemplate:
    """创建QA提示词模板"""
    return ChatPromptTemplate.from_messages([
        ("system", "你是深耕电子与 Wi-Fi 协议的资深工程师。请根据上下文资料回答问题，如果没有提及请如实回答不知。\n\n上下文资料：\n{context}"),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}")
    ])


def create_condense_prompt() -> ChatPromptTemplate:
    """创建历史浓缩提示词模板"""
    return ChatPromptTemplate.from_messages([
        ("system", "根据下方对话重写一个独立完整的问题。如果原问题已明确，原样返回。"),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}")
    ])


def create_rag_chain(llm: ChatOpenAI, retriever, chat_history: List):
    """
    创建RAG链（支持历史感知）

    Args:
        llm: 语言模型
        retriever: 检索器
        chat_history: 聊天历史

    Returns:
        RAG链
    """
    qa_prompt = create_qa_prompt()
    qa_chain = create_stuff_documents_chain(llm, qa_prompt)

    if not chat_history:
        rag_chain = create_retrieval_chain(retriever, qa_chain)
    else:
        condense_prompt = create_condense_prompt()
        history_aware_retriever = create_history_aware_retriever(llm, retriever, condense_prompt)
        rag_chain = create_retrieval_chain(history_aware_retriever, qa_chain)

    return rag_chain


async def generate_rag_response(
    rag_chain,
    query: str,
    chat_history: List
) -> AsyncGenerator[str, None]:
    """
    生成RAG响应（流式）

    Args:
        rag_chain: RAG链
        query: 用户查询
        chat_history: 聊天历史

    Returns:
        响应生成器
    """
    try:
        docs = []
        async for chunk in rag_chain.astream({"input": query, "chat_history": chat_history}):
            if "context" in chunk:
                docs = chunk["context"]
            if "answer" in chunk:
                yield chunk["answer"]

        # 添加溯源信息
        if docs:
            yield "\n\n---\n**📚 智库溯源 (Top 3):**\n"
            for i, doc in enumerate(docs[:3]):
                source_name = doc.metadata.get("source", "未知文档")
                snippet = doc.page_content.replace("\n", " ")[:80] + "..."
                yield f"**[{i + 1}]** 📄 `{source_name}`  \n> 🔍 _{snippet}_\n\n"

    except Exception as e:
        logger.error(f"RAG检索错误: {str(e)}")
        yield f"\n\n❌ 处理查询时出错: {str(e)}"


def convert_chat_messages(history: List) -> List:
    """
    转换聊天历史消息格式

    Args:
        history: 原始聊天历史列表

    Returns:
        转换后的消息列表
    """
    return [
        HumanMessage(content=m.content) if m.role == "user"
        else AIMessage(content=m.content)
        for m in history
    ]
