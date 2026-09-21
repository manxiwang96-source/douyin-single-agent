# Architecture

## Layout
- app/config.py: Settings from env, cheapest image/video params, assistant city/timezone, Postgres/SMTP/MCP/scheduler flags, production validation
- app/postgres.py: create database if missing; ConnectionPool + PostgresSaver.setup() + PostgresStore.setup() with pgvector index; apply business schema; no SQLite fallback
- app/sql/001_business.sql: Douyin worker business tables; never ALTER checkpoints* / store
- app/schema.py: load/apply business SQL; CREATE EXTENSION vector or fail with a clear reason
- app/repository.py: InMemoryBusinessRepository for default pytest
- app/postgres_repository.py: psycopg production repository
- app/mcp_client.py: FastMCP stdio via MultiServerMCPClient.get_tools(); McpFactsProvider for weekday/weather/temp
- mcp_servers/personal.py: get_current_datetime + get_weather (Open-Meteo, default Guangzhou)
- app/email_client.py: SMTP_SSL smtp.163.com:465
- app/jobs.py: run_morning_brief / run_hydrate / catch_up_jobs; ainvoke timeout then facts-email fallback; idempotency namespace assistant/jobs
- app/scheduler.py: APScheduler 08:00 morning brief; hydrate 10/12/14/16/18/20/22
- app/embeddings.py / app/knowledge.py: hashing embed in tests; InMemoryStore RAG
- app/image_client.py: Gateway POST /images/generations
- app/video_client.py: DashScope async video-synthesis + poll
- app/tools.py: search_kb executes immediately; generate_image/generate_video call interrupt then Command(update=...); remember_fact/recall_facts/send_email plus extra MCP tools join the same ToolNode
- app/graph.py: tutorial graph — chatbot + tools (ToolNode) + tools_condition; custom last_image_path / last_video_path; compile(checkpointer=..., store=memory_store)
- app/runtime.py: production PostgresSaver + PostgresStore; tests InMemorySaver + in-memory long-term store and InMemoryBusinessRepository; ChatOpenAI timeout + max_tokens so the gateway cannot generate forever
- app/main.py: FastAPI factory create_app(runtime=None); ainvoke for message/resume; POST /v1/assistant/jobs/run; lifespan scheduler + catch-up
- app/prompts.py: identity is 个人超级助理; Xiaohongshu format and search_kb only when explicitly requested
- app/serialize.py: thread JSON with media URLs and review_media interrupt
- ui/view_model.py: maps media URLs to image/video widgets; HITL card vs chat history
- ui/streamlit_app.py: thin HTTP client titled 个人超级助理, st.chat_message + st.chat_input, HITL above chat
- knowledge/*.md: demo KB
- tests/: mocked suite + optional RUN_LIVE_ASSISTANT=1 / RUN_LIVE_API=1 smokes

## Graph
START -> chatbot -> tools_condition -> tools -> chatbot
                              \-> END
Nodes remain only chatbot and tools. MCP, email, and memory tools join the existing ToolNode.
Media tools interrupt inside ToolNode. Resume with Command(resume=...).
parallel_tool_calls=False.

## Memory
- Short-term: production PostgresSaver; tests InMemorySaver
- Long-term: production PostgresStore; tests in-memory store; namespaces assistant/profile and assistant/jobs
- Stage 3 isolation: conversation profile/KB use (user_id, agent_instance_id, "profile"|"kb"); media files live under outputs/{user_id}/{agent_instance_id}/images|videos; HTTP media URLs include those ids
- Production PostgresStore embedding index uses pgvector; startup fails if the extension is missing
- Business tables live beside official LangGraph tables; tests use InMemoryBusinessRepository and never open real Postgres
- KB RAG stays process-local InMemoryStore
- Secrets stay in local .env and are never stored in git

## Runtime processes
1. uvicorn app.main:create_app --factory
2. streamlit run ui/streamlit_app.py
3. Optional POST /v1/assistant/jobs/run with kind=morning_brief|hydrate

## Delivery
Default pytest is fully mocked.
Delivery gate is RUN_LIVE_ASSISTANT=1: immediately run morning brief, real MCP weekday/weather/temp, real 163 email.

## Next redesign

Current target is 抖音运营智能体, but this file remains the 个人超级助理 runtime map until later phases land.
Locked product: `docs/modify/抖音运营智能体修改设计方案（1）.md`.
Execute the upgrade one phase at a time from stage/README.md and stage/抖音运营智能体分阶段实施套餐.md.

阶段 0 landed docs/config. 阶段 1 landed business SQL + in-memory/Postgres repositories and production pgvector/schema startup. 阶段 2 landed FastAPI login/register/logout/me and plaza HTTP (create/list/patch/open/sidebar/avatar) with Bearer sessions; creating a douyin_ops instance binds douyin-lead-discovery and seeds demo KB. 阶段 3 landed per-user/instance isolation for ainvoke configurable, profile/KB namespaces, media paths, media_assets, and thread ownership. 阶段 4 landed `discover_douyin_leads` inside the existing ToolNode via DifyClient; default pytest injects FakeDifyClient and `DIFY_LIVE_ENABLED` stays false. Graph nodes remain chatbot + tools. Do not rewrite this file as if DifyClient has replaced the 个人超级助理 graph. Streamlit is still the old unauthenticated chat entry.

That doc's client entry is 登录 → 新建智能体（一人多实例，填名称/简介/头像）→ 点卡片用这个智能体 → 对话+只读侧边栏; 能力只展示、不勾选; `ainvoke` will carry `thread_id` / `user_id` / `agent_instance_id`. Graph nodes stay unchanged. Retrieve happens inside chatbot against the instance KB. v1 Dify contract is one tool `discover_douyin_leads` over `douyin-lead-discovery` with `no_send=false`, transport `POST /v1/workflows/run` + Service API key; `difyctl` is retired; Dify stays in ToolNode, not MCP. Comment/DM HITL tables exist but v1 does not review outbound Douyin. `DIFY_LIVE_ENABLED` stays false until phase 7.
