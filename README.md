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

## Vue 智能体模块

工人 HTTP 仍由 FastAPI 提供。Vue 是可独立启动的广场/对话模块，Streamlit 仍可作为过渡客户端保留。

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。开发服务器把 `/v1` 代理到 `http://127.0.0.1:8000`；默认 `VITE_API_BASE` 为空走同源代理。直连后端时再设绝对地址。

闭环：登录/注册 → 「我的智能体」→ 「新建智能体」两步弹窗（运营助手或自定义智能体）→ 运营助手留在广场，自定义智能体进入配置页 → 点卡片进入正式对话（中间聊天 + 右侧只读侧边栏）。

前端测试：

```powershell
cd frontend
npm test
```

手动触发任务：`POST /v1/assistant/jobs/run`，body 为 `{"kind":"morning_brief"}` 或 `{"kind":"hydrate","slot":"10"}`。

## 自定义智能体

广场可创建两类实例：

- 自定义智能体：创建后进入 `/agents/:id/edit` 配置页。
- 运营助手：创建后留在广场，编辑仍走弹窗。

创建后即有一份已发布默认配置。点卡片 `POST /open` 进入正式聊天，始终钉 published，不会 409，也不会用 draft 冒充 published。

配置页为顶栏 + 左导航 + 中间编辑 + 右调试。可配置提示词（双模式、优化对比/撤销）、欢迎语、示例、知识上传、工具目录勾选、新建/编辑 Skill。右侧调试是 draft 真实 SSE（`thread_kind=debug`，每条消息重读 draft），正式聊天钉 published（`thread_kind=official`）。正式空聊天展示已发布欢迎语和可点示例。

运营助手、Dify 线索工具名 `discover_leads`、现有媒体 HITL 与 SSE resume 保持不变。调试区图片/文件输入可缺。

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