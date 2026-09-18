# Context

## Product
Personal super assistant. Xiaohongshu copy/image/video remain capabilities on the same `chatbot` + `tools` graph, not a separate role.

## Locked constraints
- Graph nodes are `chatbot` and `tools` only. No Supervisor, no `create_react_agent`.
- Media HITL uses `interrupt()` inside generate_image / generate_video.
- Production: PostgresSaver + PostgresStore from POSTGRES_URI. Tests: InMemorySaver. KB RAG stays InMemoryStore.
- MCP: repo FastMCP stdio (weekday + Guangzhou weather/temp) via MultiServerMCPClient.get_tools().
- Active outreach: SMTP 163, not Streamlit popups. Morning brief + hydrate jobs.
- Out of scope: Tavily, Xiaohongshu login/publish, Platform Cron, silent SQLite fallback.
- Secrets only in local `.env`. langgraph.com.cn is reference-only; do not paste tutorial code.
- Default pytest fully mocked. Delivery gate is RUN_LIVE_ASSISTANT=1 real MCP + real 163 email.

## Runtime
- Chat: OPENAI_API_BASE_URL + OPENAI_API_MODEL
- Image: IMAGE_PROVIDER=gateway only
- Video: VIDEO_PROVIDER=dashscope (aliyun_wan3 alias)
- HITL before image/video generation
- FastAPI factory: uvicorn app.main:create_app --factory
- Jobs: POST /v1/assistant/jobs/run

## Documentation
- Upgrade package: docs/modify/个人超级助理改造方案.md
- MVP recap remains historical baseline: docs/summary/小红书运营助手对话机器人MVP总结与逻辑复盘（1）.md
- Assistant recap: docs/summary/个人超级助手总结与逻辑复盘（2）.md
