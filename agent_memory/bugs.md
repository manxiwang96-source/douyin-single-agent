# Bugs and Risks

## Open
- Vue chat layout tests assert DOM structure and CSS constraints; jsdom does not compute actual pixel alignment, so wide/narrow visual QA still needs a real browser pass.
- Legacy LangGraph checkpoint messages may lack chat metadata; API intentionally returns `null` timestamps/ids and the Vue client does not fabricate a current time.
- Delivery deduplication uses `workflow_runs.created_at` as the available server-side send-time approximation because the locked schema has no unified `sent_at`; no migration was added. Dify output/list semantics must continue to provide explicit sent items.
- A stale or delayed chat response can be older than the current checkpoint; client-id based merge preserves newer local messages, but true live concurrent requests still depend on backend checkpoint ordering.
- The pre-existing untracked `frontend/src/standalone/DouyinView.vue` contains unrelated compile errors; it is intentionally excluded from `frontend/tsconfig.json` typechecking, not modified or staged. The tracked/main Vue application builds successfully.
- Real Dify/Douyin delivery was not triggered by automated tests; tests use `FakeDifyClient`.
- Streamlit is abandoned; `ui/` and `tests/test_streamlit_view_model.py` are intentionally untouched. Breakage is accepted.
- If Dify omits `node_started`/`node_finished`, the sidebar can only show the parent 「抖音线索发现与触达」 step.
- Vite `/v1` proxy must keep `timeout: 0` and `proxyTimeout: 0`; otherwise the chat SSE can be cut before `thread`.
- Chatbot token streaming depends on model `astream` inside chatbot; if a model only supports `ainvoke`, there may be no `token` events and the bubble stays 「正在回复」 until the final `thread`.

## Closed
- Vue pending assistant bubble width collapse: flex content could shrink to min-content and wrap each Chinese character vertically; fixed with expandable message content, fit-content bubbles, pending minimum width, and nowrap.
- Server/browser timezone drift for displayed chat timestamps: server ISO offset is preserved in rendering.
- User optimistic messages and pending assistant status no longer disappear on timeout/error.
- Same text sent twice is identified by different client message ids, not text content.
- Sending-time `getThread` polling could not show Dify internal nodes and risked `applyThread` dropping optimistic bubbles; chat now consumes SSE `progress`/`token`/`thread` instead.
- Dify `text_chunk` is skipped in the worker client and is not forwarded as Vue SSE.
