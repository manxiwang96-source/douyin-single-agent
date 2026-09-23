# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical product doc: docs/modify/抖音运营智能体修改设计方案（1）.md.
Phased execution: stage/README.md and stage/抖音运营智能体分阶段实施套餐.md.
Vue client playbook: docs/modify/抖音运营智能体Vue前端实施套餐.md.
Do not treat deleted stage1/ as source. Do not edit C's Dify.

## Phase 0-7 landed
Docs/config, business SQL, login/plaza HTTP, per-instance isolation, DifyClient + discover_douyin_leads, job cancel HTTP/tools, Streamlit plaza client, live Dify true-send behind local DIFY_LIVE_ENABLED=true (not committed).
Default pytest still injects FakeDifyClient and must not true-send.
Live gate: RUN_LIVE_DOUYIN=1 with LIVE_DOUYIN_ACCOUNT / LIVE_DOUYIN_VIDEO_ID. If video_id is present, keyword is omitted.
Worker hardcodes no_send=false. Empty DOUYIN_HTTP_BASE_URL uses published default http://192.168.1.33:8765. Empty DOUYIN_HTTP_API_TOKEN is omitted from stored inputs; live HTTP fills missing required start-node defaults from GET /parameters.
Do not write Dify keys, tokens, or passwords into git / docs / agent_memory.

## Plaza/sidebar
一人多实例; unique title per user among non-archived (case-insensitive, no whitespace); card avatar/name/intro/mode/timestamps; sidebar capability_description + development notes + read-only single mode + knowledge panel; no model column; catalog supplies workflow/tool names and user_facing_summary. Chat click does not bump updated_at.

## Dify / tools
Keep ToolNode + DifyClient + catalog/binding. Do not wrap C's Dify as MCP.
v1 transport: POST /v1/workflows/run + DIFY_API_KEY, tool discover_douyin_leads, no_send=false.
DOUYIN_HTTP_* may be empty because C's workflow has defaults; /workflows/run does not apply console defaults, so the worker fills required missing fields.
Reserve agent_instance_workflows. Catalog stays code/config. Do not compile a graph per instance.

## Client
Vue frontend/ is the plaza module entry: /login, /agents, /agents/:agentInstanceId. Token in localStorage as Bearer. Create modal is two steps on the same route (douyin_ops only). Chat is center pane + read-only sidebar.
Streamlit remains a transitional client; do not delete it.
FastAPI Bearer JSON is the contract. Default CORS allows Streamlit 8501 and Vue 5173. Vite dev proxies /v1 to 8000 when VITE_API_BASE is empty.
Do not treat missing live Dify config as Vue delivery success.

## Knowledge
Per-instance vector retrieve inside chatbot; seed douyin_ops demo; optional search_kb as 补检索. Metadata table agent_knowledge_documents; chunks in Store namespace (user_id, agent_instance_id, "kb"). Production PostgresStore embedding index (pgvector).

## Data
Deployment B: server Postgres is source of truth. Do not ALTER LangGraph official tables.

## Plaza HTTP
查询 `GET /v1/agent-instances`、修改 `PATCH /v1/agent-instances/{id}`、删除 `DELETE /v1/agent-instances/{id}` 已有。删除是逻辑归档 `status=archived`，不物理删行。Vue 广场增查改删已接：卡片底栏编辑走 PATCH（新选图片才带 avatar），归档走自定义二次确认后 DELETE。对话页不改。

## Current Dify status contract (landed 2026-09-22)

- `app/dify_client.py` parses outer `dify_workflow_status` separately from DSL `job_status`/`job_response`; `job_response.data.status` or root `status` wins, and missing/unknown job state is `unverified`.
- `app/leads.py` returns `workflow_ok`, `delivery_ok`, `status`, `delivery`, `message_details`, `job_id`, `workflow_run_id`, and actual Dify errors. Only explicit per-item success is `sent`; list error objects never become records; `written` is local persistence only.
- Outer workflow `succeeded` cannot override inner `failed/error/cancelled/timeout`; `job_response` status has priority over the loop variable, no job state or unknown state never reports success. Dify errors use `error/reason/error_message/failure_reason/message` when present. The persisted workflow row maps user-visible `unverified` to existing database `failed` status.
- `app/prompts.py` instructs the assistant to report only `job_status` and explicit `delivery.*.sent`, never outer success or `written`, and to show Dify-provided `message_details`.
- Scope remains backend Dify parsing only. C's DSL, Vue, Streamlit, and phases 0–7 were not edited.
