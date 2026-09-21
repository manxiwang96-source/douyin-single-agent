# Bugs and Risks

## Open
- FastAPI/Streamlit titles already say 抖音运营助手 after 阶段 0, but the graph still has no `discover_douyin_leads` and Streamlit is still the old unauthenticated chat entry until later phases.
- C HTTP (`DOUYIN_HTTP_BASE_URL` / `DOUYIN_HTTP_API_TOKEN`) is empty in local `.env`. User confirmed the Dify workflow has defaults and console runs succeed; worker still must omit empty HTTP fields instead of failing startup.
- Cancelling a worker job may not stop the Dify poll loop or C's async job. Local status can be cancelled while send already happened.
- Existing PROFILE_NAMESPACE / JOBS_NAMESPACE ("assistant", ...) is global and will leak across users until phase 3 lands `(user_id, agent_instance_id, "profile"|"kb")`.
- Existing POST /v1/threads has no user_id / agent_instance_id; the formal App three-step entry cannot use it as-is (phase 2 replaces this as product entry).
- Phone-off 08:00 jobs fail if job tables are ever moved to the client.
- Feishu bot and this worker might both true-send if run together; live phase 7 must stagger with C.
- `list_comment` / `list_message` / `snapshot` live JSON samples are still unconfirmed; phase 4 writeback is best-effort.
- ~/.codex/templates/agent_memory/ is still missing; files follow the existing three-file layout.
- Live ChatOpenAI against aitokens.website can exceed 20s; unrelated.
- Pre-existing dirty file docs/summary/个人超级助手总结与逻辑复盘（2）.md makes test_each_heading_starts_with_plain_language fail (## 0. heading without nearby 白话). Left untouched.
- difyctl auth login remains blocked on host OpenAPI 404. v1 no longer uses CLI OAuth; keep App API key and dfoa_ tokens unmixed.

## Closed
- Plaza/sidebar, 一人多实例, binding table, instance KB retrieve, and field-level schema are locked in docs/modify/抖音运营智能体修改设计方案（1）.md.
- Phased execution for a new conversation is locked in stage/README.md and stage/抖音运营智能体分阶段实施套餐.md. Deleted stage1/ is not a source.
- User confirmed douyin-lead-discovery is published and console-tested; local `.env` has DIFY_API_KEY / DIFY_BASE_URL (values must not be copied into docs or memory).
- v1 no longer assumes two tools or default --no-send; no_send=false is the locked true-send path.
- Comment/DM review is intentionally skipped in v1 after C confirmed real publish.
- Input variable names for douyin-lead-discovery were read from the start node.
- Dify version for this host is 1.17.0 Community.