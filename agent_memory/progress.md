# Progress

## Current task
修复 Vue 聊天框待回复气泡宽度塌缩：确保“正在回复”和加载点横向显示，消息内容区域可正常伸展。

## Completed implementation
- `frontend/src/styles/agent.css`：让消息内容 flex 项可伸展，普通气泡按内容宽度显示并受父容器约束；pending 气泡增加最小宽度并禁止逐字换行。
- `frontend/tests/chat-view.test.ts`：增加待回复气泡布局回归测试，校验消息内容 flex 能力、气泡宽度策略和 pending 文本不换行 CSS 契约。

## Verification status
- 前端定向测试：`npm test -- --run tests/chat-view.test.ts`，8 tests passed。
- 前端完整测试：`npm test -- --run`，35 tests passed。
- 前端构建：`npm run build`，成功。

## Commit
- 本次 CSS 与测试修复已提交，提交描述为“修复聊天框待回复气泡布局”。
