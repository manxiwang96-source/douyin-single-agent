# Tech Stack

- Python 3.11, existing venv
- FastAPI + uvicorn: HTTP contract; message/resume via `ainvoke`; lifespan APScheduler
- ChatOpenAI: request timeout + max_tokens; morning brief wraps graph `ainvoke` with a timeout and falls back to SMTP facts
- Streamlit: thin chat UI titled 个人超级助理
- LangGraph StateGraph: `chatbot` + `tools` (ToolNode) + `tools_condition`; HITL `interrupt()` inside media tools
- Production memory: `PostgresSaver` + `PostgresStore` (`langgraph-checkpoint-postgres`, `psycopg[binary,pool]`); URI from `POSTGRES_URI`; `setup()` then `compile(checkpointer=..., store=...)`
- Tests: `InMemorySaver` + in-memory long-term store; no real Postgres
- KB RAG: LangGraph `InMemoryStore` + langchain-openai OpenAIEmbeddings (SiliconFlow bge-m3)
- MCP: FastMCP stdio in `mcp_servers/personal.py`; `langchain-mcp-adapters.MultiServerMCPClient.get_tools()` merged into existing tools. Open-Meteo, no API key
- Email: stdlib SMTP_SSL `smtp.163.com:465`
- Scheduler: APScheduler in FastAPI lifespan; OSS has no LangGraph Platform Cron
- httpx for gateway image, DashScope video, Open-Meteo, and the next-upgrade Dify Service API (`POST /v1/workflows/run` + `DIFY_API_KEY`; `difyctl` retired)
- pydantic-settings for env
- pytest fully mocked by default; `RUN_LIVE_ASSISTANT=1` and `RUN_LIVE_API=1` optional live gates

Framework pages are reference-only; do not copy tutorial graphs, `create_react_agent`, or streamable-http weather demos.
Next upgrade (not current runtime): 抖音运营智能体. Catalog template `douyin_ops`; tool `discover_douyin_leads` over workflow `douyin-lead-discovery`. Settings include `DIFY_LIVE_ENABLED` default false. 阶段 0 docs/config and 阶段 1 business SQL/repositories have landed. Do not treat later plaza/DifyClient as already landed.
