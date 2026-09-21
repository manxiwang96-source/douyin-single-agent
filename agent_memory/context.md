# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical next-upgrade doc: docs/modify/抖音运营智能体修改设计方案（1）.md.
Do not implement worker business code until that doc plus memory-bank pointers are the source of truth. Do not edit C's Dify.
User asked not to rewrite the modify doc until remaining technical logic is confirmed.

## Client entry (locked in doc, under discussion)
登录 -> app_users / user_id -> 新建智能体 (agent_instances, template_code=douyin_ops) -> 展示厅（只展示，不勾选） -> 开始新对话 (app_threads with user_id + agent_instance_id) -> ainvoke(..., configurable={thread_id, user_id, agent_instance_id}).
Doc v1: one active instance per user. Graph stays START -> chatbot -> tools_condition -> tools -> chatbot.

## Plaza/sidebar (confirmed in talk, not in doc yet)
登录 -> 新建智能体（一人可多个）-> 选模板（v1 only 抖音运营助手）-> 填名称/简介/头像（名称当前用户唯一）-> 点卡片进对话。
Card: avatar, name, intro, mode (preset single), created_at / updated_at.
Sidebar: 应用描述=能力文案; 应用开发要点; 应用设置 mode single|multi read-only; 知识库板块预设为空; 去掉模型栏; 显示 C 的 Dify 工作流名称和工具名.
Clicking chat does not update updated_at.

## Locked v1 Dify loop
- Unique contract: Dify app douyin-lead-discovery (Community 1.17.0).
- Transport: published workflow Service API key (POST /v1/workflows/run) from the existing ToolNode. difyctl OAuth / difyctl run is retired.
- no_send=false = real send at Dify's first POST /v1/commands/run.
- Do not dual-call C's CLI. Do not add MCP or a Dify graph node. Do not use create_react_agent.
- Config names: DIFY_BASE_URL, DIFY_API_KEY, DIFY_LEAD_APP_ID, DOUYIN_HTTP_BASE_URL, DOUYIN_HTTP_API_TOKEN.
- Tool args for the model: account (required), keyword/video_id, limit, channels, list_status. Server fills base_url, api_token, no_send=false, auto_login.

## Custom agents / Dify (discussing)
Keep ToolNode + DifyClient + catalog/binding. Do not wrap C's Dify as MCP.
Preset auto-binds douyin-lead-discovery. Later custom agents pick from our published catalog, not arbitrary App IDs/keys.
Do not compile a new graph per instance. Dynamic subset via bind_tools at request time, with authorization inside the tool.
If supervisor later needs MCP, wrap this worker's HTTP, not Dify. Secrets stay server-filled.
Existing MCP is weather/datetime stdio (mcp_servers/personal.py) and already joins the same ToolNode via extra_tools.

## Data and HITL
- Deployment B: server Postgres is source of truth; client is cache only.
- App tables carry user_id. Conversation/job/engage/media/Douyin-account rows also carry agent_instance_id. Do not ALTER LangGraph official tables.
- HITL columns stay; v1 Douyin outreach uses require_approval=false.
- workflow_runs: one row per POST /v1/workflows/run.

## Open
- Confirm ToolNode vs MCP recommendation before rewriting the modify doc
- When C publishes the app, creates the app- Service API key, and brings HTTP up
- Output JSON samples, job stop, account mapping, Feishu dual-send
- Supervisor mount later; auth UX later