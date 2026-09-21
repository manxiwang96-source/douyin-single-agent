# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical next-upgrade doc: docs/modify/抖音运营智能体修改设计方案（1）.md.
User asked not to rewrite the modify doc until remaining technical logic is confirmed. Do not edit C's Dify.

## Plaza/sidebar (confirmed in talk, not in doc yet)
一人多实例; unique title per user (case-insensitive, no whitespace); card avatar/name/intro/mode/timestamps; sidebar capability copy + development notes + read-only mode + empty knowledge panel; no model column; catalog supplies workflow/tool names. Chat click does not bump updated_at.

## Dify / tools (confirmed in talk)
Keep ToolNode + DifyClient + catalog/binding. Do not wrap C's Dify as MCP.
v1 transport: POST /v1/workflows/run + DIFY_API_KEY, tool discover_douyin_leads, no_send=false.
Later more Dify workflows than douyin-lead-discovery. Users pick from our published catalog, not arbitrary App IDs/keys.
Reserve agent_instance_workflows now. Catalog stays code/config. Do not compile a graph per instance.
Recommended bind_tools: resolve bindings at HTTP/job entry, pass allowed_workflow_codes in configurable, chatbot bind_tools(subset), ToolNode keeps union, each Dify tool re-checks binding.
If supervisor later needs MCP, wrap this worker HTTP, not Dify.

## Data
Deployment B: server Postgres is source of truth. Do not ALTER LangGraph official tables.
Doc v1 tables: app_users, agent_instances, app_threads, douyin_accounts, job_definitions/job_runs, workflow_runs, engage_*, media_assets.
Talk extras not in doc: plaza fields on agent_instances, empty agent_knowledge_documents, binding table, Store namespace (user_id, agent_instance_id, profile).
workflow_runs is the generic Dify call ledger; engage_* is Douyin outreach only.

## Open
- Confirm bind_tools + binding-table shape before rewriting the modify doc
- C publish + Service API key + HTTP up
- Supervisor mount later