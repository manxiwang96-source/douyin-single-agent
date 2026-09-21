# Progress

## Current task
阶段 5（任务取消）已完成：list_jobs / cancel_job、HTTP disable/cancel、enabled=false 不再生成新 run、取消是状态且已 sent 不撤回。

## Status
ToolNode 增加 list_jobs、cancel_job，从 configurable 读 user_id + agent_instance_id，只能动当前用户和当前实例。HTTP `POST /v1/jobs/{job_id}/disable` 与 `POST /v1/job-runs/{run_id}/cancel` 写同一行。禁用定义后 `create_job_run` 抛 JobDisabledError。进行中取消把 job_runs 标 cancelled，并把同一 run 下未发出的评论/私信标 cancelled；已 sent / failed / needs_login 不撤回。取消不删行。不实现抖音 8 点调度。晨报调度保持关闭。`POST /v1/assistant/jobs/run` 仍可手动留着。图节点仍只有 chatbot + tools。DIFY_LIVE_ENABLED 保持 false。Streamlit 仍是旧未登录入口。

## Next
阶段 6：Streamlit 过渡客户端。一次只做当前阶段。不要重建 stage1/。不要在未到阶段 7 时打真实 Dify。不要把 DIFY_LIVE_ENABLED 设为 true。
