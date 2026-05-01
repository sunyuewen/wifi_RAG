"""
数据准备模块
负责文档上传、去重、解析、分块和存储到向量数据库
"""

import os
import hashlib
import time
import uuid
import logging
from typing import List, Dict

import pymupdf4llm
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownTextSplitter

from config import DB_PATH, CHUNK_SIZE, CHUNK_OVERLAP, BATCH_SIZE
from .index_construction import get_vectorstore, get_embeddings

# 任务状态字典，用于跟踪后台处理任务
TASK_STATUS: Dict[str, dict] = {}

logger = logging.getLogger(__name__)


def get_file_hash(file_path: str) -> str:
    """计算文件的MD5哈希"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def check_document_exists(file_hash: str) -> bool:
    """检查向量库中是否已存在相同哈希的文档"""
    try:
        vectorstore = get_vectorstore()
        results = vectorstore.get(where={"file_hash": {"$eq": file_hash}})
        return len(results['documents']) > 0
    except Exception as e:
        logger.error(f"检查文档存在性时出错: {e}")
        return False


def process_and_store_documents_bg(task_id: str, temp_files: List[str], original_names: List[str]):
    """
    后台处理文档：去重、解析、分块并存储到向量数据库

    Args:
        task_id: 任务ID
        temp_files: 临时文件路径列表
        original_names: 原始文件名列表
    """
    try:
        TASK_STATUS[task_id] = {"status": "🔍 正在检测文档去重...", "progress": 0, "total": 0}
        all_splits = []
        skipped_count = 0

        vectorstore = get_vectorstore()

        for temp_pdf, orig_name in zip(temp_files, original_names):
            file_hash = get_file_hash(temp_pdf)

            if check_document_exists(file_hash):
                TASK_STATUS[task_id]["status"] = f"⏭️ 跳过重复文件: {orig_name}"
                skipped_count += 1
                os.remove(temp_pdf)
                continue

            TASK_STATUS[task_id]["status"] = f"📖 正在解析: {orig_name}"
            md_text = pymupdf4llm.to_markdown(temp_pdf)

            docs = [Document(
                page_content=md_text,
                metadata={
                    "source": orig_name,
                    "file_hash": file_hash,
                    "upload_timestamp": str(int(time.time()))
                }
            )]
            text_splitter = MarkdownTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
            splits = text_splitter.split_documents(docs)
            all_splits.extend(splits)
            os.remove(temp_pdf)

        total_splits = len(all_splits)
        TASK_STATUS[task_id] = {
            "status": "✨ 疯狂向量化并分批入库中...",
            "progress": 0,
            "total": total_splits,
            "skipped": skipped_count
        }

        if total_splits > 0:
            for i in range(0, total_splits, BATCH_SIZE):
                batch = all_splits[i: i + BATCH_SIZE]
                vectorstore.add_documents(documents=batch)

                TASK_STATUS[task_id]["progress"] += len(batch)

        TASK_STATUS[task_id] = {
            "status": "completed",
            "progress": total_splits,
            "total": total_splits,
            "skipped": skipped_count,
            "message": f"✅ 新增 {total_splits} 个知识块，跳过 {skipped_count} 个重复文件"
        }

        # 清除全局 BM25 索引缓存和向量存储缓存
        from .index_construction import clear_bm25_cache, clear_vectorstore_cache
        clear_bm25_cache()
        clear_vectorstore_cache()

        # 使检索结果缓存失效
        from .retrieval_optimization import RETRIEVAL_CACHE
        RETRIEVAL_CACHE.invalidate()

    except Exception as e:
        TASK_STATUS[task_id] = {"status": "error", "error_msg": str(e)}
        logger.error(f"文档处理失败: {e}")
        for f in temp_files:
            if os.path.exists(f):
                os.remove(f)


def prepare_upload_files(files: List) -> tuple:
    """
    准备上传文件，保存为临时文件

    Args:
        files: 上传文件列表

    Returns:
        tuple: (temp_files列表, original_names列表)
    """
    temp_files = []
    original_names = []

    for file in files:
        temp_pdf = f"temp_{uuid.uuid4().hex}_{file.filename}"
        with open(temp_pdf, "wb") as f:
            f.write(file.read())
        temp_files.append(temp_pdf)
        original_names.append(file.filename)

    return temp_files, original_names


def get_task_status(task_id: str) -> dict:
    """获取任务状态"""
    return TASK_STATUS.get(task_id, {"status": "not_found"})


def clear_all_tasks():
    """清空所有任务状态"""
    TASK_STATUS.clear()