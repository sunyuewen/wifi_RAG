"""
配置管理模块
集中管理所有常量、环境变量和全局配置
"""

import os

# 数据库路径
DB_PATH = "./wifi_knowledge_db"

# HuggingFace 镜像端点
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 路由缓存大小限制
CACHE_SIZE_LIMIT = 1000

# 闲聊关键词集合
CHITCHAT_KEYWORDS = {
    "你好", "hello", "hi", "嘿", "hey",
    "谢谢", "谢了", "感谢", "thank", "thanks",
    "再见", "拜拜", "bye", "goodbye",
    "怎么样", "如何", "还好", "还可以",
    "多少钱", "价格", "费用", "成本",
    "你是谁", "介绍一下", "自我介绍",
    "天气", "时间", "日期", "几号",
    "笑话", "段子", "开玩笑", "有趣",
    "很棒", "很好", "真不错", "厉害", "牛逼"
}

# 技术关键词集合
TECH_KEYWORDS = {
    "wifi", "协议", "标准", "参数", "性能",
    "802.11", "频段", "带宽", "速率", "吞吐",
    "信号", "天线", "功率", "增益", "rssi",
    "指标", "规格", "配置", "优化", "改进",
    "对比", "区别", "支持", "兼容", "如何配置",
    "为什么", "什么是", "解释", "说明", "原理",
    "技术", "专业", "硬件", "软件", "算法"
}

# 嵌入模型名称
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# 重排序模型名称
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"

# LLM 配置
LLM_MODEL = "deepseek-chat"
LLM_BASE_URL = "https://api.deepseek.com"
LLM_TEMPERATURE = 0.1

# 分块配置
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

# 批处理大小
BATCH_SIZE = 200

# 检索配置
BM25_K = 5
VECTOR_K = 5
ENSEMBLE_WEIGHTS = [0.5, 0.5]
RERANKER_TOP_N = 3
DYNAMIC_TOP_N_QUERY_1 = 4
DYNAMIC_TOP_N_QUERY_OTHER = 3
MULTI_QUERY_MIN = 1
MULTI_QUERY_MAX = 5

# 限流配置
RATE_LIMIT = "30/minute"

# 检索缓存配置
RETRIEVAL_CACHE_MAXSIZE = 200
RETRIEVAL_CACHE_TTL_SECONDS = 600

# 评估配置
EVAL_DATASET_PATH = "eval_dataset.json"
JUDGE_MAX_ENTRIES = 20