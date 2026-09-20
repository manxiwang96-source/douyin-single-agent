# Bugs and Risks

## Open
- Classmate C input variable names, App IDs, and Dify version are unknown; workflow inputs stay JSONB until the contract arrives.
- Cancelling a run while Dify is still scanning may not kill the subprocess; the design records `cancelled` and ignores later writes.
- Existing `PROFILE_NAMESPACE` / `JOBS_NAMESPACE` (`"assistant", ...`) is global and will leak across users when multi-user lands.
- Phone-off 08:00 jobs fail if job tables are ever moved to the client.
- `~/.codex/templates/agent_memory/` is still missing; files follow the existing three-file layout.
- Live ChatOpenAI against aitokens.website can exceed 20s; unrelated to this documentation change.
- Pre-existing dirty file `docs/summary/个人超级助手总结与逻辑复盘（2）.md` makes `test_each_heading_starts_with_plain_language` fail (`## 0.` heading without nearby `人话`). Not part of this Douyin design delivery; left untouched.

## Closed
- Discussion-only phase is closed: the Douyin redesign is now a locked modify doc, not just chat notes.