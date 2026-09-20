# Progress

## Current task
Lock env var names for the published-workflow API-key transport. Do not call Dify until C publishes.

## Status
`difyctl` is set aside. User asked how to write env vars first; values stay empty until publish. No secrets in git. No workflow edits.

## Locked env names (empty until C publishes)
- `DIFY_BASE_URL=http://192.168.1.158/v1`  (origin + `/v1`, same style as `OPENAI_API_BASE_URL`)
- `DIFY_API_KEY=`  (Service API `app-...`; only `.env`)
- `DIFY_LEAD_APP_ID=douyin-lead-discovery`  (log / switch; not required to `POST /workflows/run`)
- `DOUYIN_HTTP_BASE_URL=`  (C HTTP `base_url` input)
- `DOUYIN_HTTP_API_TOKEN=`  (C HTTP `api_token` input; only `.env`)
Retired: `DIFYCTL_BIN`, `DIFY_COMMENT_APP_ID`, `DIFY_DM_APP_ID`.

## Next
- After C publishes and creates the key, fill `.env` locally; never commit the key.
- Promote this in the modify doc when user asks to write.
