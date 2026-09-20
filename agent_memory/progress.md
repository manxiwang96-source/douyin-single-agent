# Progress

## Current task
Make `difyctl` usable on PATH and sign in to local Dify `http://192.168.1.158`.

## Status
PATH is fixed. Login is blocked on the Dify host: `/openapi/v1/*` returns 404 (`OPENAPI_ENABLED` / `ENABLE_OAUTH_BEARER` are off by default). `difyctl auth login --host http://192.168.1.158 --insecure --no-browser` exits 6: `unsupported_endpoint` / HTTP 404. This machine cannot SSH or Docker into `192.168.1.158`. No workflow edits. No secrets written to git.

## Done
- Confirmed `difyctl version --client` works via full path and via `%USERPROFILE%\.local\bin\difyctl.cmd`.
- User PATH already had `%LOCALAPPDATA%\difyctl\bin`; Codex/old shells still need a new window or the shim.

## Next
- On the Dify host, set `OPENAPI_ENABLED=true` and `ENABLE_OAUTH_BEARER=true`, restart API, then rerun `difyctl auth login --host http://192.168.1.158 --insecure`.
- Do not `difyctl run` until C publishes `douyin-lead-discovery`.
