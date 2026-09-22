# Progress

## Current task
下一窗口按 `docs/modify/抖音运营智能体删除HTTP实施套餐.md` 实现智能体实例逻辑删除 HTTP。

## Status
套餐已写入，代码尚未改。
- 查询 `GET /v1/agent-instances`、修改 `PATCH /v1/agent-instances/{id}` 后端已有。
- 删除只有仓库 `archive_agent_instance`，缺 `DELETE /v1/agent-instances/{id}`。
- 本套餐锁定：逻辑归档、不改仓库、不改前端、不做物理删除/7 天清扫。

## Next
新开对话读取该套餐，一次交付 DELETE HTTP + `tests/test_auth_plaza.py` + 更新 `memory-bank/architecture.md`。
不要映射 Vue。不要重做阶段 0–7。