# Context

## Product
抖音运营智能体. This repo is one worker the supervisor will later schedule. Independently runnable. Not the supervisor, not classmate C's Dify.

## Locked design
Canonical next-upgrade doc: `docs/modify/抖音运营智能体修改设计方案（1）.md`.
Do not implement business code until that doc plus memory-bank pointers are the source of truth.

## Locked constraints
- Graph nodes stay `chatbot` and `tools` only. No Supervisor, no `create_react_agent`, no Dify graph node, no new MCP server wrapping Dify.
- Call C's Dify via `difyctl` adapter + two tools in the existing ToolNode: `reply_douyin_comment`, `send_douyin_dm`.
- Deployment B: shared locally deployed server. Client app is cache only. Do not shard Postgres onto phones.
- HITL tables now. Default `require_approval=true`. Chat media HITL stays `interrupt()`. Outbound comment/DM HITL is a table queue.
- Job tables now, including `cancelled`. Users can cancel from the client or from chat. Douyin 08:00 implementation can wait.
- App tables carry `user_id`. Do not ALTER LangGraph official tables. Store namespace becomes `(user_id, "profile")`.
- C owns operational scrape/login/send/confirm. This worker stores selected videos + proposed-or-later comments/DMs.

## Open
- C workflow input names, App IDs, Dify version
- Supervisor mount later
- Auth UX later (columns only)