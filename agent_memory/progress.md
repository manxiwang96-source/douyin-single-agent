# Progress

## Current task
Wrote the published-workflow API-key transport into `docs/modify/抖音运营智能体修改设计方案（1）.md`. `difyctl` is retired as the v1 default.

## Status
Doc + doc tests + `.env.example` placeholders updated. No worker business code. No Dify workflow edits. No secrets in git.

## Locked env names (empty until C publishes)
- `DIFY_BASE_URL=http://192.168.1.158/v1`
- `DIFY_API_KEY=`  (Service API `app-...`; only `.env`)
- `DIFY_LEAD_APP_ID=douyin-lead-discovery`
- `DOUYIN_HTTP_BASE_URL=`
- `DOUYIN_HTTP_API_TOKEN=`
Retired: `DIFYCTL_BIN`, `DIFY_COMMENT_APP_ID`, `DIFY_DM_APP_ID`.

## Next
- Wait for C to publish and provide the Service API key plus HTTP `base_url` / `api_token`.
- Do not implement `DifyClient` / Settings until asked.
