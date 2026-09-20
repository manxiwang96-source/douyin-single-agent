# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical next-upgrade doc: `docs/modify/抖音运营智能体修改设计方案（1）.md`.
Do not implement business code until that doc plus memory-bank pointers are the source of truth.

## Client entry
登录 → `app_users` / `user_id` → 新建智能体 (`agent_instances`, `template_code=douyin_ops`) → 展示能力（只展示、不勾选）→ 用这个智能体 (`app_threads` with `user_id` + `agent_instance_id`) → `ainvoke(..., configurable={thread_id, user_id, agent_instance_id})`.
v1: one active instance per user. Graph stays `START -> chatbot -> tools_condition -> tools -> chatbot`.

## Locked constraints
- Graph nodes stay `chatbot` and `tools` only. No Supervisor, no `create_react_agent`, no Dify graph node, no new MCP server wrapping Dify.
- Call C's Dify via `difyctl` adapter + two tools in the existing ToolNode: `reply_douyin_comment`, `send_douyin_dm`.
- Deployment B: shared locally deployed server. Client app is cache only. Do not shard Postgres onto phones. `agent_instances` lives on server Postgres.
- HITL tables now. Default `require_approval=true`. Chat media HITL stays `interrupt()`. Outbound comment/DM HITL is a table queue.
- Job tables now, including `cancelled`. Users can cancel from the client or from chat. Douyin 08:00 implementation can wait.
- App tables carry `user_id`. Conversation/job/engage/media/Douyin-account rows also carry `agent_instance_id`. Do not ALTER LangGraph official tables. Store namespace becomes `(user_id, "profile")`.
- C owns operational scrape/login/send/confirm. This worker stores selected videos + proposed-or-later comments/DMs.

## Inspected Dify (read-only, 2026-09-20)
- Host: `http://192.168.1.158`, Community `1.17.0`. Do not write console passwords or tokens into git/docs.
- Target app `douyin-lead-discovery` id `66d7b877-12a7-4ba2-b6cc-7b7b2b19795e`, mode=workflow.
- It is an HTTP orchestrator over C's service (`base_url` default `http://192.168.1.33:8765`): POST `/v1/commands/run` (async) → poll GET `/v1/jobs/{job_id}` (loop 40, sleep 3s) → GET `/v1/snapshot` → POST `/v1/commands/list` comment + message.
- Inputs: `base_url`, `api_token`, `account`, `video_id`, `keyword`, `limit`, `channels`, `no_send`, `auto_login`, `list_status`.
- Outputs: `job_id`, `run_response`, `job_status`, `job_response`, `snapshot`, `list_comment`, `list_message`.
- No send/message nodes. No other Douyin comment/DM send app in this workspace.
- Draft only: published_count=0, `workflow` id empty, `tool_published=false`, api-keys empty. `enable_api=true` but not runnable via `difyctl`/Service API until published.
- Description says default scan-only; start variable `no_send` default is `"false"`. HITL-unsafe if called without override.
- Other apps: `capability-execute` (published), `douyin-script-generation` (draft HTTP orchestrator for generate/edit/publish), two `test` apps. Not this worker's comment/DM path.

## Open
- v1 unique contract: Dify / C CLI / C HTTP. Do not dual-call.
- Whether C will publish `douyin-lead-discovery`, add a send workflow, and fix `no_send` default.
- Whether `/v1/commands/send` (or CLI `send`/`message`) is the send path.
- Whether `192.168.1.33:8765` is the live C HTTP from the worker host.
- Supervisor mount later
- Auth UX later (columns only)
- Multiple agent instances and capability checkboxes later
