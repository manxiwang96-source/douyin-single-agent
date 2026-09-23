# Architecture

## Product
This repository is the 抖音运营智能体 worker. It is independently runnable. It is not the supervisor and not classmate C's Dify. Locked product: `docs/modify/抖音运营智能体修改设计方案（1）.md`. Phased execution: `stage/README.md` and `stage/抖音运营智能体分阶段实施套餐.md`.

User entry: Vue module at `frontend/` (login -> create a `douyin_ops` instance (name/intro/avatar, one user many instances) -> click the 广场 card -> chat + read-only sidebar). Streamlit remains a transitional client. Capabilities are displayed, not checked. Opening a thread does not bump card `updated_at`.

## Layout
- app/config.py: Settings from env; Dify + Douyin HTTP fields; `scheduler_enabled` default false; `dify_live_enabled` default false in code / `.env.example`; default `cors_origins` allow Streamlit `8501` and Vue `5173`; production validation; `public_config()` never returns secrets
- app/catalog.py: read-only `douyin_ops` template, workflow `douyin-lead-discovery`, tool `discover_douyin_leads`
- app/postgres.py: create database if missing; ConnectionPool + PostgresSaver.setup() + PostgresStore.setup() with pgvector index; apply business schema; no SQLite fallback
- app/sql/001_business.sql: Douyin worker business tables; never ALTER checkpoints* / store
- app/schema.py: load/apply business SQL; CREATE EXTENSION vector or fail with a clear reason
- app/repository.py: InMemoryBusinessRepository for default pytest
- app/postgres_repository.py: psycopg production repository
- app/auth.py: login_name + PBKDF2 password hash; Bearer session 7 days
- app/dify_client.py: POST `{DIFY_BASE_URL}/workflows/run` with Bearer `DIFY_API_KEY`, `response_mode=blocking`; live POST only when `DIFY_LIVE_ENABLED=true` or an http_client is injected
- app/leads.py: `discover_douyin_leads` inputs/dedup/writeback; `no_send=false` and `auto_login=true` hardcoded; fill C start-node defaults for platform/limit/channels/assess; sanitize `channels` to `comment`/`message`/`comment,message` (map `dm`/中文); drop keyword when `video_id` is present; empty local `DOUYIN_HTTP_BASE_URL` uses published `http://192.168.1.33:8765`; empty `DOUYIN_HTTP_API_TOKEN` omitted from stored inputs
- app/mcp_client.py: FastMCP stdio via MultiServerMCPClient.get_tools(); McpFactsProvider for weekday/weather/temp
- mcp_servers/personal.py: get_current_datetime + get_weather (Open-Meteo, default Guangzhou)
- app/email_client.py: SMTP_SSL smtp.163.com:465
- app/job_control.py: list/disable job definitions and cancel job runs for the current user/instance; HTTP and ToolNode share the same rows
- app/jobs.py: leftover morning brief / hydrate helpers; Douyin 08:00 cron is not implemented
- app/scheduler.py: APScheduler remains, but lifespan does not catch-up when `scheduler_enabled` is false
- app/embeddings.py / app/knowledge.py: hashing embed in tests; instance KB retrieve
- app/image_client.py: Gateway POST /images/generations
- app/video_client.py: DashScope async video-synthesis + poll
- app/tools.py: search_kb, generate_image/generate_video HITL, remember_fact/recall_facts/send_email, discover_douyin_leads, list_jobs/cancel_job, extra MCP tools; all in the same ToolNode
- app/graph.py: chatbot + tools (ToolNode) + tools_condition; compile(checkpointer=..., store=memory_store)
- app/runtime.py: production PostgresSaver + PostgresStore; tests InMemorySaver + in-memory long-term store and InMemoryBusinessRepository; default pytest injects FakeDifyClient
- app/main.py: FastAPI factory create_app(runtime=None); Bearer plaza/auth/open/sidebar; ainvoke for message/resume
- app/prompts.py: identity is 抖音运营助手; must say 会真实发送 then immediately call `discover_douyin_leads`; do not ask for keyword when `video_id` is present; channels stay `comment,message`; no Xiaohongshu note template
- app/serialize.py: thread JSON with media URLs and review_media interrupt
- ui/view_model.py: plaza cards, readonly sidebar, auth_gate so a thread exists only after login and /open
- ui/streamlit_app.py: Streamlit v1 client over existing HTTP; token in session_state as Bearer; transitional, not deleted
- frontend/: Vue 3 + Vite plaza module; routes `/login`, `/agents`, `/agents/:agentInstanceId`; Bearer in localStorage; CSS prefix `agent-`
- knowledge/douyin_ops_demo/*.md: per-instance demo KB
- tests/: mocked suite; optional RUN_LIVE_API=1 / RUN_LIVE_ASSISTANT=1 leftovers; Douyin delivery gate RUN_LIVE_DOUYIN=1 in tests/test_live_douyin.py

## Graph
START -> chatbot -> tools_condition -> tools -> chatbot
                              \-> END
Nodes remain only chatbot and tools. Dify is a ToolNode tool, not MCP and not a new node.
Media tools interrupt inside ToolNode. Resume with Command(resume=...).
parallel_tool_calls=False.
ainvoke configurable carries thread_id / user_id / agent_instance_id / allowed_workflow_codes.

## Memory
- Short-term: production PostgresSaver; tests InMemorySaver
- Long-term: production PostgresStore; tests in-memory store
- Conversation profile/KB: (user_id, agent_instance_id, "profile"|"kb")
- Media files: outputs/{user_id}/{agent_instance_id}/images|videos; HTTP media URLs include those ids
- Production PostgresStore embedding index uses pgvector; startup fails if the extension is missing
- Business tables live beside official LangGraph tables; tests use InMemoryBusinessRepository and never open real Postgres
- Secrets stay in local .env and are never stored in git, docs, or agent_memory

## HTTP entry
- Auth: POST /v1/auth/register|login|logout, GET /v1/me
- Plaza: GET/POST /v1/agent-instances, PATCH /v1/agent-instances/{id}, DELETE /v1/agent-instances/{id}, POST /v1/agent-instances/{id}/open, GET sidebar/avatar
- Chat: GET /v1/threads/{id}, POST /v1/threads/{id}/messages, POST /v1/threads/{id}/resume
- Jobs: POST /v1/jobs/{job_id}/disable, POST /v1/job-runs/{run_id}/cancel
- Leftover: POST /v1/assistant/jobs/run
- Old unauthenticated POST /v1/threads is rejected; use /open after login
- Vue `frontend/` is the plaza module client; Streamlit remains the transitional stand-in; FastAPI Bearer JSON is the contract

## Dify
v1 has one product tool `discover_douyin_leads` bound to published workflow `douyin-lead-discovery`.
Transport: POST `{DIFY_BASE_URL}/workflows/run` + `Authorization: Bearer {DIFY_API_KEY}`.
Server forces `no_send=false` (true-send) in both `build_dify_inputs` and `DifyClient.run`, plus `auto_login=true`. This is not an env switch; C's start-node default `true` is never sent.
Published start-node required defaults are filled by the worker when the model omits them: `platform=douyin`, `limit=20`, `channels=comment,message`, `assess=true`. Invalid model `channels` such as `comment,dm` or 中文「评论、私信」are mapped or replaced with `comment,message`. If `video_id` is present, keyword is omitted from stored inputs.
C's `no_send` / `auto_login` / `assess` are select options `true`/`false`; DifyClient stringifies JSON booleans only on the HTTP body. `workflow_runs.inputs` still stores Python bools.
If local `DOUYIN_HTTP_BASE_URL` is empty, send C's published start-node default `http://192.168.1.33:8765` so startup is not blocked. Empty `DOUYIN_HTTP_API_TOKEN` is still omitted from stored inputs; live `DifyClient` `GET /parameters` fills only missing required start-node defaults on the HTTP body, because `/workflows/run` does not apply console defaults. Hardcoded `no_send=false` is never overwritten. Do not change C's Dify.
`user` is our `user_id`. Paused/needs_login accounts are rejected; missing projection rows are allowed.
In-progress runs in a 10-minute window are reused. Each real call writes `workflow_runs`; list_comment/list_message/snapshot writeback is best-effort.
v1 does not review outbound comments/DMs.

### Dify result contract (landed 2026-09-22)
`DifyClient` retains outer `dify_workflow_status` separately from DSL-derived `job_status`/`job_response`. `job_response.data.status` or root `status` has priority over the DSL loop variable, and missing/unknown job state is `unverified` with `job status unavailable`; it never defaults to success. Dify error extraction preserves `error`, `reason`, `error_message`, `failure_reason`, or `message` supplied by Dify. `discover_douyin_leads` exposes `workflow_ok`, `delivery_ok`, final `status`, `delivery`, `message_details`, `job_id`, and the two distinct status fields. Only explicit per-item success counts as `delivery.*.sent`; list error objects are errors, not records, and `written` remains local persistence count only. If the job is not succeeded, list results cannot prove successful delivery. `app/prompts.py` tells the assistant to use `job_status` and explicit delivery counts, not outer success or `written`, when describing results. The workflow run table persists `unverified` as `failed` because its existing database status constraint does not include `unverified`; the tool response preserves the user-visible `unverified` state.

## Runtime processes
1. uvicorn app.main:create_app --factory
2. streamlit run ui/streamlit_app.py (transitional client)
3. cd frontend && npm run dev (Vue plaza module on 5173, proxy `/v1` to 8000)
4. scheduler_enabled stays false unless explicitly turned on; Douyin 08:00 scan is not in this worker yet

## Delivery
Default pytest is fully mocked and injects FakeDifyClient; zero real Dify POST.
Local live requires `.env` `DIFY_LIVE_ENABLED=true` (not committed).
Delivery gate is `RUN_LIVE_DOUYIN=1` with `LIVE_DOUYIN_ACCOUNT` and `LIVE_DOUYIN_VIDEO_ID`: one real `POST /v1/workflows/run`, `no_send=false`, writeback `workflow_runs`, and a scan/send summary in the tool result.
Skip due to missing live config is not delivery success.
Old `RUN_LIVE_ASSISTANT=1` morning-brief email is not the Douyin worker success definition.
Live true-send must stagger with C's Feishu bot to avoid double send.
