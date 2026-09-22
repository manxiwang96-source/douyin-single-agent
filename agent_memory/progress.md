# Progress

## Current task
智能体实例逻辑删除 HTTP 已落地。

## Status
- `DELETE /v1/agent-instances/{id}` 走现有 `archive_agent_instance`，HTTP 层 `_owned_instance` 鉴权。
- 成功 200：`ok=true`、`status=archived`；未登录 401；不存在/他人/已归档/非法 UUID 404。
- 归档后列表不再返回该卡；open / sidebar / patch / 二次 DELETE 404；同名可再建。
- 未改仓库归档语义、未做物理删除/7 天清扫、未加 GET /{id}、未加服务端 keyword、未映射 Vue。

## Next
前端暂不映射删除/修改。不要重做阶段 0–7。
