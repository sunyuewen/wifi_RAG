@echo off
REM Wi-Fi GPT RAG系统 - 一键启动脚本 (Windows版)
REM
REM 功能：同时启动后端(FastAPI)和前端(Streamlit)

cls
echo.
echo ======================================================
echo   Wi-Fi GPT RAG 系统 - 启动脚本
echo ======================================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python解释器
    echo 请先安装Python 3.8+
    pause
    exit /b 1
)

echo [?] Python 检查通过
echo.

REM 检查依赖
echo [检查] 验证依赖包...
python -c "import fastapi; import streamlit; import langchain" >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 依赖包缺失，正在安装...
    pip install -r requirements.txt
)

echo [?] 依赖包就绪
echo.

REM 检查.env文件
if not exist ".env" (
    echo [错误] .env文件不存在
    echo 请在项目目录创建.env文件并配置OPENAI_API_KEY
    echo 参考.env.example文件
    pause
    exit /b 1
)

echo [?] 配置文件就绪
echo.

REM 创建日志目录
if not exist "logs" mkdir logs

echo ======================================================
echo   准备启动服务
echo ======================================================
echo.
echo [后端] FastAPI 地址 http://127.0.0.1:8000
echo [前端] Streamlit 地址 http://127.0.0.1:8501
echo.
echo 按任意键开始启动...
pause
echo.

REM 启动后端，打开新窗口：
echo [启动] 后端服务...
start "Wi-Fi GPT Backend" cmd /k "python -m uvicorn main:app --reload --port 8000 2>&1 | tee logs/backend.log"

REM 等待后端启动
echo [等待后端启动...]
timeout /t 3 /nobreak

REM 启动前端，打开新窗口：
echo [启动] 前端服务...
start "Wi-Fi GPT Frontend" cmd /k "streamlit run frontend.py 2>&1 | tee logs/frontend.log"

echo.
echo [?] 服务启动完成
echo.
echo ? 接口文档: http://127.0.0.1:8000/docs
echo ? 前端应用: http://127.0.0.1:8501
echo ? 健康检查: http://127.0.0.1:8000/health
echo.
echo [提示] 按 Ctrl+C 停止各个服务窗口
echo [提示] 日志文件保存在 logs/ 目录
echo.
pause
