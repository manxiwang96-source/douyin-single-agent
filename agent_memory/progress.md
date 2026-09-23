# Progress

## Current task
按 `docs/modify/抖音运营智能体Dify真实状态回传实施套餐.md` 完成后端真实 Dify 状态回传。

## Status
- 已读取 AGENTS、架构/设计文档、agent_memory、实施套餐及 `D:\浏览器下载路径\douyin-lead-discovery.yml`；DSL 文件可访问且未修改。
- `app/dify_client.py` 已区分外层 `dify_workflow_status` 与 DSL `job_status`，始终优先解析 `job_response` 的 `data.status`/根级 `status`，支持 `success/succeeded/failed/error/cancelled/canceled/timeout`，缺失/未知返回 `unverified` 和 `job status unavailable`；任务错误支持 `error/reason/error_message/failure_reason/message`。
- `app/leads.py` 已返回 `workflow_ok`、`delivery_ok`、最终 `status`、`delivery`、`message_details`、`job_id`；`job_response` 优先于 loop 字段，列表错误对象不入记录，逐条未确认不计入 `sent`，逐条失败保留错误别名，`written` 仅代表本地写入。
- `app/prompts.py` 已明确要求只依据 `job_status` 和 `delivery.*.sent` 向用户表述，不得将外层 succeeded 或 `written` 当作发送成功，并展示 `message_details` 中的 Dify 内容、状态和错误。
- 已更新 `tests/test_dify_client.py`、`tests/test_discover_leads.py`、`tests/fakes.py`，覆盖外层成功/内层失败、error、cancelled、缺失/未知、列表错误对象、私信明细、失败原因和 written 不覆盖真实失败。
- 相关测试通过：`venv\Scripts\python.exe -m pytest -q tests/test_dify_client.py tests/test_discover_leads.py tests/test_dify_status_return_playbook_doc.py`，共 36 passed。
- 完整测试通过：`venv\Scripts\python.exe -m pytest -q`，全部通过、6 skipped（含既有 Starlette 弃用 warning）。未触发真实 Dify 或真实抖音发送。
- `.local/` 是预先存在的未跟踪目录，本次未处理、不提交。

## Next
- 已完成相关及完整 pytest；下一步完成 diff/敏感信息/范围检查后，创建中文 Git commit，交付前确认仅修改后端解析、提示词、测试和项目记忆文件。
