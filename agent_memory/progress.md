# Progress

## Current task
阶段 3（对话隔离）已完成：configurable、profile/KB namespace、媒体路径与 media_assets、线程归属校验。

## Status
ainvoke 携带 thread_id / user_id / agent_instance_id / allowed_workflow_codes。remember_fact / recall_facts 写入 (user_id, agent_instance_id, "profile")。chatbot 与 search_kb 检索 (user_id, agent_instance_id, "kb")。媒体文件与 URL 按用户+实例隔离，写 media_assets。图节点仍只有 chatbot + tools。未写 DifyClient。Streamlit 仍是旧未登录入口。

## Next
阶段 4：Dify 工具（mock）。一次只做当前阶段。不要重建 stage1/。不要在未到阶段 7 时打真实 Dify。
