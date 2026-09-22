# Progress

## Current task
阶段 7（真实 Dify 交付）已完成。不要连做下一阶段。

## Status
已收紧 prompt：有 video_id 不再要 keyword，先警告再立刻调工具。`channels` 归一为 `comment`/`message`/`comment,message`，`comment,dm` 与中文「评论、私信」不再原样下发。有 video_id 时省略 keyword。
工人已真调已发布的 `douyin-lead-discovery`：`POST {DIFY_BASE_URL}/workflows/run`，Bearer `DIFY_API_KEY`。
`no_send=false` 由 `build_dify_inputs` 和 `DifyClient.run` 写死；HTTP 体把 bool 转成 select 字符串 `true`/`false`。
模型未填时补 C 开始节点默认：`platform=douyin`、`limit=20`、`channels=comment,message`、`assess=true`。
空的 `DOUYIN_HTTP_BASE_URL` 使用已发布默认 `http://192.168.1.33:8765`；空的 `DOUYIN_HTTP_API_TOKEN` 不写入 `workflow_runs.inputs`，live HTTP 只从 `GET /parameters` 补必填缺省。
本地 `.env` 的 `DIFY_LIVE_ENABLED=true` 未提交。
默认 pytest 仍注入 FakeDifyClient，零真发。
live smoke：`RUN_LIVE_DOUYIN=1` + `LIVE_DOUYIN_ACCOUNT=wmq` + `LIVE_DOUYIN_VIDEO_ID=7674838941266087168` 已通过（有 video_id 不填 keyword）。
`memory-bank/architecture.md` 已是抖音工人现网图。

## Next
本套餐阶段 7 已停。抖音 8 点调度不在本套餐。等用户明确说继续下一阶段再动手。
