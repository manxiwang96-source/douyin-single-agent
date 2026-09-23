# Context

## Product and locked boundaries
抖音运营智能体 worker。Vue `frontend/` 是当前主客户端。Streamlit 废弃：不改、不删、不做 SSE 兼容。Dify workflow 不在本仓库修改；LangGraph 官方 checkpoint/store 表不修改；禁止新增聊天消息表和 migration。不要把 token、password 或其他 secrets 写入仓库、文档或 memory。

## Backend contract
- Chat message metadata is stored in `additional_kwargs["chat_message"]`: `message_id`, `client_message_id`, `created_at`.
- User messages receive server timestamps in `Settings.assistant_timezone`; assistant messages receive their own server timestamps and inherit the current user client id. `serialize_thread()` returns `timezone` and nullable metadata for legacy messages.
- Graph model context includes server now/date/timezone and historical `[message_time=...]` markers. Prompt rules make server time authoritative.
- Delivery deduplication requires same user/agent instance, account, `video_id`, requested channel, current server-local date, succeeded workflow status, and explicit sent delivery item. Comment and private-message channels are independent.
- Thread JSON includes derived `progress` (`round_id`, `phase`, `steps`). Bubble filtering is unchanged: tool calls stay hidden and media still attaches to assistant bubbles. `discover_douyin_leads` steps may include nested `kind=dify_node` children; GET thread replays them from compact `workflow_nodes`.
- Chat POST `/messages` and `/resume` success path is SSE only: events `progress` / `token` / `thread` / `error`. Precheck 401/404/409 remain JSON. No parallel JSON chat endpoint and no Accept negotiation.
- Dify uses `response_mode=streaming`. Skip `ping`/`text_chunk`; do not forward Dify `text_chunk` as Vue SSE. Fail closed without `workflow_finished`. Jobs / morning brief still `ainvoke`.

## Frontend contract
- `messageId` is the primary identity, `clientMessageId` the client/request identity.
- Send flow appends user optimistic message first, then pending assistant message. Stale bootstrap/send responses must not remove newer local messages. Timeout and error states remain visible; chat requests use `CHAT_TIMEOUT_MS`.
- Server timestamps preserve the server ISO offset when rendered; absent legacy timestamps stay absent.
- Chat page layout: full-width top bar; main chat plus read-only `ChatSidebar`; messages and composer share a centered 860px `.agent-chat-column` inside the main pane; assistant left / user right inside that column; pending bubbles stay horizontal; desktop sidebar is 400px; narrow screens stack the sidebar below the chat area.
- Right sidebar is viewport-fixed. The top "当前任务" box and catalog below it scroll independently.
- Chat send/resume uses `fetch` + `AbortController`, not EventSource. Sending no longer polls `getThread`. `progress` updates the task bar; `token` appends pending text; `phase=running` drops early tokens and restores 「正在回复」; `thread` then `applyThread`. Do not `applyThread` live progress snapshots onto bubbles.

## Verification and working-tree boundaries
- Relevant backend tests: `tests/test_api.py`, `tests/test_serialize_progress.py`, `tests/test_dify_client.py`, `tests/test_chat_sse.py`, plus existing HITL/media/jobs tests.
- Relevant frontend tests: `frontend/tests/chat.test.ts`, `frontend/tests/chat-view.test.ts`, `frontend/tests/components.test.ts`, `frontend/tests/http.test.ts`.
- Pre-existing untracked `.local/` and `frontend/src/standalone/DouyinView.vue` are not part of this task and must not be staged.
- The local agent-memory template directory `~/.codex/templates/agent_memory/` is unavailable; existing project memory files are maintained in place.

## Vue chat streaming playbook
- Execution package: `docs/modify/Vue聊天页流式输出与Dify节点进度实施套餐.md`.
- Old package `docs/modify/Vue聊天页本轮任务流程实施套餐.md` still describes the landed sidebar, but its "不要上 SSE" rule is superseded. Do not edit that old file.
