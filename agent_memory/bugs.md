# Bugs and Risks

## Open
- Vue chat layout tests assert DOM structure and CSS constraints; jsdom does not compute actual pixel alignment, so wide/narrow visual QA still needs a real browser pass.
- Legacy LangGraph checkpoint messages may lack chat metadata; API intentionally returns `null` timestamps/ids and the Vue client does not fabricate a current time.
- Delivery deduplication uses `workflow_runs.created_at` as the available server-side send-time approximation because the locked schema has no unified `sent_at`; no migration was added. Dify output/list semantics must continue to provide explicit sent items.
- A stale or delayed chat response can be older than the current checkpoint; client-id based merge preserves newer local messages, but true live concurrent requests still depend on backend checkpoint ordering.
- The pre-existing untracked `frontend/src/standalone/DouyinView.vue` contains unrelated compile errors; it is intentionally excluded from `frontend/tsconfig.json` typechecking, not modified or staged. The tracked/main Vue application builds successfully.
- Real Dify/Douyin delivery was not triggered by automated tests; tests use `FakeDifyClient`.
- Before the first LangGraph tool checkpoint, the sidebar can only show the client-local 「正在思考」 step because blocking `ainvoke` does not emit node-level events.
- Task-bar polling must never call `applyThread`; doing so would drop optimistic user/pending bubbles. Skip is frozen locally so a later composing snapshot cannot reopen the round.
- Dify internal workflow nodes remain invisible by product rule; only the ToolNode label 「抖音线索发现与触达」 is shown.

## Closed
- Vue pending assistant bubble width collapse: flex content could shrink to min-content and wrap each Chinese character vertically; fixed with expandable message content, fit-content bubbles, pending minimum width, and nowrap.
- Server/browser timezone drift for displayed chat timestamps: server ISO offset is preserved in rendering.
- User optimistic messages and pending assistant status no longer disappear on timeout/error.
- Same text sent twice is identified by different client message ids, not text content.
