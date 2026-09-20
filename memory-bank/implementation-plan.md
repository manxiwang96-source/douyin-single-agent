# Implementation Plan

Each step is independently verifiable. Do not paste langgraph.com.cn samples. Secrets stay in local `.env`.

1. Update `memory-bank/design-document.md`, `tech-stack.md`, and this plan with locked identity, Postgres/MCP/email/scheduler decisions, and reference-only links.
   Validate: docs mention `chatbot`/`tools`, `PostgresSaver`, FastMCP, `RUN_LIVE_ASSISTANT=1`, and "只参考，不整段复制".

2. Extend Settings and `.env.example` with `POSTGRES_URI`, `ASSISTANT_CITY`, `ASSISTANT_TIMEZONE`, `SCHEDULER_ENABLED`, SMTP fields. Add requirements: `langchain-mcp-adapters`, `mcp`, `psycopg[binary,pool]`, `langgraph-checkpoint-postgres`, `apscheduler`. Do not overwrite existing `.env` secrets.
   Validate: `tests/test_config.py` covers defaults, production-required fields, and no secrets in example files.

3. Production `PostgresSaver` + `PostgresStore` with `setup()` and `compile(checkpointer=..., store=...)`. Create database if missing; fail if Postgres is unavailable. Tests keep `InMemorySaver`. Add `remember_fact` / `recall_facts` against the long-term store. KB stays `InMemoryStore`.
   Validate: mocked tests never open real Postgres; runtime test path still uses in-memory checkpointer.

4. Add `mcp_servers/personal.py` FastMCP stdio tools for weekday/datetime and city weather/temperature (Open-Meteo, default 广州). Load via `MultiServerMCPClient.get_tools()` into existing `build_tools()` / ToolNode. Do not add graph nodes.
   Validate: MCP unit tests mock HTTP; graph nodes remain only `chatbot` and `tools`.

5. Add `send_email`, `run_morning_brief()`, `run_hydrate(slot)`, and `POST /v1/assistant/jobs/run`. Morning brief: MCP facts + same-graph suggestions + email, with facts fallback. Hydrate 08:00 merged; other slots template-only.
   Validate: morning brief ignores wall-clock; 08:00 hydrate does not send a second mail; hydrate does not call the LLM.

6. Register APScheduler in FastAPI lifespan when `SCHEDULER_ENABLED=true`. Tests set `scheduler_enabled=False`. Startup catch-up: morning brief if now >= 08:00; hydrate only the current slot; no catch-up after 22:00. Job keys in store namespace `("assistant", "jobs")`.
   Validate: default pytest does not start a live scheduler or send mail.

7. Switch FastAPI message/resume to `ainvoke`. Rewrite `SYSTEM_PROMPT` and Streamlit/FastAPI titles to 个人超级助理. Xiaohongshu format and `search_kb` only when explicitly requested.
   Validate: prompt/UI tests; existing HITL and API contract tests stay green.

8. Default `pytest` fully mocked and green. Then `RUN_LIVE_ASSISTANT=1 tests/test_live_assistant.py`: immediately run morning brief, real MCP weekday/weather/temp, real 163 email. Missing live config must skip with a reason; that skip is not delivery success.

9. After the milestone, update `memory-bank/architecture.md`, `memory-bank/progress.md`, and `agent_memory/*`.

## Next upgrade

Stop following the assistant-upgrade steps above for new work. The locked Douyin worker redesign is `docs/modify/抖音运营智能体修改设计方案（1）.md`. Implement in the order listed there: one Dify tool over HTTP `POST /v1/workflows/run` + `DIFY_API_KEY` (not `difyctl`), true-send (`no_send=false`), no comment/DM review API, job tables first. Do not start Dify/job business code before that doc is the source of truth.
