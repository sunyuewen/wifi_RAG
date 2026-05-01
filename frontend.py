import streamlit as st
import requests
import json
import time # 在顶部别忘了加上 import time
import os # 新增这行

# 强行告诉 Python 的网络库：不要对本地地址使用系统代理
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

# --- 配置后端 API 地址 ---
API_BASE_URL = "http://127.0.0.1:8000"

# --- 1. 页面级全局 UI 优化 ---
st.set_page_config(page_title="Wi-Fi 7 专家智库", page_icon="📡", layout="wide")

# 注入自定义 CSS 让界面更具科技感
st.markdown("""
    <style>
    /* 调整主标题样式 */
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #1e3c72, #2a5298);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    /* 调整侧边栏背景和字体 */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e0e0e0;
    }
    /* 聊天气泡样式微调 */
    .stChatMessage {
        border-radius: 10px;
        padding: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# 顶部横幅
st.markdown('<p class="main-title">📡 Wi-Fi 7 & 通信协议全栈智库</p>', unsafe_allow_html=True)
st.caption("基于 FastAPI 后端驱动的流式 RAG 检索系统")
st.divider()

# --- 2. 侧边栏：控制台与状态盘 ---
with st.sidebar:
    st.image("https://img.icons8.com/clouds/200/000000/wifi.png", width=150)
    st.header("⚙️ 引擎控制台")

    api_key = st.text_input("🔑 DeepSeek API Key", type="password", help="在此输入你的密钥以激活大模型大脑")

    st.markdown("---")
    st.subheader("📁 知识库管理 (向后端传文件)")

    # uploaded_file = st.file_uploader("上传新的 PDF 协议书", type="pdf", label_visibility="collapsed")
    uploaded_files = st.file_uploader("批量上传多份 PDF 协议书", type="pdf", label_visibility="collapsed",
                                      accept_multiple_files=True)

    st.markdown("---")
    st.subheader("🎛️ 检索参数配置")
    multi_query_count = st.slider(
        "多查询扩展数量 (1=最快, 5=最精准)",
        min_value=1,
        max_value=5,
        value=2,
        help="值越大检索越精准，但响应时间越长"
    )
    if st.button("🚀 批量上传并构建向量库", use_container_width=True, type="primary"):
        task_id = None  # 先初始化

        if uploaded_files and api_key:
            # 缩进块 1：只负责发文件和拿快递单号
            with st.spinner("🚀 正在投递文件至引擎..."):
                files_payload = [("files", (file.name, file.getvalue(), "application/pdf")) for file in uploaded_files]
                try:
                    response = requests.post(f"{API_BASE_URL}/upload", files=files_payload)
                    if response.status_code == 200:
                        task_id = response.json().get("task_id")
                        st.success("✅ 文件投递成功！系统转入后台静默处理。")
                    else:
                        st.error(f"❌ 后端拒绝投递: {response.text}")
                except Exception as e:
                    st.error("网络连接失败，请确认后端的 FastAPI 是否运行！")

            # 🔥 缩进块 2：注意！这里已经退出了 with st.spinner 的缩进！
            # 转圈圈动画到这里就会消失，接力棒交给真正的进度条！
            if task_id:
                progress_bar = st.progress(0, text="⏳ 准备解析...")
                while True:
                    try:
                        status_res = requests.get(f"{API_BASE_URL}/task_status/{task_id}")
                        if status_res.status_code == 200:
                            task_info = status_res.json()
                            current_status = task_info["status"]
                            prog = task_info.get("progress", 0)
                            total = task_info.get("total", 0)

                            if current_status == "error":
                                st.error(f"❌ 后端处理崩溃: {task_info.get('error_msg')}")
                                progress_bar.empty()
                                break
                            elif current_status == "completed":
                                progress_bar.progress(1.0, text=f"🎉 彻底完成！共解析 {total} 个知识块。")
                                st.balloons()
                                break
                            else:
                                if total > 0:
                                    pct = min(prog / total, 1.0)
                                    progress_bar.progress(pct, text=f"{current_status} ({prog}/{total} 块)")
                                else:
                                    progress_bar.progress(0, text=f"{current_status}")
                    except:
                        pass  # 忽略偶发的网络抖动

                    time.sleep(1.5)
        else:
            st.warning("请先填写 API Key 并至少选择一个文件。")

    if st.button("🗑️ 清空服务器数据库", use_container_width=True):
        try:
            response = requests.delete(f"{API_BASE_URL}/clear_db")
            if response.status_code == 200:
                st.success("✅ 后端数据库已清空！")
            else:
                st.error(f"❌ {response.json().get('detail')}")
        except:
            st.error("无法连接到后端服务器。")

# --- 3. 聊天主界面：对接流式 API ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# 渲染历史记录
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if api_key:
    if user_query := st.chat_input("向协议智库提问（支持连续追问）..."):
        # 1. 把用户的问题立刻显示在界面上
        with st.chat_message("user"):
            st.markdown(user_query)

        # 2. 准备发给 FastAPI 的数据体
        payload = {
            "query": user_query,
            "api_key": api_key,
            "history": st.session_state.messages,
            "multi_query_count": multi_query_count
        }

        # 3. 呼叫后端，并接收"像水流一样"的数据
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_answer = ""

            with st.spinner("📡 正在连接后端检索引擎..."):
                try:
                    # 使用 requests 进行流式请求 (stream=True)，添加超时
                    with requests.post(
                        f"{API_BASE_URL}/chat/stream",
                        json=payload,
                        stream=True,
                        timeout=120
                    ) as r:
                        if r.status_code == 200:
                            # 一点一点读取后端吐出来的字
                            for chunk in r.iter_content(chunk_size=1024, decode_unicode=True):
                                if chunk:
                                    full_answer += chunk
                                    message_placeholder.markdown(full_answer + " ▌")  # 闪烁光标特效

                            # 去掉末尾光标
                            message_placeholder.markdown(full_answer)

                            # 保存到记忆中
                            st.session_state.messages.append({"role": "user", "content": user_query})
                            st.session_state.messages.append({"role": "assistant", "content": full_answer})
                        elif r.status_code == 401:
                            st.error("❌ API Key 无效，请检查后重新输入")
                        elif r.status_code == 429:
                            st.error("❌ 请求过于频繁，请稍后再试")
                        elif r.status_code == 400:
                            st.error(f"❌ 错误请求: {r.text}")
                        else:
                            st.error(f"❌ 后端错误 ({r.status_code}): {r.text}")
                except requests.exceptions.Timeout:
                    st.error("❌ 请求超时，请检查网络或稍后重试")
                except requests.exceptions.ConnectionError:
                    st.error("❌ 无法连接到后端服务器，请确认 FastAPI (127.0.0.1:8000) 是否正在运行！")
                except Exception as e:
                    st.error(f"❌ 发生错误: {str(e)}")
else:
    st.info("👈 请先在左侧输入 API Key 激活系统。")
