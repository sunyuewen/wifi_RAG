"""
RAG 核心模块包
包含数据准备、索引构建、检索优化、生成集成和评估模块
"""

from . import data_preparation
from . import index_construction
from . import retrieval_optimization
from . import generation_integration
from . import evaluation

__all__ = [
    "data_preparation",
    "index_construction",
    "retrieval_optimization",
    "generation_integration",
    "evaluation",
]