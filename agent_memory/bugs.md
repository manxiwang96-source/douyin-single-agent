# Bugs and Risks

## Open
- `douyin-lead-discovery` is draft-only (0 published versions, no API keys). `difyctl run` / Service API cannot be the current v1 path until C publishes.
- Start variable `no_send` defaults to `"false"` while the app description says scan-only. Calling the workflow without forcing `no_send=true` can send during discovery and break HITL.
- This Dify app has no send/DM nodes. Two tools `reply_douyin_comment` / `send_douyin_dm` cannot both be satisfied by this one App.
- Dify is an extra hop: LangGraph → Dify → C HTTP (`192.168.1.33:8765`) → likely CLI/browser. Probe from this machine to that HTTP port did not return in time; treat backend reachability as unconfirmed.
- Cancelling a worker job may not stop the Dify poll loop or C's async job.
- Existing `PROFILE_NAMESPACE` / `JOBS_NAMESPACE` (`"assistant", ...`) is global and will leak across users when multi-user lands.
- Existing `POST /v1/threads` has no `user_id` / `agent_instance_id`; the formal App three-step entry cannot use it as-is.
- Phone-off 08:00 jobs fail if job tables are ever moved to the client.
- `~/.codex/templates/agent_memory/` is still missing; files follow the existing three-file layout.
- Live ChatOpenAI against aitokens.website can exceed 20s; unrelated.
- Pre-existing dirty file `docs/summary/个人超级助手总结与逻辑复盘（2）.md` makes `test_each_heading_starts_with_plain_language` fail (`## 0.` heading without nearby `人话`). Left untouched.

## Closed
- Input variable names for `douyin-lead-discovery` are no longer unknown; they were read from the draft start node.
- Dify version for this host is 1.17.0 Community.
