# Progress

## Current task
按 docs/modify/Vue聊天页流式输出与Dify节点进度实施套餐.md 把聊天 messages/resume 改成 SSE，并在右侧栏展示 Dify 节点进度。

## Status
已落地：聊天 SSE、Dify 节点进度、前后端测试与前端构建均通过。

## Landed
- messages/resume 成功路径只返回 `text/event-stream`，事件只有 `progress` / `token` / `thread` / `error`。
- Dify `response_mode=streaming`；节点通过 `on_event` + `get_stream_writer` 进入 custom 流，并写入 compact `workflow_nodes` 供回放。
- Vue 用 `fetch` + `AbortController` 消费 SSE；发送期不再 `getThread` 轮询；`phase=running` 丢掉提前 token。
- 侧栏 `dify_node` children：running 转圈 / done ✓ / failed ✕。

## Boundaries
- Streamlit 废弃，不要改 Streamlit。
- 不要修改同学 C 的 Dify，不要新增聊天消息表，不要改旧套餐文档。
- 不提交 .local/ 与 frontend/src/standalone/DouyinView.vue。
- 不要转发 Dify text_chunk；不要 EventSource。
- EventSourceResponse(..., ping=0)；每次 yield 新 dict。
- Jobs / morning brief 仍走 ainvoke。
