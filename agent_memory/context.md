# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical next-upgrade doc: `docs/modify/抖音运营智能体修改设计方案（1）.md`.
Do not implement worker business code until that doc plus memory-bank pointers are the source of truth. Do not edit C's Dify.

## Client entry (locked in doc, under discussion)
登录 → `app_users` / `user_id` → 新建智能体 (`agent_instances`, `template_code=douyin_ops`) → 展示能力（只展示、不勾选）→ 用这个智能体 (`app_threads` with `user_id` + `agent_instance_id`) → `ainvoke(..., configurable={thread_id, user_id, agent_instance_id})`.
Doc v1: one active instance per user. Graph stays `START -> chatbot -> tools_condition -> tools -> chatbot`.

## Discussing (not locked)
User wants Yuanqi-like plaza + sidebar. Proposed product flow:
登录 → 新建智能体（一人可多个）→ 选模板（v1 only 抖音运营助手）→ 填名称/简介/头像（名称对当前用户唯一）→ 点卡片进对话。
Card: avatar, name, intro, mode (preset single), created_at / updated_at.
Sidebar: 应用描述=提示词; 应用开发要点; 应用设置 mode single|multi; 知识库板块但预设为空; 去掉模型栏; 显示 C 的 Dify 工作流名和工具名.
This conflicts with doc v1 "一人一实例" and "不建可编辑 agent_templates". Table discussion only; do not rewrite the modify doc until user confirms.

## Locked v1 Dify loop
- Unique contract: Dify app `douyin-lead-discovery` (Community `1.17.0`).
- Transport: **published workflow Service API key** (`POST /v1/workflows/run`) from the existing ToolNode. `difyctl` OAuth / `difyctl run` is retired (OpenAPI device-code 404; Explorer cannot open the install dir).
- `no_send=false` = real send at Dify's first `POST /v1/commands/run`. list-comment / list-message only fetch results.
- Do not dual-call C's CLI. Do not add MCP or a Dify graph node. Do not use `create_react_agent`.
- Config names: `DIFY_BASE_URL` (`http://192.168.1.158/v1`), `DIFY_API_KEY` (Service API, `.env` only), `DIFY_LEAD_APP_ID`, `DOUYIN_HTTP_BASE_URL`, `DOUYIN_HTTP_API_TOKEN`. Retired: `DIFYCTL_BIN`, `DIFY_COMMENT_APP_ID`, `DIFY_DM_APP_ID`.
- Tool args for the model: `account` (required), `keyword`/`video_id`, `limit`, `channels`, `list_status`. Server fills `base_url`, `api_token`, `no_send=false`, `auto_login`.
- Tell the user it will really send. Do not say draft-first.

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
- Confirm plaza/sidebar table delta before rewriting the modify doc
- When C publishes the app, creates the `app-` Service API key, and brings HTTP up
- Output JSON samples, job stop, account mapping, Feishu dual-send
- Supervisor mount later; auth UX later
