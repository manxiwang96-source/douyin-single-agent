# Progress

## Current task
按 `docs/modify/Vue聊天页流式输出与Dify节点进度实施套餐.md` 把聊天 messages/resume 改成 SSE，并在右侧栏展示 Dify 节点进度。

## Status
手册与文档测试已落地。代码尚未改：`_arun` 仍是 `ainvoke`，Dify 仍是 `response_mode=blocking`，Vue 仍用 axios JSON + 发送期 `getThread` 轮询。

## Boundaries
- Streamlit 废弃，不要改 Streamlit。
- 不要修改同学 C 的 Dify，不要新增聊天消息表，不要改旧套餐文档。
- 不提交 `.local/` 与 `frontend/src/standalone/DouyinView.vue`。