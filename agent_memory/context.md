# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical product doc: docs/modify/抖音运营智能体修改设计方案（1）.md.
Phased execution for a new conversation: stage/README.md and stage/抖音运营智能体分阶段实施套餐.md.
Do not treat deleted stage1/ as source. Do not edit C's Dify.

## Phase 0 landed
Read-only catalog `douyin_ops`; Douyin identity prompt; Settings Dify fields; `scheduler_enabled` default false; `knowledge/douyin_ops_demo`; FastAPI/Streamlit title copy. Runtime graph/API/memory namespaces are still the personal assistant.

## Phase 1 landed
Business SQL in `app/sql/001_business.sql`. Test repository is `InMemoryBusinessRepository`. Production applies schema, requires pgvector, and uses `PostgresBusinessRepository`. Instance create then Store seed is not one distributed transaction; seed failure marks `agent_knowledge_documents.status=failed` and keeps the instance.

## Phase 2 landed
Real `login_name` + PBKDF2 password hash. Bearer session 7 days. Plaza HTTP: list/create/patch/open/sidebar/avatar. Create binds `douyin-lead-discovery` and seeds demo KB. Opening a thread does not bump card `updated_at`. Old unauthenticated `POST /v1/threads` is no longer the product entry.

## Phase 3 landed
`ainvoke` configurable carries `thread_id` / `user_id` / `agent_instance_id` / `allowed_workflow_codes`. Profile memory uses `(user_id, agent_instance_id, "profile")`. Chatbot retrieve and `search_kb` use `(user_id, agent_instance_id, "kb")` and skip re-embedding the last ToolMessage. Media lives under `outputs/{user_id}/{agent_instance_id}/images|videos` with owner ids in the URL; cross-user access is 404/403; anonymous media is 401. `media_assets` is written on generate. Graph nodes remain chatbot + tools. DifyClient is still a later phase.

## Plaza/sidebar
一人多实例; unique title per user among non-archived (case-insensitive, no whitespace); card avatar/name/intro/mode/timestamps; sidebar capability_description + development notes + read-only single mode + knowledge panel; no model column; catalog supplies workflow/tool names and user_facing_summary. Chat click does not bump updated_at.

## Dify / tools
Keep ToolNode + DifyClient + catalog/binding. Do not wrap C's Dify as MCP.
v1 transport: POST /v1/workflows/run + DIFY_API_KEY, tool discover_douyin_leads, no_send=false.
Phases 0-6 mock only; phase 7 live true-send behind DIFY_LIVE_ENABLED.
DOUYIN_HTTP_* may be empty because C's workflow has defaults.
Reserve agent_instance_workflows. Catalog stays code/config. Do not compile a graph per instance.

## Client
Streamlit is the v1 plaza stand-in. FastAPI Bearer JSON is the contract for the later frontend.
Real login_name + PBKDF2 password hash. Default-disable morning brief / hydrate scheduler; keep send_email / weather / memory tools in chat.

## Knowledge
Per-instance vector retrieve inside chatbot; seed douyin_ops demo; optional search_kb as 补检索. Metadata table agent_knowledge_documents; chunks in Store namespace (user_id, agent_instance_id, "kb"). Production PostgresStore embedding index (pgvector).

## Data
Deployment B: server Postgres is source of truth. Do not ALTER LangGraph official tables.
