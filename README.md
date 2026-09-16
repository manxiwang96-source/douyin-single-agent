# 小红书运营机器人 MVP

对话写稿、廉价生图、廉价生视频。不登录、不发布小红书。架构按 LangGraph get-started 1–5：`chatbot` + `tools`、SQLite 记忆、工具内 HITL、自定义 `last_image_path` / `last_video_path`。

## 准备

1. 复制 `.env.example` 为 `.env` 并填写密钥（实现不会覆盖已有 `.env`）。
2. 使用仓库 `venv`：

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 启动

两个进程：

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
.\venv\Scripts\python.exe -m streamlit run ui/streamlit_app.py
```

Streamlit 默认请求 `http://127.0.0.1:8000`，可用环境变量 `STREAMLIT_API_BASE` 覆盖。

## 测试

默认全 mock，不打真实 API：

```powershell
.\venv\Scripts\python.exe -m pytest
```

可选 cheapest 冒烟（需密钥与网络）：

```powershell
$env:RUN_LIVE_API=1
.\venv\Scripts\python.exe -m pytest tests/test_live_api.py
```
