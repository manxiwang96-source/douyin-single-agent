# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical next-upgrade doc: `docs/modify/抖音运营智能体修改设计方案（1）.md`.
Do not implement worker business code until that doc plus memory-bank pointers are the source of truth. Do not edit C's Dify.

## Client entry
登录 → `app_users` / `user_id` → 新建智能体 (`agent_instances`, `template_code=douyin_ops`) → 展示能力（只展示、不勾选）→ 用这个智能体 (`app_threads` with `user_id` + `agent_instance_id`) → `ainvoke(..., configurable={thread_id, user_id, agent_instance_id})`.
v1: one active instance per user. Graph stays `START -> chatbot -> tools_condition -> tools -> chatbot`.

## Locked v1 Dify loop
- Unique contract: Dify app `douyin-lead-discovery` (Community `1.17.0`).
- Transport: **published workflow Service API key** (`POST /v1/workflows/run`) from the existing ToolNode. `difyctl` OAuth / `difyctl run` is retired (OpenAPI device-code 404; Explorer cannot open the install dir).
- `no_send=false` = real send at Dify's first `POST /v1/commands/run`. list-comment / list-message only fetch results.
- Do not dual-call C's CLI. Do not add MCP or a Dify graph node. Do not use `create_react_agent`.
- Config names: `DIFY_BASE_URL` (`http://192.168.1.158/v1`), `DIFY_API_KEY` (Service API, `.env` only), `DIFY_LEAD_APP_ID`, `DOUYIN_HTTP_BASE_URL`, `DOUYIN_HTTP_API_TOKEN`. Retired: `DIFYCTL_BIN`, `DIFY_COMMENT_APP_ID`, `DIFY_DM_APP_ID`.
- Tool args for the model: `account` (required), `keyword`/`video_id`, `limit`, `channels`, `list_status`. Server fills `base_url`, `api_token`, `no_send=false`, `auto_login`.
- Tell the user it will really send. Do not say draft-first.

## Local difyctl (retired, keep path notes)
- Binary still exists at `C:\Users\86153\AppData\Local\difyctl\bin\difyctl.exe` (`0.2.0-alpha`, Dify 1.16–1.17) but is **not** the v1 runtime path.
- Do not keep installing or logging in. Closed loop: C publishes + API key. Do not write console passwords, API keys, or tokens into git/docs.

## Data and HITL
- Deployment B: server Postgres is source of truth; client is cache only.
- App tables carry `user_id`. Conversation/job/engage/media/Douyin-account rows also carry `agent_instance_id`. Do not ALTER LangGraph official tables.
- HITL columns stay (`proposed` / `ready_to_send` / `approved_reply` / `require_approval`). v1 Douyin outreach uses `require_approval=false` and no pending-review API. Media HITL stays `interrupt()`.
- Job tables now, including `cancelled`. Users can cancel from the client or from chat. In-progress cancel marks local `cancelled` but may not stop Dify/C already sending. `sent` is not withdrawn.
- `workflow_runs`: one row per `POST /v1/workflows/run`. Dedup short-window same `account+keyword+video_id`.

## Inspected Dify (read-only)
- Host `http://192.168.1.158`, Community `1.17.0`. Never write console passwords or tokens into git/docs.
- App is draft: published_count=0, no API keys, `tool_published=false`. C HTTP not up. Live true-send is blocked until publish + HTTP.
- Inputs/outputs are listed in the modify doc section 6.3.

## Open
- When C publishes the app, creates the `app-` Service API key, and brings HTTP up
- Output JSON samples, job stop, account mapping, Feishu dual-send
- Supervisor mount later; auth UX later; multiple agent instances later
