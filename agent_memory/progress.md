# Progress

## Current task
阶段 6（Streamlit 过渡客户端）已完成：登录/注册、广场卡片、点卡片 /open 进入对话、右侧只读侧边栏；token 在 session_state，请求头 Bearer；保留生图生视频 HITL。

## Status
Streamlit 只调已有 HTTP，不 import 仓库业务表或 Store。登录后才有 thread。广场卡片展示头像/名称/简介/模式/创建时间/最近编辑时间。新建弹窗名称、简介、头像，模板固定 douyin_ops。interrupted 时禁用聊天输入。标题仍是抖音运营助手。默认 pytest 全 mock。DIFY_LIVE_ENABLED 保持 false。没有任务取消页，取消仍走阶段 5 的 HTTP/工具。

## Next
阶段 7：真实 Dify 交付。不要在未到阶段 7 时把 DIFY_LIVE_ENABLED 设为 true。不要改 C 的 Dify。不要把密钥写入 git / 文档 / agent_memory。
