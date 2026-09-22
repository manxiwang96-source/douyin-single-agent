# Progress

## Current task
一次交付 Vue 前端闭环：CORS → 脚手架 → 登录 → 广场两步弹窗 → 对话+只读侧边栏，接到现有 FastAPI。

## Status
已完成，不要重做。
- 对话发送后 `sending` 时显示助手侧「正在回复」占位气泡，请求结束即消失。
- 默认 CORS 含 Streamlit 8501 与 Vue 5173。
- frontend/ Vue 3 + Vite 模块已落地：登录/注册、广场两步弹窗、卡片、对话+只读侧边栏。
- Vitest 16 passed（含 login→modal→card→chat 与 HITL 禁用输入）。
- vue-tsc + vite build 通过。
- 默认 pytest 176 passed, 5 skipped（未开 RUN_LIVE_DOUYIN）。
- 已对现网 FastAPI 跑通 register→login→create→list→open→sidebar→thread；sidebar 含工作流「抖音线索发现与触达」和工具 discover_douyin_leads，无 model 栏。
- 未做 Dify 真发。缺 live 配置不算交付成功。

## Next
仅当本地 DIFY_LIVE_ENABLED=true 且与 C 错开时，在 Vue 里手动真发一条 discover_douyin_leads。
抖音 8 点调度不在本套餐。
