# 抖音运营智能体 Dify 真实状态回传实施套餐

> 给后续新对话的执行手册：本套餐只修改本仓库后端对 Dify 工作流结果的解析、状态归一化、发送明细回传和测试；不修改同学 C 的 Dify DSL，不重做工人阶段 0–7，不改 Vue、Streamlit 或无关业务。
> 产品对错仍以 `docs/modify/抖音运营智能体修改设计方案（1）.md` 为准。Dify DSL 事实依据为用户提供的 `douyin-lead-discovery.yml`；如执行环境能访问该文件，开工时重新核对，但不要改写它。
> 标识符、环境变量、接口路径、表名、状态值保持英文。密钥只写本地 `.env`，不入库、不写本文档、不写 `agent_memory`。

## 0. 新对话必读

把下面这段贴给新对话（目标模式，一次完整交付）：

```text
读取 docs/modify/抖音运营智能体 Dify 真实状态回传实施套餐.md。
产品决策以 docs/modify/抖音运营智能体修改设计方案（1）.md 为准。
本窗口只修改后端 Dify 结果解析：以 DSL 输出的 job_status/job_response 为真实任务状态，区分 Dify 外层 workflow 状态、内部 job 状态和逐条评论/私信发送状态；失败或状态缺失时禁止回复成功；错误响应不得伪装成一条成功记录；返回私信发送内容和失败原因（仅限 Dify 实际返回的字段）。
不要修改同学 C 的 Dify DSL，不改 Vue、Streamlit，不重做工人阶段 0–7，不扩大到无关重构。
改完补充/更新测试，运行完整相关测试，更新 agent_memory/progress.md 和 agent_memory/bugs.md（只保留当前有效信息），创建中文 Git commit；不要把密钥写入 git、文档或 agent_memory。
```

开工顺序：

1. 读取本文、`memory-bank/architecture.md`、`memory-bank/design-document.md`、`agent_memory/{context,progress,bugs}.md`。
2. 阅读 `app/dify_client.py`、`app/leads.py`、`app/prompts.py`、`tests/test_dify_client.py`、`tests/test_discover_leads.py`；若可访问，再阅读 `douyin-lead-discovery.yml`。
3. 先写或更新解析和状态判定测试，再按第 6 节实现后端。
4. 运行相关 pytest，再运行完整 pytest；不打真实 Dify、不触发真实抖音发送。
5. 更新当前有效的 `agent_memory/progress.md` 与 `agent_memory/bugs.md`；本套餐是后端行为重大里程碑，完成后同步更新 `memory-bank/architecture.md` 的 Dify 结果契约描述。
6. 创建中文 commit，提交描述概括“Dify真实状态回传”。

## 1. 目标与成功标准

当前问题是：Dify 外层工作流返回 `succeeded`，但内部 `/v1/jobs/{job_id}` 可能已经 `failed`；或者 `/v1/commands/list` 返回错误对象，却被后端当成一条私信/评论记录并默认标记为 `sent`。

本套餐的唯一交付标准是：

> 用户看到的任务状态必须来自 DSL 轮询得到的真实 `job_status`；外层 Dify workflow `succeeded` 不能覆盖内部 job 的失败；状态缺失不能猜成成功。

交付后必须满足：

- 用户能看到 `dify_workflow_status` 与 `job_status`，且二者语义不混淆；
- `job_status=failed/error/cancelled/timeout` 时，用户不能看到“发送成功”；
- `job_status` 缺失、空值或无法解析时，不能返回成功；
- `list_message` / `list_comment` 的错误响应不能被当成一条发送记录；
- 只有逐条记录明确为 `sent`/等价成功状态时，才计入真实发送成功数量；
- 用户可看到 Dify 返回的私信内容、逐条状态和错误原因；
- `written.dms` / `written.comments` 只表示本地写入数量，不得被解释为发送成功数量；
- 相关测试和完整测试全部通过。

## 2. 已确认的 DSL 事实

用户提供的 `douyin-lead-discovery.yml` 的主要链路是：

```text
POST /v1/commands/run
  → 解析 job_id
  → 循环 GET /v1/jobs/{job_id}
  → GET /v1/snapshot
  → POST /v1/commands/list channel=comment
  → POST /v1/commands/list channel=message
  → 结束
```

DSL 结束节点输出：

```text
job_id
run_response
job_status
job_response
snapshot
list_comment
list_message
```

其中：

- `job_status` 是轮询代码写入 loop variable 的状态；
- `job_response` 是 `/v1/jobs/{job_id}` 的原始响应体；
- `list_comment` 是评论列表接口原始响应体；
- `list_message` 是私信列表接口原始响应体；
- `run_response` 是启动任务接口原始响应体；
- 列表字段不是规范化数组，通常需要先 JSON 解码。

DSL 的 `no_send` 开始节点默认值是 `true`，代表直接在 Dify 中按默认参数运行时偏向只发现不发送；本项目当前调用链会强制传入 `no_send=false`，该约束保持不变。发送动作由 `/v1/commands/run` 内部完成，DSL 没有单独的“发送节点”。

DSL 的轮询代码把 `succeeded`、`failed`、`error`、`cancelled`、`canceled` 都视为 `done`，但循环结束后没有根据失败状态阻止后续 `snapshot` 和 `commands/list` 节点。因此外层 Dify workflow 可能仍然走到结束节点，不能只看 Dify 外层 `data.status`。

## 3. 当前实现的已知问题

### 3.1 混淆外层 workflow 状态和内部 job 状态

`app/dify_client.py` 当前主要读取：

```text
data.status / 顶层 status
 data.outputs / 顶层 outputs
workflow_run_id / data.id / data.workflow_run_id / 顶层 id
 data.error / 顶层 error / 顶层 message
```

但没有从 DSL 输出的 `job_response` 中解析内部 job 的真实状态。

必须区分：

```text
dify_workflow_status = 外层 Dify 工作流引擎状态
job_status            = /v1/jobs/{job_id} 的业务任务状态
```

`job_status` 是本套餐规定的用户交付状态来源。

### 3.2 错误对象可能被当作一条记录

当前 `app/leads.py` 的列表解析对没有数组字段的字典存在如下风险：

```json
{"ok": false, "error": "当前账号未登录"}
```

可能被包装成一条记录，随后因为没有 `status`/`send_status` 又被默认当作 `sent`。

必须规定：只有明确的数组或明确的数组包装字段才进入记录解析；`ok=false`、`error`、`message` 等错误对象只能进入错误分支。

### 3.3 缺少逐条状态时默认 `sent`

当前评论和私信记录状态缺失时使用默认 `sent`。必须改为：

```text
明确成功 → sent
明确失败 → failed
状态缺失或未知 → unverified
```

`unverified` 不是数据库现有业务状态时，落库使用 `proposed`，用户返回和统计必须保留 `unverified` 语义，不能伪装为已发送。

### 3.4 本地写入数量被误当成发送数量

`written.comments` / `written.dms` 表示写入本地业务表的记录数，不表示抖音发送成功数。必须新增 delivery 统计，用户文案只能使用 delivery。

### 3.5 任务失败后仍可能读取列表

DSL 任务失败后仍会执行列表节点。后端必须先判定 `job_status`，任务失败时不能把后续列表结果当作本次成功发送证明。

## 4. 锁定的状态契约

### 4.1 状态字段

工具返回至少包含：

```json
{
  "ok": false,
  "workflow_ok": true,
  "delivery_ok": false,
  "status": "failed",
  "dify_workflow_status": "succeeded",
  "job_status": "failed",
  "workflow_run_id": "...",
  "job_id": "...",
  "error": "..."
}
```

字段含义：

- `dify_workflow_status`：外层 Dify `data.status`，仅用于诊断；
- `job_status`：DSL 轮询 `/v1/jobs/{job_id}` 得到的真实状态，是用户交付状态；
- `status`：本次本地业务运行的有效状态，按 `job_status` 归一化；
- `workflow_ok`：外层 Dify 工作流是否正常完成；
- `delivery_ok`：评论/私信是否有可靠的逐条结果；
- `ok`：是否允许对用户报告本次整体成功；
- `workflow_run_id`：Dify 外层运行 ID；
- `job_id`：DSL 启动的底层任务 ID；
- `error`：任务级或传输级错误原因。

### 4.2 状态优先级

最终状态按以下顺序判断：

1. HTTP 异常、超时、401、HTTP 400 以上；
2. `job_response` JSON 中的 `data.status` 或顶层 `status`；
3. DSL 输出的 `job_status`；
4. 外层 Dify `data.status` 或顶层 `status`；
5. 全部缺失时，按失败/未确认处理，禁止按成功处理。

终态映射：

| 输入状态 | `status` |
| --- | --- |
| `succeeded` | `succeeded` |
| `failed` / `error` | `failed` |
| `cancelled` / `canceled` | `cancelled` |
| `timeout` | `timeout` |
| 缺失或无法解析 | `failed`，`error=job status unavailable` |

特殊规则：

```text
外层 Dify status=succeeded + job_status=failed
→ status=failed, ok=false
```

```text
外层 Dify status=succeeded + 没有 job_status
→ status=failed, ok=false, error=job status unavailable
```

### 4.3 `ok` 判定

`ok=true` 必须同时满足：

- Dify 请求没有传输错误；
- `job_status=succeeded`；
- 没有任务级错误；
- 没有明确失败的评论/私信记录；
- 没有无法确认的评论/私信记录。

`workflow_ok=true` 不等于 `ok=true`。

## 5. 逐条评论/私信结果契约

### 5.1 结果统计

保留本地写入数量：

```json
"written": {
  "videos": 0,
  "comments": 1,
  "dms": 1
}
```

新增用户交付统计：

```json
"delivery": {
  "comments": {
    "sent": 0,
    "failed": 1,
    "unverified": 0
  },
  "dms": {
    "sent": 0,
    "failed": 1,
    "unverified": 0
  }
}
```

只有 `delivery.*.sent` 可以用于“已确认发送”文案。

### 5.2 单条状态归一化

从每条记录优先读取：

```text
status
send_status
```

归一化规则：

```text
sent / success / succeeded → sent
failed / fail / error       → failed
cancelled / canceled        → cancelled
needs_login                 → needs_login
缺少或未知                  → unverified
```

明确失败、取消、登录失效和未确认均不得计入 `sent`。

数据库现有状态集合不增加 `unverified` 时：

- 明确成功落库为 `sent`；
- 明确失败落库为 `failed`；
- 登录失效落库为 `needs_login`；
- 取消落库为 `cancelled`；
- 未确认落库为 `proposed`，但返回给用户必须保留 `unverified`。

### 5.3 私信明细

新增 `message_details`，每条尽量返回：

```json
{
  "message_id": "m001",
  "video_id": "v001",
  "source_text": "多少钱？",
  "content": "您好，这款产品售价是99元",
  "content_source": "reply",
  "status": "sent",
  "error": null
}
```

内容字段读取优先级：

```text
sent_content
actual_message
message_content
sent_message
message
reply
approved_reply
candidate_reply
```

展示标记：

- `sent_content` / `actual_message`：`实际发送内容`；
- `message` / `reply` / `approved_reply`：`Dify返回内容`；
- `candidate_reply`：`候选发送内容`，不能称为实际已发送。

错误字段读取优先级：

```text
error
reason
error_message
failure_reason
message
```

失败但没有原因时返回：

```text
Dify 未提供具体失败原因
```

禁止编造错误原因。

## 6. 实施改动清单

### 6.1 `app/dify_client.py`

- 保留现有 HTTP 状态、超时、401、无 API Key 和 JSON 解析错误处理；
- 保留外层字段解析，并明确输出 `dify_workflow_status`；
- 增加可复用的 JSON 解码和 job 状态提取逻辑；
- 支持 `job_response` 中根级和 `data` 嵌套结构；
- 对缺少 job 状态返回明确的 `job status unavailable`，不得默认 `succeeded`；
- 不把 `task_id`、`workflow_id` 等未参与状态判定的字段误当成成功依据。

### 6.2 `app/leads.py`

- 在 `run_discover_douyin_leads()` 中先解析 `job_response`，再决定最终状态；
- 外层 workflow 成功但内部 job 失败时，以内部 job 失败为准；
- 任务失败时不把 `list_comment` / `list_message` 当成成功发送证明；
- 重写列表响应解析，错误对象不得进入记录数组；
- 重写 `_item_status()`，缺少状态时返回 `unverified`，不再默认 `sent`；
- 增加评论、私信的 `delivery` 统计和 `message_details`；
- 保留 `written`，但摘要不得使用它表达发送成功；
- 在 `workflow_runs` 中保存有效业务状态：job succeeded→`succeeded`，job failed/error→`failed`，cancelled→`cancelled`，timeout→`timeout`，状态缺失→`failed`；
- 保持原始 `outputs` 结构兼容，不把诊断元数据混入已有输出字段，除非现有测试和调用方同步更新。

### 6.3 `app/prompts.py`

增加模型约束：

- 只能依据 `job_status` 说明工作流是否完成；
- 不得仅凭 `dify_workflow_status=succeeded` 说发送成功；
- 不得把 `written` 当成发送数量；
- `job_status` 缺失时必须说“无法确认真实任务状态”；
- `message_details` 存在时展示发送内容、状态和错误原因；
- 只有 `delivery.*.sent` 才能表述为“已确认发送”。

### 6.4 `memory-bank/architecture.md`

完成实现并通过测试后，补充 Dify 结果契约：

- 外层 Dify workflow 状态与 DSL job 状态分离；
- `job_status` 是真实任务交付状态；
- `written` 不代表发送成功；
- 发送明细和错误原因只使用 Dify 实际返回字段；
- 状态缺失 fail closed。

## 7. 用户可见结果示例

### 7.1 成功

```text
Dify 工作流任务已成功完成。
任务状态：succeeded。
已确认评论发送 1 条，私信发送 1 条。

私信内容：您好，这款产品售价是99元
```

### 7.2 内部任务失败、外层工作流成功

```text
Dify 外层工作流已完成，但内部任务失败。
Dify 工作流状态：succeeded。
实际任务状态：failed。
失败原因：当前账号未登录。
本次未确认有私信发送成功。
```

### 7.3 部分发送失败

```text
Dify 工作流任务已完成，但发送结果不完整。
任务状态：succeeded。
私信：已确认成功 1 条，失败 1 条，未确认 0 条。

失败原因：私信窗口打开失败。
```

### 7.4 状态缺失

```text
Dify 外层工作流已结束，但没有返回真实任务状态。
本次结果无法确认，未将其判定为发送成功。
```

## 8. 测试计划

更新或新增：

- `tests/test_dify_client.py`
- `tests/test_discover_leads.py`

必须覆盖：

1. 外层 `succeeded` + `job_response.status=succeeded`：最终 `status=succeeded`、`ok=true`；
2. 外层 `succeeded` + `job_response.status=failed`：最终 `status=failed`、`ok=false`，使用 job 错误原因；
3. `job_response.status=error`：映射为 `failed`；
4. `job_response.status=cancelled`：最终为 `cancelled`，不得报告成功；
5. `job_response` 缺失、空值或非法 JSON：`job status unavailable`，不得默认成功；
6. job 状态位于 `data.status` 和根级 `status` 两种结构时都能解析；
7. `list_message` 正常数组：提取内容、状态和错误；
8. `list_message` 为 `{"ok":false,"error":"..."}`：不产生私信记录，错误进入结果；
9. 私信 item 为 `sent`：只计入 `delivery.dms.sent`；
10. 私信 item 为 `failed`：只计入 `delivery.dms.failed`，用户摘要不得说成功；
11. 私信 item 缺少状态：计入 `unverified`，不得计入 `sent`；
12. `written.dms=1` 但 `delivery.dms.sent=0`：摘要不得出现“私信发送成功 1 条”；
13. `job_status=succeeded` 但存在失败 item：`workflow_ok=true`、`delivery_ok=false`、`ok=false`；
14. 保留 HTTP 401、超时、HTTP 400、Dify live disabled 等现有测试；
15. 修改当前将未知输出判为成功的测试，使其验证“发送结果未确认，不得报告成功”。

测试要求：

```text
默认 pytest 全部 mock，不触发真实 Dify，不触发真实抖音发送。
只有明确的 live 环境变量和人工运行时才允许 live smoke；本次实现窗口不要自行发真实消息。
```

## 9. 范围边界和未解决限制

- 本套餐不修改 `douyin-lead-discovery.yml`，不修改同学 C 的 Dify；
- 不把 Dify 包成 MCP；
- 不改 Vue、Streamlit、认证、广场和无关业务；
- 如果 `/v1/jobs/{job_id}` 不返回状态或错误字段，后端只能返回“无法确认”，不能推测成功；
- 如果 `/v1/commands/list` 不返回逐条发送状态，后端只能展示 Dify 返回内容并标记未确认；
- 如果列表接口不支持 `job_id`/`run_id` 过滤，后端无法仅凭当前 DSL 证明列表中的每条记录都属于本次任务；不能无条件表述为“本次刚刚发送”；
- 不新增数据库表，不 ALTER LangGraph 官方表；优先复用现有 `workflow_runs.outputs` 和状态字段，避免破坏现有接口。

## 10. 完成检查表

- [ ] 新对话先读本文、架构、设计、agent_memory 和相关代码
- [ ] 已区分 `dify_workflow_status` 与 `job_status`
- [ ] 已以 `job_response` 作为真实任务状态来源
- [ ] job 失败不会被外层 workflow 成功覆盖
- [ ] 缺少 job 状态不会默认为成功
- [ ] 错误响应不会伪装成一条私信/评论
- [ ] 缺少逐条状态不会默认 `sent`
- [ ] 已返回 `delivery` 和 `message_details`
- [ ] 用户能看到 Dify 返回的私信内容和错误原因
- [ ] `written` 不再作为发送成功数量
- [ ] `tests/test_dify_client.py` 与 `tests/test_discover_leads.py` 已更新
- [ ] 相关测试和完整 pytest 全部通过
- [ ] `memory-bank/architecture.md` 已同步结果契约
- [ ] `agent_memory/progress.md`、`agent_memory/bugs.md` 已更新为当前有效信息
- [ ] 已创建中文 Git commit
- [ ] 未修改 Dify DSL、Vue、Streamlit 或无关模块
- [ ] 未写入任何密钥、token 或密码
