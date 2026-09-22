# Bugs and Risks

## Open
- Streamlit v1 没有任务取消页；取消仍走阶段 5 的 HTTP/工具。
- 默认 CORS 仍只有 Streamlit `8501`。Vue `http://localhost:5173` / `http://127.0.0.1:5173` 尚未放行，留给下一窗口一次交付的第一步，做完立刻继续脚手架，不要停在 CORS。
- 本地 `.env` 的 `DOUYIN_HTTP_BASE_URL` / `DOUYIN_HTTP_API_TOKEN` 仍为空。工人对空 `base_url` 使用已发布默认 `http://192.168.1.33:8765`；空 token 不写入 `workflow_runs.inputs`，live HTTP 只从 `GET /parameters` 补缺省。不要把 token 写入 git / 文档 / agent_memory。
- Cancelling a worker job may not stop the Dify poll loop or C's async job. Local status can be cancelled while send already happened.
- Morning-brief JOBS_NAMESPACE ("assistant", "jobs") remains global; conversation profile/KB/media are isolated as of phase 3.
- Phone-off 08:00 jobs fail if job tables are ever moved to the client.
- Feishu bot and this worker might both true-send if run together. Phase 7 live already ran; later live still needs to stagger with C.
- `list_comment` / `list_message` / `snapshot` live JSON samples are still unconfirmed; writeback is best-effort.
- ~/.codex/templates/agent_memory/ is still missing; files follow the existing three-file layout.
- Live ChatOpenAI against aitokens.website can exceed 20s; unrelated.
- Pre-existing dirty file docs/summary/个人超级助手总结与逻辑复盘（2）.md makes test_each_heading_starts_with_plain_language fail (## 0. heading without nearby 白话). Left untouched.
- difyctl auth login remains blocked on host OpenAPI 404. v1 no longer uses CLI OAuth; keep App API key and dfoa_ tokens unmixed.

## Closed
- 2026-09-22 手动联调：有 video_id 仍要 keyword，以及模型把 `channels` 改成 `comment,dm`/中文导致 C 的 `/v1/commands/run` 400。已收紧 prompt，并在 `normalize_lead_channels` 把非法 channels 归一成 `comment,message`；有 video_id 时不再写入 keyword。
- 阶段 7 live smoke passed：`RUN_LIVE_DOUYIN=1`、account=wmq、给定 video_id、`no_send=false`，默认 pytest 仍全 mock。
- 阶段 6 Streamlit 过渡客户端 landed：登录/注册、广场卡片、/open 对话、只读侧边栏；token 在 session_state 并带 Bearer；旧未登录 POST /v1/threads 入口已去掉。
- 阶段 5 list_jobs/cancel_job + HTTP disable/cancel landed；disable 后不再生成新 run；取消是状态，已 sent 不撤回。
- 阶段 4 DifyClient + discover_douyin_leads landed in ToolNode; default pytest injects FakeDifyClient and does not POST real Dify.
- 阶段 1-3 business SQL, login/plaza HTTP, and per-instance isolation landed.
- Plaza/sidebar, 一人多实例, binding table, instance KB retrieve, and field-level schema are locked in docs/modify/抖音运营智能体修改设计方案（1）.md.
- Phased execution is locked in stage/README.md and stage/抖音运营智能体分阶段实施套餐.md. Deleted stage1/ is not a source.
- User confirmed douyin-lead-discovery is published and console-tested; local `.env` has DIFY_API_KEY / DIFY_BASE_URL (values must not be copied into docs or memory).
- v1 no longer assumes two tools or default --no-send; no_send=false is the locked true-send path.
- Comment/DM review is intentionally skipped in v1 after C confirmed real publish.
- Dify version for this host is 1.17.0 Community.
