# Bugs and Risks

## Open
- Legacy LangGraph checkpoint messages may lack chat metadata; API intentionally returns `null` timestamps/ids and the Vue client does not fabricate a current time.
- Delivery deduplication uses `workflow_runs.created_at` as the available server-side send-time approximation because the locked schema has no unified `sent_at`; no migration was added. Dify output/list semantics must continue to provide explicit sent items.
- A stale or delayed chat response can be older than the current checkpoint; client-id based merge preserves newer local messages, but true live concurrent requests still depend on backend checkpoint ordering.
- The pre-existing untracked `frontend/src/standalone/DouyinView.vue` contains unrelated compile errors; it is intentionally excluded from `frontend/tsconfig.json` typechecking, not modified or staged. The tracked/main Vue application builds successfully.
- Real Dify/Douyin delivery was not triggered by automated tests; tests use `FakeDifyClient`.

## Closed
- Server/browser timezone drift for displayed chat timestamps: server ISO offset is preserved in rendering.
- User optimistic messages and pending assistant status no longer disappear on timeout/error.
- Same text sent twice is identified by different client message ids, not text content.
