"""
Wi-Fi 7 专家 API (异步批处理版) - 主程序入口
基于 FastAPI 的 RAG 系统，支持文档上传和智能问答

=== FastAPI 基础概念 ===

FastAPI 是一个 Python Web 框架，核心概念：
1. "路由"：用 @app.get / @app.post 等装饰器把一个函数绑定到一个 URL 路径
   - @app.get("/health")  → 浏览器访问 GET http://localhost:8000/health 就会调用下面这个函数
   - @app.post("/chat/stream") → 前端发 POST 请求到 http://localhost:8000/chat/stream 就会调用下面这个函数
   - @app.delete("/clear_db") → 前端发 DELETE 请求到这个路径
   GET/POST/DELETE 是 HTTP 请求方法：GET=获取数据, POST=提交数据, DELETE=删除数据

2. "异步"：async def 表示这是异步函数，遇到 I/O 等待（如网络请求）时不会阻塞，可以同时处理其他请求

3. "启动顺序"：
   第①步：Python 加载这个文件，执行所有顶层代码（导入、创建 app 对象、注册路由）
   第②步：uvicorn 启动服务器，触发 @app.on_event("startup") 回调
   第③步：服务器开始监听端口，等待 HTTP 请求到来
   第④步：请求到达时，FastAPI 根据路径和方法找到对应的路由函数并调用
"""

import os
import sys
import time
import logging
import shutil
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import config
import performance_monitor
from rag_modules import data_preparation, index_construction, retrieval_optimization, generation_integration

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第①步：全局初始化（文件加载时立即执行）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 配置日志格式，输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format="🌟 [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# 请求限流器：限制每个IP地址的请求频率，防止滥用
# key_func=get_remote_address 表示用客户端IP作为限流的key
limiter = Limiter(key_func=get_remote_address)

# 创建 FastAPI 应用实例
# 这是整个Web服务的核心对象，所有路由都注册在这个 app 上
app = FastAPI(title="Wi-Fi 7 专家 API (模块化版)", version="4.3")
app.state.limiter = limiter  # 把限流器挂到app上，slowapi需要这样做


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第②步：服务器启动时的回调
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# @app.on_event("startup") 表示：服务器启动完成后自动执行这个函数
# 作用：提前加载AI模型，避免第一个用户请求时才加载（那样会很慢）
@app.on_event("startup")
async def preload_models():
    """启动时预加载模型，避免首次请求冷启动延迟"""
    logger.info("预加载模型...")
    if index_construction.database_exists():
        try:
            index_construction.get_embeddings()    # 加载嵌入模型（~3-5秒）
            index_construction.get_vectorstore()   # 初始化ChromaDB连接
            logger.info("模型预加载完成")
        except Exception as e:
            logger.warning(f"模型预加载跳过（数据库可能为空）: {e}")
    else:
        logger.info("未找到数据库，跳过模型预加载")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第①步续：数据模型定义（请求体的数据结构）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Pydantic BaseModel 用来定义API接收/返回的数据格式
# FastAPI 会自动做数据验证：如果前端传的数据不符合格式，直接返回422错误

class ChatMessage(BaseModel):
    """单条聊天消息的格式"""
    role: str       # "user" 或 "assistant"
    content: str    # 消息内容


class ChatRequest(BaseModel):
    """聊天请求的完整格式 —— 前端发 POST /chat/stream 时的请求体必须长这样"""
    query: str                          # 用户的问题
    api_key: str                        # DeepSeek API密钥
    history: List[ChatMessage] = []     # 聊天历史（可选，默认空列表）
    multi_query_count: int = 2          # 多查询扩展数量（可选，默认2）


def validate_api_key(api_key: str) -> bool:
    """验证 API Key 格式和基本有效性"""
    if not api_key:
        print("❌ API Key 不能为空")
        return False
    # 检查 DeepSeek API Key 格式 (sk-开头，长度约50)
    if not api_key.startswith("sk-"):
        print("❌ API Key 格式无效")
        return False
    # 防止明显的测试密钥
    if api_key in ["sk-test", "sk-demo", "sk-example"]:
        print("❌ API Key 不能使用测试密钥")
        return False
    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第①步续：异常处理器注册
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# @app.exception_handler(XXX) 表示：当某类异常发生时，用下面这个函数处理
# 作用：把技术性的错误信息转换成用户友好的JSON响应

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """请求太频繁时的处理（429状态码）"""
    logger.warning(f"⚠️ 限流触发: {get_remote_address(request)}")
    return JSONResponse(
        status_code=429,
        content={"detail": "请求过于频繁，请稍后再试"}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """兜底异常处理：所有未被单独捕获的异常都会走到这里（500状态码）"""
    logger.error(f"❌ 未捕获异常: {type(exc).__name__}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"}
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第③步：路由注册 —— 定义各个API端点
# 每个路由 = 一个URL路径 + 一个HTTP方法 + 一个处理函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ── 路由1: 根路径重定向 ──
# @app.get("/") 表示：当有人用 GET 方法访问 http://localhost:8000/ 时，调用下面这个函数
@app.get("/")
async def redirect_to_docs():
    """访问根路径时，自动跳转到API文档页面"""
    return RedirectResponse(url="/docs")


# ── 路由2: 健康检查 ──
# GET /health → 运维人员/监控系统用来确认服务是否正常运行
@app.get("/health")
async def health_check():
    """健康检查端点，用于监控服务状态"""
    db_exists = index_construction.database_exists()
    doc_count = index_construction.get_document_count()

    return {
        "status": "healthy",
        "version": "4.3",
        "database_exists": db_exists,
        "document_count": doc_count,
        "models_loaded": {
            "embeddings": index_construction._embeddings_cache is not None,
            "cross_encoder": index_construction._cross_encoder_cache is not None,
            "vectorstore": index_construction._vectorstore_cache is not None,
            "bm25": index_construction._bm25_cache is not None,
        },
        "cache_status": {
            "router_cache_size": retrieval_optimization.ROUTER_CACHE.size(),
            "retrieval_cache_generation": retrieval_optimization.RETRIEVAL_CACHE.generation(),
        }
    }


# ── 路由3: 性能指标 ──
# GET /metrics → 返回延迟分位数、阶段分解等性能数据
@app.get("/metrics")
async def get_metrics():
    """性能指标端点，返回延迟分位数和阶段分解"""
    return performance_monitor.get_metrics()


# ── 路由4: 文档上传 ──
# @app.post("/upload") 表示：前端用 POST 方法上传文件到 /upload 路径
# BackgroundTasks: FastAPI内置的后台任务机制 —— 函数返回响应后，后台继续执行任务
# files: List[UploadFile] = File(...) 表示接收多个上传文件
@app.post("/upload")
async def upload_document(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """
    上传文档到知识库
    支持批量上传，自动去重，后台处理

    流程：
    1. 前端上传PDF文件 → 2. 保存为临时文件 → 3. 立即返回任务ID
    4. 后台异步处理：去重 → 解析 → 分块 → 向量化 → 存入数据库
    """
    # 准备临时文件（把上传的文件保存到磁盘临时位置）
    temp_files, original_names = data_preparation.prepare_upload_files(files)

    # 生成唯一任务ID，前端用这个ID来轮询处理进度
    import uuid
    task_id = uuid.uuid4().hex
    data_preparation.TASK_STATUS[task_id] = {"status": "排队准备中...", "progress": 0, "total": 0}

    # 把耗时操作加入后台任务队列
    # add_task 不会阻塞当前请求，函数会立即返回响应，后台慢慢处理
    background_tasks.add_task(
        data_preparation.process_and_store_documents_bg,
        task_id, temp_files, original_names
    )

    return {"status": "success", "task_id": task_id, "message": "文件已接收，后台疯狂处理中！"}


# ── 路由5: 任务状态查询 ──
# GET /task_status/abc123 → 查询某个上传任务的进度
# {task_id} 是路径参数，FastAPI自动从URL中提取
@app.get("/task_status/{task_id}")
async def get_task_status(task_id: str):
    """获取后台任务状态"""
    status = data_preparation.get_task_status(task_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="找不到该任务")
    return status


# ── 路由6: 清空数据库 ──
# DELETE /clear_db → 删除整个向量数据库
@app.delete("/clear_db")
async def clear_database():
    """清空本地向量数据库"""
    index_construction.clear_all_caches()
    if os.path.exists(config.DB_PATH):
        try:
            shutil.rmtree(config.DB_PATH)
            return {"status": "success", "message": "本地数据库已清空"}
        except PermissionError:
            raise HTTPException(status_code=423, detail="文件被锁定")
    return {"status": "success", "message": "数据库本来就是空的"}


# ── 路由7: 流式聊天（核心接口） ──
# @app.post("/chat/stream") 表示：前端 POST 请求到 /chat/stream
# @limiter.limit(config.RATE_LIMIT) 表示：这个接口限流 30次/分钟
# request: Request 是 FastAPI 自动注入的请求对象（限流器需要它获取IP地址）
# chat_request: ChatRequest 是请求体，FastAPI 自动把 JSON 解析成这个对象
@app.post("/chat/stream")
@limiter.limit(config.RATE_LIMIT)
async def chat_stream(request: Request, chat_request: ChatRequest):
    """
    流式聊天接口 —— 核心功能
    支持闲聊模式和技术查询模式，自动路由判决

    完整流程：
    用户问题 → 验证API Key → 路由判决(闲聊/技术) → 分支处理 → 流式返回

    "流式"的意思：不是等整个回答生成完再返回，而是一边生成一边发送，
    就像打字机一样一个字一个字地输出，用户可以立即看到部分回答。
    """
    # API Key 验证
    if not validate_api_key(chat_request.api_key):
        raise HTTPException(status_code=401, detail="无效的 API Key 格式")

    # 记录请求开始时间（用于计算总延迟）
    overall_start = time.time()

    try:
        # 创建LLM实例（DeepSeek大模型客户端）
        llm = generation_integration.create_llm(chat_request.api_key, streaming=True)

        # 把前端传来的聊天历史转换成 LangChain 的消息格式
        chat_history = generation_integration.convert_chat_messages(chat_request.history)

        # ── 路由判决：判断用户是在闲聊还是在问技术问题 ──
        route_start = time.time()
        # 返回 (路由结果, 来源): 结果=0闲聊/1技术, 来源=cache/local_rule/llm
        route_result, route_source = await retrieval_optimization.get_route_result(
            chat_request.query, chat_request.api_key
        )
        route_latency = time.time() - route_start
        performance_monitor.log_stage_latency("routing", route_latency)

        is_cached = (route_source == "cache")

        # ── 分支1: 闲聊模式 ──
        if route_result == 0:
            # 创建闲聊链（不检索知识库，直接让LLM回答）
            chitchat_generator = generation_integration.create_chitchat_chain(llm, chat_history)

            # StreamingResponse：流式响应，不是一次返回全部内容
            # 而是通过 yield 一点一点发送，前端可以实时显示
            async def chitchat_stream():
                async for chunk in chitchat_generator(chat_request.query):
                    yield chunk  # 每生成一小段就立即发送给前端
                # 流结束后记录性能指标
                overall_latency = time.time() - overall_start
                performance_monitor.log_query(route_source, overall_latency, is_cached, route_result=0)

            return StreamingResponse(chitchat_stream(), media_type="text/plain")

        # ── 分支2: 技术查询模式（RAG检索增强生成） ──
        else:
            # 检查数据库是否存在
            if not index_construction.database_exists():
                raise HTTPException(status_code=400, detail="本地数据库未建立。要查专业知识，请先上传文档哦。")

            # 创建检索器（BM25+向量混合检索 → 缓存 → MultiQuery → 重排序）
            retriever = retrieval_optimization.create_rag_retriever(
                llm, chat_request.api_key, chat_request.multi_query_count
            )

            # 创建RAG链（检索器 + LLM生成器组合）
            rag_chain = generation_integration.create_rag_chain(llm, retriever, chat_history)

            # 流式生成RAG回答
            async def rag_stream():
                async for chunk in generation_integration.generate_rag_response(
                    rag_chain, chat_request.query, chat_history
                ):
                    yield chunk  # 每生成一小段就立即发送
                # 流结束后记录性能指标
                overall_latency = time.time() - overall_start
                performance_monitor.log_query(route_source, overall_latency, is_cached, route_result=1)

            return StreamingResponse(rag_stream(), media_type="text/plain")

    except HTTPException as e:
        # HTTPException 是我们主动抛出的业务异常（如401/400/429）
        logger.error(f"HTTP错误: {e.detail}")
        raise
    except Exception as e:
        # 其他未知异常
        logger.error(f"查询处理错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 入口点：直接运行 python main.py 时执行
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    import uvicorn
    # uvicorn 是 ASGI 服务器，负责接收 HTTP 请求并转给 FastAPI 处理
    # host="0.0.0.0" 表示监听所有网卡（允许外部访问）
    # port=8000 表示服务运行在 8000 端口
    uvicorn.run(app, host="0.0.0.0", port=8000)
