# Design Document

> 当前目标是抖音运营智能体，不是继续改个人超级助理。产品锁定：`docs/modify/抖音运营智能体修改设计方案（1）.md`。执行切分：`stage/README.md` 与 `stage/抖音运营智能体分阶段实施套餐.md`。v1 模板只有 `douyin_ops`；工具 `discover_douyin_leads` 调 Dify `douyin-lead-discovery`（`POST /v1/workflows/run` + `DIFY_API_KEY`，`no_send=false` 真发，评论/私信不审；`difyctl` 不再采用）。`DIFY_LIVE_ENABLED` 默认 false，阶段 0–6 只 mock。阶段 0 已改文档与配置。阶段 1 已建业务表与仓库，仍不调 Dify、不接登录广场。本文仍描述当前已落地的个人超级助理运行时，避免和现网图脱节。
## Scope
Personal super assistant on the existing Xiaohongshu MVP. One graph, one product identity. Users chat in Streamlit; the same assistant can answer daily questions, remember facts, fetch weekday/weather via FastMCP, send SMTP email, and only write Xiaohongshu notes or generate media when the user explicitly asks.

v1 must run immediately (do not wait for 08:00): real MCP weekday + Guangzhou weather/temperature, model-written 2-4 situational suggestions, and a real 163 email.

## Non-goals
- `create_react_agent`, Supervisor, or a separate Xiaohongshu agent
- Copying langgraph.com.cn examples (MCP streamable-http weather demo, Platform Cron, custom routing)
- Xiaohongshu login or publish
- pgvector / migrating `data/checkpoints.sqlite`
- Silent SQLite fallback when Postgres is down
- Committing secrets (SMTP auth code, DB password) to git or memory-bank

## User journeys
1. Daily chat: natural language. No note template, no `search_kb` unless Xiaohongshu copy is requested.
2. Explicit Xiaohongshu note: `search_kb` then 【标题】【正文】【标签】.
3. Explicit image/video: existing HITL `interrupt()` inside `generate_image` / `generate_video`.
4. Morning brief: MCP facts -> same graph `ainvoke` suggestions -> `send_email`. Fallback still emails the facts if the model did not send, including when `ainvoke` times out.
5. Hydration reminders 10/12/14/16/18/20/22: template email, no LLM. 08:00 is merged into the morning brief.
6. Manual verify: `run_morning_brief()`, `run_hydrate(slot)`, `POST /v1/assistant/jobs/run`.

## State and memory
- Graph state: MessagesState + `last_image_path` / `last_video_path`.
- Thread short-term: production `PostgresSaver`; tests `InMemorySaver`.
- Cross-thread long-term: production `PostgresStore`; tests in-memory store. Namespaces: `("assistant", "profile")` facts, `("assistant", "jobs")` idempotency.
- KB RAG stays process-local `InMemoryStore` + bge-m3. No pgvector.

## Graph
START -> chatbot -> tools_condition -> tools -> chatbot
Nodes remain only `chatbot` and `tools`. MCP tools, `send_email`, and memory tools join the existing ToolNode. `parallel_tool_calls=False`. FastAPI message/resume uses `ainvoke`.

## API contract
Keep `/health`, `/v1/config`, `/v1/threads*`, `/v1/media/*`.
Add `POST /v1/assistant/jobs/run` with `kind=morning_brief|hydrate`.

## Configuration
Local `.env` only for secrets. New names: `POSTGRES_URI`, `ASSISTANT_CITY`, `ASSISTANT_TIMEZONE`, `SCHEDULER_ENABLED`, `SMTP_*`. Production start fails if Postgres or SMTP is missing.

## Acceptance
- Default pytest: fully mocked, no Postgres/SMTP/Open-Meteo, graph nodes unchanged, prompt identity is personal assistant, jobs ignore wall-clock for morning brief, 08:00 hydrate does not double-send.
- `RUN_LIVE_ASSISTANT=1`: immediately run morning brief; real MCP weekday/weather/temp; real 163 email. This is the delivery gate.
- Existing `RUN_LIVE_API=1` cheapest smokes remain, not the upgrade success definition.

## Framework references (read only, do not paste)
- https://langgraph.com.cn/agents/mcp/index.html
- https://langgraph.com.cn/reference/mcp/index.html
- https://langgraph.com.cn/concepts/memory.1.html
- https://langgraph.com.cn/how-tos/persistence.1.html
- https://langgraph.com.cn/concepts/persistence.1.html
- https://langgraph.com.cn/agents/context/index.html
