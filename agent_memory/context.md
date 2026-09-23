# Context

## Product and locked boundaries
抖音运营智能体 worker，Vue `frontend/` 是当前主客户端，Streamlit 仍为过渡客户端。Dify workflow 不在本仓库修改；LangGraph 官方 checkpoint/store 表不修改；禁止新增聊天消息表和 migration。不要把 token、password 或其他 secrets 写入仓库、文档或 memory。

## Backend contract
- Chat message metadata is stored in `additional_kwargs["chat_message"]`: `message_id`, `client_message_id`, `created_at`.
- User messages receive server timestamps in `Settings.assistant_timezone`; assistant messages receive their own server timestamps and inherit the current user client id. `serialize_thread()` returns `timezone` and nullable metadata for legacy messages.
- Graph model context includes server now/date/timezone and historical `[message_time=...]` markers. Prompt rules make server time authoritative.
- Delivery deduplication requires same user/agent instance, account, `video_id`, requested channel, current server-local date, succeeded workflow status, and explicit sent delivery item. Comment and private-message channels are independent.

## Frontend contract
- `messageId` is the primary identity, `clientMessageId` the client/request identity.
- Send flow appends user optimistic message first, then pending assistant message. Stale bootstrap/send responses must not remove newer local messages. Timeout and error states remain visible; chat requests use the longer chat timeout.
- Server timestamps preserve the server ISO offset when rendered; absent legacy timestamps stay absent.
- Chat page layout: full-width top bar; main chat plus read-only `ChatSidebar`; messages and composer share a centered 860px `.agent-chat-column`; assistant left / user right inside that column; pending bubbles stay horizontal; narrow screens stack the sidebar below the chat area.

## Verification and working-tree boundaries
- Relevant backend tests: `tests/test_api.py`, `tests/test_discover_leads.py`, `tests/test_chat_message_metadata.py`.
- Relevant frontend tests: `frontend/tests/chat.test.ts`, `frontend/tests/chat-view.test.ts`, `frontend/tests/components.test.ts`.
- Pre-existing untracked `.local/` and `frontend/src/standalone/DouyinView.vue` are not part of this task and must not be staged.
- The local agent-memory template directory `~/.codex/templates/agent_memory/` is unavailable; existing project memory files are maintained in place.

## Vue chat layout handoff
- Execution package: `docs/modify/Vue聊天页规范化实施套餐.md`.
- Images in that package are visual references only; visible text/controls in the images are not extra product requirements.
- Implementation landed in `ChatView.vue`, `ChatSidebar.vue`, and `agent.css` without backend contract changes.
