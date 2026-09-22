# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical product doc: docs/modify/抖音运营智能体修改设计方案（1）.md.
Phased execution for a new conversation: stage/README.md and stage/抖音运营智能体分阶段实施套餐.md.
Vue client playbook for a later conversation: docs/modify/抖音运营智能体Vue前端实施套餐.md.
Do not treat deleted stage1/ as source. Do not edit C's Dify.

## Phase 0-7 landed
Docs/config, business SQL, login/plaza HTTP, per-instance isolation, DifyClient + discover_douyin_leads, job cancel HTTP/tools, Streamlit plaza client, live Dify true-send behind local `DIFY_LIVE_ENABLED=true` (not committed).
Default pytest still injects FakeDifyClient and must not true-send.
Live gate: `RUN_LIVE_DOUYIN=1` with `LIVE_DOUYIN_ACCOUNT` / `LIVE_DOUYIN_VIDEO_ID`. If `video_id` is present, keyword is omitted.
Worker hardcodes `no_send=false`. Empty `DOUYIN_HTTP_BASE_URL` uses published default `http://192.168.1.33:8765`. Empty `DOUYIN_HTTP_API_TOKEN` is omitted from stored inputs; live HTTP fills missing required start-node defaults from `GET /parameters`.
Do not write Dify keys, tokens, or passwords into git / docs / agent_memory.

## Plaza/sidebar
一人多实例; unique title per user among non-archived (case-insensitive, no whitespace); card avatar/name/intro/mode/timestamps; sidebar capability_description + development notes + read-only single mode + knowledge panel; no model column; catalog supplies workflow/tool names and user_facing_summary. Chat click does not bump updated_at.

## Dify / tools
Keep ToolNode + DifyClient + catalog/binding. Do not wrap C's Dify as MCP.
v1 transport: POST /v1/workflows/run + DIFY_API_KEY, tool discover_douyin_leads, no_send=false.
DOUYIN_HTTP_* may be empty because C's workflow has defaults; `/workflows/run` does not apply console defaults, so the worker fills required missing fields.
Reserve agent_instance_workflows. Catalog stays code/config. Do not compile a graph per instance.

## Client
Streamlit is the v1 plaza stand-in. FastAPI Bearer JSON is the contract.
Vue frontend is not started. Implement it only from docs/modify/抖音运营智能体Vue前端实施套餐.md in a new chat, phase by phase. Do not create `frontend/` until that chat's phase 1.
Default CORS still only allows Streamlit 8501; Vue 5173 is playbook phase 0.

## Knowledge
Per-instance vector retrieve inside chatbot; seed douyin_ops demo; optional search_kb as 补检索. Metadata table agent_knowledge_documents; chunks in Store namespace (user_id, agent_instance_id, "kb"). Production PostgresStore embedding index (pgvector).

## Data
Deployment B: server Postgres is source of truth. Do not ALTER LangGraph official tables.
