# Bugs and Risks

## Open
- `difyctl auth login` remains blocked on host OpenAPI 404, but login is paused: v1 closed loop will try the workflow Service API key instead. Last inspect: `douyin-lead-discovery` unpublished, no API keys yet. App API key != `difyctl` `dfoa_` token; do not mix them.
- User CMD vs PowerShell: `$env:PATH=...` in CMD yields 文件名、目录名或卷标语法不正确. Prefer the full exe path or `set "PATH=C:\Users\86153\AppData\Local\difyctl\bin;%PATH%"`. Shim no longer depends on `%LOCALAPPDATA%`.
- `douyin-lead-discovery` is still draft-only (0 published versions, no API keys). `difyctl run` / Service API cannot live-run until C publishes.
- C HTTP (`base_url`) was not reachable from this machine when inspected; treat backend reachability as unconfirmed.
- Cancelling a worker job may not stop the Dify poll loop or C's async job. Local status can be `cancelled` while send already happened.
- Existing `PROFILE_NAMESPACE` / `JOBS_NAMESPACE` (`"assistant", ...`) is global and will leak across users when multi-user lands.
- Existing `POST /v1/threads` has no `user_id` / `agent_instance_id`; the formal App three-step entry cannot use it as-is.
- Phone-off 08:00 jobs fail if job tables are ever moved to the client.
- Feishu bot and this worker might both send if run together; still needs C confirmation.
- `~/.codex/templates/agent_memory/` is still missing; files follow the existing three-file layout.
- Live ChatOpenAI against aitokens.website can exceed 20s; unrelated.
- Pre-existing dirty file `docs/summary/个人超级助手总结与逻辑复盘（2）.md` makes `test_each_heading_starts_with_plain_language` fail (`## 0.` heading without nearby `人话`). Left untouched.
- A fresh GitHub re-download of the 112MB Windows binary was slow/partial and was not required after SHA-256 already matched the installed copy.

## Closed
- Input variable names for `douyin-lead-discovery` were read from the draft start node.
- Dify version for this host is 1.17.0 Community.
- v1 no longer assumes two tools or default `--no-send`; `no_send=false` is the locked true-send path, not a HITL bug.
- Comment/DM review is intentionally skipped in v1 after C confirmed real publish.
- Matching `difyctl` for Dify `1.17.0` is installed locally (`0.2.0-alpha`, official Windows x64 asset).
