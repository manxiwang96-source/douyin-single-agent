# Progress

## Current task
Make `difyctl` usable in the user's CMD and sign in to local Dify `http://192.168.1.158`.

## Status
Client binary is fine. User typed PowerShell `$env:PATH=...` into CMD, which is why the second command said 文件名、目录名或卷标语法不正确. `difyctl auth login` is still blocked on the Dify host: `POST /openapi/v1/oauth/device/code` returns 404 (`OPENAPI_ENABLED` / `ENABLE_OAUTH_BEARER` default false). Exit 6 `unsupported_endpoint`. This machine cannot SSH or Docker into `192.168.1.158`. No workflow edits. No secrets written to git.

## Done
- `difyctl.exe` at `C:\Users\86153\AppData\Local\difyctl\bin\difyctl.exe` runs `version --client` → `0.2.0-alpha`.
- Shim `C:\Users\86153\.local\bin\difyctl.cmd` now calls that absolute path (no `%LOCALAPPDATA%`).
- User PATH already has `%LOCALAPPDATA%\difyctl\bin` then `%USERPROFILE%\.local\bin`. Old CMD windows do not see it; new CMD or full exe path does.
- Re-ran `difyctl auth login --host http://192.168.1.158 --insecure --no-browser -v`; still HTTP 404.

## Next
- In a **new CMD** (not PowerShell), run the full-path version command, then login.
- On the Dify host, set `OPENAPI_ENABLED=true` and `ENABLE_OAUTH_BEARER=true`, restart API, then login again.
- Do not `difyctl run` until C publishes `douyin-lead-discovery`.
