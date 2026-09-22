# Bugs and Risks

## Open
- 已关闭：Dify 真实状态回传已落地并通过相关及完整 pytest；后续若 DSL 输出结构变化，需继续以实际 `job_response`/列表响应样本补回归测试。
- 当前有效限制：`job_response`、`list_message`、`list_comment` 仍按 DSL 原始字符串/JSON 兼容解析；缺失或未知状态保持 `unverified`，不能默认 `sent`。
- DSL 的列表节点未明确绑定本次 `job_id`/`run_id` 时，历史列表记录混入本次结果的风险仍存在；本次只记录风险，不修改 C 的 DSL。
- Streamlit v1 没有任务取消页；取消仍走阶段 5 的 HTTP/工具。
- 现网若未重启 uvicorn，5173 Origin 直连仍无 CORS 头；npm run dev 走 /v1 proxy 可联调，不能代替重启后的 CORS。
- 本地 .env 的 DOUYIN_HTTP_BASE_URL / DOUYIN_HTTP_API_TOKEN 仍为空。工人对空 base_url 使用已发布默认 http://192.168.1.33:8765；空 token 不写入 workflow_runs.inputs，live HTTP 只从 GET /parameters 补缺省。不要把 token 写入 git / 文档 / agent_memory。
- Cancelling a worker job may not stop the Dify poll loop or C's async job. Local status can be cancelled while send already happened.
- Morning-brief JOBS_NAMESPACE ("assistant", "jobs") remains global; conversation profile/KB/media are isolated as of phase 3.
- Phone-off 08:00 jobs fail if job tables are ever moved to the client.
- Feishu bot and this worker might both true-send if run together. Phase 7 live already ran; later live still needs to stagger with C.
- list_comment / list_message / snapshot 的完整 live JSON 样本仍未在本窗口触发；解析已覆盖数组、数组包装和错误对象，真实联调仍需人工控制。
- ~/.codex/templates/agent_memory/ is still missing; files follow the existing three-file layout.
- Live ChatOpenAI against aitokens.website can exceed 20s; unrelated.
- Pre-existing dirty file docs/summary/个人超级助手总结与逻辑复盘（2）.md makes test_each_heading_starts_with_plain_language fail (## 0. heading without nearby 白话). Left untouched.
- difyctl auth login remains blocked on host OpenAPI 404. v1 no longer uses CLI OAuth; keep App API key and dfoa_ tokens unmixed.
- Vue 401 会清 localStorage，但默认 http 客户端未回调 Pinia/路由，当前页可能仍显示已登录直到下次刷新。

## Closed
- 2026-09-22 Vue 前端闭环落地：CORS 默认放行 5173；frontend/ 登录→两步新建弹窗→卡片→对话+只读侧边栏接到 FastAPI。自动化测试只 mock，不打 live。
- 2026-09-22 手动联调：有 video_id 仍要 keyword，以及模型把 channels 改成 comment,dm/中文导致 C 的 /v1/commands/run 400。已收紧 prompt，并在 normalize_lead_channels 把非法 channels 归一成 comment,message；有 video_id 时不再写入 keyword。
- 阶段 7 live smoke passed：RUN_LIVE_DOUYIN=1、account=wmq、给定 video_id、no_send=false，默认 pytest 仍全 mock。
- 阶段 6 Streamlit 过渡客户端 landed：登录/注册、广场卡片、/open 对话、只读侧边栏；token 在 session_state 并带 Bearer；旧未登录 POST /v1/threads 入口已去掉。
- 阶段 5 list_jobs/cancel_job + HTTP disable/cancel landed；disable 后不再生成新 run；取消是状态，已 sent 不撤回。
- 阶段 4 DifyClient + discover_douyin_leads landed in ToolNode; default pytest injects FakeDifyClient and does not POST real Dify.
- 阶段 1-3 business SQL, login/plaza HTTP, and per-instance isolation landed.
- Plaza/sidebar, 一人多实例, binding table, instance KB retrieve, and field-level schema are locked in docs/modify/抖音运营智能体修改设计方案（1）.md.
- Phased execution is locked in stage/README.md and stage/抖音运营智能体分阶段实施套餐.md. Deleted stage1/ is not a source.
- User confirmed douyin-lead-discovery is published and console-tested; local .env has DIFY_API_KEY / DIFY_BASE_URL (values must not be copied into docs or memory).
- v1 no longer assumes two tools or default --no-send; no_send=false is the locked true-send path.
- Comment/DM review is intentionally skipped in v1 after C confirmed real publish.
- Dify version for this host is 1.17.0 Community.
