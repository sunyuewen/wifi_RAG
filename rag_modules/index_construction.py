"""
索引构建模块
负责向量存储、BM25 索引的创建、缓存和管理
"""

import os
import logging
from typing import List, Optional

import jieba

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.retrievers.bm25 import BM25Retriever

from config import (
    DB_PATH, EMBEDDING_MODEL_NAME, RERANKER_MODEL_NAME,
    BM25_K, VECTOR_K, ENSEMBLE_WEIGHTS
)

logger = logging.getLogger(__name__)


def jieba_tokenizer(text: str) -> list:
    """结巴分词器，用于 BM25 中文分词"""
    return jieba.lcut(text)


# 全局缓存
_embeddings_cache: Optional[HuggingFaceEmbeddings] = None
_cross_encoder_cache: Optional[HuggingFaceCrossEncoder] = None
_compressor_cache: Optional[CrossEncoderReranker] = None
_bm25_cache: Optional[BM25Retriever] = None
_vectorstore_cache: Optional[Chroma] = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """获取嵌入模型（带缓存）"""
    global _embeddings_cache
    if _embeddings_cache is None:
        logger.info(f"加载嵌入模型: {EMBEDDING_MODEL_NAME}")
        _embeddings_cache = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
    return _embeddings_cache


def get_cross_encoder() -> HuggingFaceCrossEncoder:
    """获取交叉编码器（带缓存）"""
    global _cross_encoder_cache
    if _cross_encoder_cache is None:
        logger.info(f"加载重排序模型: {RERANKER_MODEL_NAME}")
        _cross_encoder_cache = HuggingFaceCrossEncoder(model_name=RERANKER_MODEL_NAME)
    return _cross_encoder_cache


def get_compressor() -> CrossEncoderReranker:
    """获取重排序压缩器（带缓存）"""
    global _compressor_cache
    if _compressor_cache is None:
        logger.info("创建重排序压缩器")
        _compressor_cache = CrossEncoderReranker(model=get_cross_encoder(), top_n=3)
    return _compressor_cache


def get_vectorstore() -> Chroma:
    """获取向量存储实例（带缓存）"""
    global _vectorstore_cache
    if _vectorstore_cache is None:
        logger.info("初始化 ChromaDB 向量存储实例")
        _vectorstore_cache = Chroma(
            persist_directory=DB_PATH,
            embedding_function=get_embeddings()
        )
    return _vectorstore_cache


def clear_vectorstore_cache():
    """清除向量存储缓存（当数据库更新时调用）"""
    global _vectorstore_cache
    _vectorstore_cache = None
    logger.info("向量存储缓存已清除")


def get_bm25_retriever() -> BM25Retriever:
    """获取 BM25 检索器（带缓存）"""
    global _bm25_cache
    if _bm25_cache is None:
        logger.info("构建 BM25 检索器")
        vectorstore = get_vectorstore()
        db_data = vectorstore.get()

        if not db_data['documents']:
            raise ValueError("数据库为空，无法构建 BM25 索引")

        _bm25_cache = BM25Retriever.from_texts(
            texts=db_data['documents'],
            metadatas=db_data['metadatas'],
            preprocess_func=jieba_tokenizer
        )
        _bm25_cache.k = BM25_K

    return _bm25_cache


def clear_bm25_cache():
    """清除 BM25 缓存（当数据库更新时调用）"""
    global _bm25_cache
    _bm25_cache = None
    logger.info("BM25 缓存已清除")


def clear_all_caches():
    """清除所有缓存"""
    global _embeddings_cache, _cross_encoder_cache, _compressor_cache, _bm25_cache, _vectorstore_cache
    _embeddings_cache = None
    _cross_encoder_cache = None
    _compressor_cache = None
    _bm25_cache = None
    _vectorstore_cache = None
    logger.info("所有模型缓存已清除")


def get_vector_retriever() -> Chroma:
    """获取向量检索器"""
    vectorstore = get_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": VECTOR_K})
    return retriever


def get_ensemble_retriever():
    """获取混合检索器（BM25 + 向量）"""
    from langchain_classic.retrievers.ensemble import EnsembleRetriever

    bm25_retriever = get_bm25_retriever()
    vector_retriever = get_vector_retriever()

    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=ENSEMBLE_WEIGHTS
    )

    return ensemble_retriever


def database_exists() -> bool:
    """检查数据库是否存在"""
    return os.path.exists(DB_PATH) and os.path.isdir(DB_PATH)


def get_document_count() -> int:
    """获取数据库中的文档数量"""
    try:
        vectorstore = get_vectorstore()
        db_data = vectorstore.get()
        return len(db_data['documents'])
    except Exception as e:
        logger.error(f"获取文档数量失败: {e}")
        return 0
