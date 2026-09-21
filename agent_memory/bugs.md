# Bugs and Risks

## Open
- Streamlit v1 没有任务取消页；取消仍走阶段 5 的 HTTP/工具。
- C HTTP (`DOUYIN_HTTP_BASE_URL` / `DOUYIN_HTTP_API_TOKEN`) is empty in local `.env`. User confirmed the Dify workflow has defaults and console runs succeed; worker still must omit empty HTTP fields instead of failing startup.
- Cancelling a worker job may not stop the Dify poll loop or C's async job. Local status can be cancelled while send already happened.
- Morning-brief JOBS_NAMESPACE ("assistant", "jobs") remains global; conversation profile/KB/media are isolated as of phase 3.
- Phone-off 08:00 jobs fail if job tables are ever moved to the client.
- Feishu bot and this worker might both true-send if run together; live phase 7 must stagger with C.
- `list_comment` / `list_message` / `snapshot` live JSON samples are still unconfirmed; phase 4 writeback is best-effort.
- ~/.codex/templates/agent_memory/ is still missing; files follow the existing three-file layout.
- Live ChatOpenAI against aitokens.website can exceed 20s; unrelated.
- Pre-existing dirty file docs/summary/个人超级助手总结与逻辑复盘（2）.md makes test_each_heading_starts_with_plain_language fail (## 0. heading without nearby 白话). Left untouched.
- difyctl auth login remains blocked on host OpenAPI 404. v1 no longer uses CLI OAuth; keep App API key and dfoa_ tokens unmixed.

## Closed
- 阶段 6 Streamlit 过渡客户端 landed：登录/注册、广场卡片、/open 对话、只读侧边栏；token 在 session_state 并带 Bearer；旧未登录 POST /v1/threads 入口已去掉。默认 pytest 仍全 mock。
- 阶段 5 list_jobs/cancel_job + HTTP disable/cancel landed；disable 后不再生成新 run；取消是状态，已 sent 不撤回。默认 pytest 仍全 mock。
- 阶段 4 DifyClient + discover_douyin_leads landed in ToolNode; default pytest injects FakeDifyClient and does not POST real Dify. DIFY_LIVE_ENABLED stays false.
- 阶段 1 business SQL + in-memory repository landed; default pytest still does not open real Postgres.
- 阶段 2 FastAPI login/plaza/sidebar/open HTTP landed; old POST /v1/threads is no longer the product entry after login.
- 阶段 3 per-user/instance conversation memory, KB retrieve, media path/URL, and media_assets isolation landed. Graph nodes remain chatbot + tools.
- Plaza/sidebar, 一人多实例, binding table, instance KB retrieve, and field-level schema are locked in docs/modify/抖音运营智能体修改设计方案（1）.md.
- Phased execution for a new conversation is locked in stage/README.md and stage/抖音运营智能体分阶段实施套餐.md. Deleted stage1/ is not a source.
- User confirmed douyin-lead-discovery is published and console-tested; local `.env` has DIFY_API_KEY / DIFY_BASE_URL (values must not be copied into docs or memory).
- v1 no longer assumes two tools or default --no-send; no_send=false is the locked true-send path.
- Comment/DM review is intentionally skipped in v1 after C confirmed real publish.
- Input variable names for douyin-lead-discovery were read from the start node.
- Dify version for this host is 1.17.0 Community.
