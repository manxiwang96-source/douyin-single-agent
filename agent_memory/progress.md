# Progress

## Current task
已完成 Vue 聊天页规范化：统一主聊天内容列、消息左右对齐、输入框与消息同列，并规范只读侧栏。

## Completed
- `frontend/src/views/ChatView.vue`：顶栏全宽；主区与侧栏分栏；消息列表和输入框放入居中 `.agent-chat-column`。
- `frontend/src/styles/agent.css`：内容列最大宽度 860px；用户消息在列内右对齐，助手消息左对齐；pending 保持横向最小宽度；长文本与侧栏可换行；窄屏侧栏下移。
- `frontend/src/components/ChatSidebar.vue`：保留只读字段，空数据使用友好占位。
- `frontend/tests/chat-view.test.ts`、`frontend/tests/components.test.ts`：补充布局、对齐、溢出和空占位回归。
- 未改后端 API、数据库、migration 或聊天状态机。

## Verification
- 前端定向测试：`tests/chat-view.test.ts`、`tests/components.test.ts`、`tests/chat.test.ts` 通过。
- 前端完整测试：38 passed。
- 前端构建：`npm run build` 通过。
- 后端测试：`pytest -q` 通过（205 passed, 6 skipped）。

## Commit
- 规范 Vue 聊天页布局与侧边栏
