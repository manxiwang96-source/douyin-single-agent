# 抖音运营智能体删除 HTTP 实施套餐

> 给后续新对话的执行手册：本窗口只补智能体实例的逻辑删除 HTTP，不改仓库、不改前端。
> 产品对错仍以 `docs/modify/抖音运营智能体修改设计方案（1）.md` 为准，尤其实例 `status=archived` 后广场不展示、名称可重用。
> 工人阶段 0–7 与 Vue 前端闭环已完成，不要重做。
> 标识符、环境变量、接口路径、表名、状态值保持英文。密钥只写本地 `.env`，不入库、不写本文档、不写 `agent_memory`。

## 0. 新对话必读

把下面这段贴给新对话（目标模式，一次完整交付）：

```text
读取 docs/modify/抖音运营智能体删除HTTP实施套餐.md。
产品决策以 docs/modify/抖音运营智能体修改设计方案（1）.md 为准。
工人阶段 0–7 与 Vue 前端闭环已完成，不要重做 Dify / 业务表 / Streamlit / Vue，不要改 C 的工作流。
本窗口只实现智能体实例逻辑删除 HTTP：DELETE /v1/agent-instances/{id} 调用现有 archive_agent_instance。
不要改仓库归档语义，不要物理删除，不要加 7 天清扫，不要加 GET /{id}，不要加服务端 keyword 搜索。
改完补测试并中文 commit。不要把密钥写入 git / 文档 / agent_memory。
```

开工顺序：

1. 读本文、`memory-bank/architecture.md`、`memory-bank/design-document.md`、`agent_memory/{context,progress,bugs}.md`。
2. 按第 5 节一次做完：HTTP、测试、架构文档。
3. 使用仓库 `venv` 跑默认 pytest；全绿后再中文 commit。
4. 完成后更新 `memory-bank/architecture.md` 与 `agent_memory/progress.md`。
5. 不要改前端、不要删 Streamlit、不要改 C 的工作流。

## 1. 目标与成功标准

当前后端：

| 能力 | 现状 |
| --- | --- |
| 查询 | 已有 `GET /v1/agent-instances`，返回当前用户未归档卡片 |
| 修改 | 已有 `PATCH /v1/agent-instances/{id}`，可改 title / intro / avatar |
| 删除 | 仓库已有 `archive_agent_instance`，**还没有 HTTP** |

本窗口成功定义：主人能用 Bearer 调 `DELETE /v1/agent-instances/{id}`，实例变成 `archived`；广场列表不再出现；同名可再建；open / sidebar / patch 对该 id 返回 404。

未登录 DELETE 401。不存在 / 他人 / 已归档 / 非法 UUID 一律 404。默认 pytest 全绿。

## 2. 当前后端事实（不要重做）

- `GET /v1/agent-instances`：当前用户 `status <> archived` 的卡片。
- `POST /v1/agent-instances`：v1 只接受 `template_code=douyin_ops`。
- `PATCH /v1/agent-instances/{id}`：只改 title/intro/avatar 才更新 `updated_at`。
- `POST /v1/agent-instances/{id}/open`、`GET .../sidebar`、`GET .../avatar`：均走 `require_owned_instance`；归档实例视为不存在。
- `InMemoryBusinessRepository.archive_agent_instance` 与 `PostgresBusinessRepository.archive_agent_instance` 已把 `status` 设为 `archived`，**不 bump `updated_at`**。
- 部分唯一索引：`UNIQUE (user_id, lower(title)) WHERE status <> 'archived'`。归档后同名可复用。现有 `tests/test_business_repository.py::test_archived_title_can_be_reused` 已覆盖，不要改断言。
- `archive_agent_instance` **不校验 user_id**。所有权必须在 HTTP 层用 `_owned_instance`（内部 `require_owned_instance`）。
- 查询形态已锁定为列表 + 以后前端本地搜索。本窗口不加 `GET /v1/agent-instances/{id}`，不加服务端 `q` 参数。

## 3. 锁定决策

- 删除 = **逻辑删除**（`status=archived`），不是物理删行。
- **不用改仓库逻辑**。不要新增 purge 方法，不要改 `archive_agent_instance` 语义，不要给归档补 `user_id` 参数，不要 bump `updated_at`。
- HTTP 方法与路径：`DELETE /v1/agent-instances/{agent_instance_id}`。不要做成 `POST .../archive`。
- 鉴权：`Authorization: Bearer <token>`。未登录 `401` `not authenticated`。
- 成功 `200`：

```json
{"ok": true, "agent_instance_id": "<uuid>", "status": "archived"}
```

- 失败：不存在 / 他人实例 / 已归档 / 非法 UUID → `404` `agent instance not found`。二次 DELETE 也是 404，不要做成幂等 200。
- 归档后：`GET /v1/agent-instances` 不再返回该卡；`open` / `sidebar` / `patch` / 再 `DELETE` 均为 404；同名 `POST` 可以 201。
- 不删子表、不碰 LangGraph `checkpoints*` / `store`、不删头像/媒体磁盘文件。长期磁盘占用以后再做 7 天物理清扫，本窗口不预留 purge API、不加 `archived_at` 列。
- 前端、Streamlit、任务调度、Dify、图节点都不改。
- Vue 套餐里「v1 界面不要做改名 PATCH」仍然有效：本窗口只补后端 DELETE，不把改/删映射到 Vue。

## 4. 为什么不改仓库 / 为什么不做物理删除

立刻 `DELETE FROM agent_instances` 会失败：`agent_instance_workflows`、`app_threads`、`douyin_accounts`、`job_definitions`、`job_runs`、`workflow_runs`、`engage_videos`、`engage_comments`、`engage_dms`、`media_assets`、`agent_knowledge_documents` 都 REFERENCES `agent_instances`，且 **没有 `ON DELETE CASCADE`**。知识向量在 Store namespace `(user_id, agent_instance_id, "kb")`，对话 checkpoint 在官方 LangGraph 表（禁止 ALTER）。

逻辑删除几乎不占 FastAPI 进程内存：只改 Postgres 一行 `status`。关联行和磁盘文件仍占库/磁盘，v1 一人几张卡片可忽略。不要把「占内存」当成改仓库的理由。

## 5. 一次交付的施工顺序

一次完整交付。下面步骤只是本窗口内部顺序，不是要开多个对话。

### 步骤 1 — HTTP

在 `app/main.py` 的 `create_app` 内、`patch_instance` 附近增加：

- `@app.delete("/v1/agent-instances/{agent_instance_id}")`
- 先 `_owned_instance(user, agent_instance_id)`
- 再 `repo.archive_agent_instance(instance.agent_instance_id)`
- 返回 `{"ok": True, "agent_instance_id": str(instance.agent_instance_id), "status": "archived"}`

不要改 `archive_agent_instance` 实现。不要在仓库层加 user_id 校验。

### 步骤 2 — 测试

改 `tests/test_auth_plaza.py`：

- 未登录 `DELETE /v1/agent-instances/{任意uuid}` → 401。可并进现有 `test_unauthenticated_business_routes_are_401`。
- 主人删除：200，body 含 `ok=true`、`status=archived`、同一 `agent_instance_id`；随后 `GET /v1/agent-instances` 不含该卡；同名再建 201；对该 id 的 `open` / `sidebar` / `patch` / 第二次 `DELETE` 均为 404。
- 他人删除：404，原主人列表仍能看到该卡。

不要改 `test_archived_title_can_be_reused`。不要对真实 Postgres 做本窗口测试（默认 pytest 走内存仓库）。

### 步骤 3 — 架构与记忆

- `memory-bank/architecture.md` 的 Plaza HTTP 列表补上 `DELETE /v1/agent-instances/{id}`。
- `agent_memory/progress.md` 写明删除 HTTP 已落地；`agent_memory/context.md` 如需同步一句即可，不要写成流水账。

提交中文：`补齐智能体实例逻辑删除 HTTP`。

## 6. 测试与验收

- 文档锁：`tests/test_delete_http_playbook_doc.py`（本文件存在且锁定决策未被改丢）。
- HTTP：`tests/test_auth_plaza.py` 覆盖 401 / 主人归档 / 二次 404 / 他人 404 / 同名可复用。
- 仓库：现有归档测试保持绿。
- 交付前用仓库 `venv` 跑默认 pytest，全部通过。不要设 `RUN_LIVE_DOUYIN=1`。

## 7. 明确不做

- 改 `archive_agent_instance` 或任何仓库删除/清扫逻辑
- 物理删除、7 天延迟清扫、`archived_at` 列、purge API
- `GET /v1/agent-instances/{id}`、服务端 keyword / 分页 / 状态筛选
- 改 Vue / Streamlit；本窗口不把删除、修改映射到前端
- 禁用 job、删 KB chunks、删磁盘头像/媒体
- 改 C 的工作流、重做工人阶段 0–7、改 `docs/summary/` 脏文件、重建 `stage1/`
- 把密钥、token、密码写入 git / 文档 / `agent_memory`

## 8. 假设

- 查询继续用现有列表；前端搜索以后再映射，本窗口不管。
- 修改 HTTP 已存在，本窗口不改 PATCH。
- 逻辑删除留下的子表和文件可接受；以后若做物理清扫再单开套餐。