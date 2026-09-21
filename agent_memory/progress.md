# Progress

## Current task
阶段 4（Dify 工具 mock）已完成：DifyClient、discover_douyin_leads、workflow_runs 与 engage_* 尽力回写。默认 pytest 注入 FakeDifyClient。

## Status
ToolNode 已挂 discover_douyin_leads。未绑定 douyin-lead-discovery 拒绝。服务器写死 no_send=false、auto_login=true；空的 DOUYIN_HTTP_* 不写入 inputs。user 使用我们的 user_id。账号 paused/needs_login 拒调；无投影行仍允许。10 分钟窗口内相同 user_id+agent_instance_id+account+keyword+video_id 的进行中 run 不二次 POST。形状不明的 outputs 仍记成功 workflow_runs。DIFY_LIVE_ENABLED 保持 false。图节点仍只有 chatbot + tools。Streamlit 仍是旧未登录入口。

## Next
阶段 5：任务停用与运行取消。一次只做当前阶段。不要重建 stage1/。不要在未到阶段 7 时打真实 Dify。不要把 DIFY_LIVE_ENABLED 设为 true。
