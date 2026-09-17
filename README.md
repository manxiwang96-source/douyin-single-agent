# 个人超级助理

日常问答、记忆、天气、晨间简报和喝水提醒。小红书写稿、配图、配视频仍是同一助手的能力：只有用户明确要求时才检索知识库并输出【标题】【正文】【标签】。不登录、不发布小红书。图拓扑保持 `chatbot` + `tools`。

## 准备

1. 复制 `.env.example` 为 `.env` 并填写密钥（实现不会覆盖已有 `.env`）。
2. 使用仓库 `venv`：

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

本地 PostgreSQL 与 163 SMTP 只写在 `.env`，不要入库。

## 启动

两个进程：

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
.\venv\Scripts\python.exe -m streamlit run ui/streamlit_app.py
```

Streamlit 默认请求 `http://127.0.0.1:8000`，可用环境变量 `STREAMLIT_API_BASE` 覆盖。

手动触发任务：`POST /v1/assistant/jobs/run`，body 为 `{"kind":"morning_brief"}` 或 `{"kind":"hydrate","slot":"10"}`。

## 测试

默认全 mock，不打真实 API、Postgres、SMTP 或 Open-Meteo：

```powershell
.\venv\Scripts\python.exe -m pytest
```

交付门禁（立即跑晨报，真实 MCP + 真实 163 邮件）：

```powershell
$env:RUN_LIVE_ASSISTANT=1
.\venv\Scripts\python.exe -m pytest tests/test_live_assistant.py
```

可选 cheapest 冒烟（需密钥与网络，不作为本改造成功定义）：

```powershell
$env:RUN_LIVE_API=1
.\venv\Scripts\python.exe -m pytest tests/test_live_api.py
```