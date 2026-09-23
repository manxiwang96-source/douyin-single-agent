# Vue 聊天页流式输出与 Dify 节点进度实施套餐

> 本文是后续新对话执行「聊天 SSE 流式输出 + 右侧栏 Dify 节点进度」的唯一实施手册。请先完整阅读本文，再按实施要求、测试要求、验收标准完成一次闭环，不要只改后端或只改前端。
>
> 产品边界以 `docs/modify/抖音运营智能体修改设计方案（1）.md`、`memory-bank/architecture.md` 和仓库现有接口为准。标识符、环境变量、接口路径、数据字段和技术标识保持仓库原有英文命名，不因中文沟通而改名。
> 不要修改同学 C 的 Dify 工作流，不要改 LangGraph 官方 checkpoint/store 表，不要新增聊天消息表或 migration，不要把密钥写入 git、文档或 `agent_memory`。
>
> 旧套餐 `docs/modify/Vue聊天页本轮任务流程实施套餐.md` 里的「不要上 SSE」已被本文取代。**不要改那篇旧文档**，按本文实现流式输出。
> Streamlit 废弃：`ui/` 与 `tests/test_streamlit_view_model.py` 一律不要改、不要删、不做 SSE 兼容；坏掉可接受。

## 0. 新窗口直接执行指令

将下面这段作为新窗口 AI 的第一条任务指令，或让 AI 读取本文后按本文执行：

```text
读取 docs/modify/Vue聊天页流式输出与Dify节点进度实施套餐.md，并严格按照本文在当前仓库完成实现，直到交付成功。

本次任务：把 Vue 聊天发送/Resume 改成 SSE 流式输出，让前端能实时读取 Dify 工作流每个节点的状态并呈现在右侧栏。
- POST /v1/threads/{id}/messages 和 POST /v1/threads/{id}/resume 只返回 text/event-stream。事件只有 progress / token / thread / error。
- 预检 401/404/409 仍返回 JSON。不要加并行 JSON 端点，不要做 Accept 协商。
- LangGraph 使用 astream(..., stream_mode=["updates","messages","custom"], version="v2")。Jobs / morning brief 仍走 ainvoke。
- Dify 改为 response_mode=streaming；解析 workflow_started/node_started/node_finished/workflow_finished；跳过 ping；不要转发 text_chunk。
- 工具内用 get_stream_writer 推送 Dify 节点进度。节点嵌套在「抖音线索发现与触达」下，kind=dify_node。
- Vue 用 fetch + AbortController，不要 EventSource。去掉发送期 getThread 轮询。token 追加到 pending；thread 事件后再 applyThread。
- 进入 phase=running 时丢掉提前 token，恢复「正在回复」。Skip 冻结不变。主气泡 pending 无文本时仍显示「正在回复」。
- Streamlit 废弃，不要改 Streamlit。不要修改同学 C 的 Dify。不要新增聊天消息表。不要改旧套餐文档。

必须先阅读根目录 AGENTS.md、memory-bank/architecture.md、memory-bank/design-document.md、agent_memory/context.md、agent_memory/progress.md、agent_memory/bugs.md，并检查 Git 状态。

严格遵守本文的文件范围、协议边界、测试要求和提交要求。不要把 .local/ 或 frontend/src/standalone/DouyinView.vue 等已有无关未跟踪内容加入提交。

完成后运行后端测试、前端测试和前端构建，更新 memory-bank/architecture.md 与 agent_memory/{context,progress,bugs}.md，创建中文 Git commit，并最终按第 14 节交付报告。
```

开工顺序：

1. 读取本文、`docs/modify/抖音运营智能体修改设计方案（1）.md`、`memory-bank/architecture.md`、`memory-bank/design-document.md` 和 `agent_memory/{context,progress,bugs}.md`。
2. 阅读 `app/main.py`、`app/dify_client.py`、`app/leads.py`、`app/tools.py`、`app/thread_progress.py`、`app/serialize.py`、`app/graph.py`、`frontend/src/api/threads.ts`、`frontend/src/api/http.ts`、`frontend/src/views/ChatView.vue`、`frontend/src/components/ChatSidebar.vue`、`frontend/src/lib/chat.ts`、`frontend/vite.config.ts` 以及现有聊天/Dify 测试。
3. 先补 SSE 解析 helper 和会失败的测试，再改后端：Dify streaming、`get_stream_writer`、`_arun` 改 `astream`、进度 `children`/`failed`。
4. 把 `sse-starlette` 写入 `requirements.txt`。把现有 POST `/messages`/`/resume` 的 `.json()` 测试改为解析 SSE，401/404/409 仍 JSON。
5. 再改 Vue：`fetch` + `AbortController` 消费 SSE，去掉发送期 `getThread` 轮询，侧栏渲染嵌套 `children`。
6. 补前端测试，先跑定向测试，再跑完整前后端测试和前端构建。
7. 测试通过后更新 `memory-bank/architecture.md` 与 `agent_memory/{context,progress,bugs}.md`，创建中文 Git commit。

## 1. 任务目标

当前 Vue 聊天发送走阻塞 `ainvoke`，前端只能等整轮结束才拿到 `serialize_thread()`；发送中每 1 秒 `getThread` 轮询任务栏，但 Dify 是 `response_mode=blocking`，内部节点不可见。主气泡锁死「正在回复」，用户看不到生成中的 chatbot 文本。

本套餐交付后：

- 发送/Approve/Resume 过程中，前端通过 SSE 实时拿到节点进度和 chatbot token；
- 右侧栏「抖音线索发现与触达」下展开 Dify 内部节点，running 转圈 / done ✓ / failed ✕；
- 主气泡在无 token 时仍显示「正在回复」，有 token 时追加文本，`thread` 事件后再 `applyThread`；
- HITL interrupted 仍通过成功收尾的 `thread` 事件下发；Skip 冻结逻辑不变。

## 2. 当前能力与限制（不要猜）

必须按仓库现状实现，不要先改图或改 Dify DSL：

- 主客户端是 Vue `frontend/`。Streamlit 废弃，不要改 Streamlit。
- `POST /v1/threads/{thread_id}/messages` 和 `POST /v1/threads/{thread_id}/resume` 都在 `app/main.py` 的 `_arun` 里 `await runtime.graph.ainvoke(...)`，再 `serialize_thread()`，返回 JSON。
- 预检 401/404/409 已是 FastAPI JSON：未登录、线程不存在、HITL 冲突（发送时 interrupted / resume 时非 interrupted）。
- `GET /v1/threads/{thread_id}` 仍是同步 JSON，bootstrap 继续用它，不要改成 SSE。
- 图拓扑：`START -> chatbot -> tools_condition -> tools -> chatbot`。节点只有 `chatbot` 和 `tools`。Dify 是 ToolNode 工具 `discover_douyin_leads`，不是图节点。
- LangGraph 版本是 **1.2.11**；Python 3.11，因此工具内 `get_stream_writer()` 可用。参考 LangGraph 流式：`graph.astream(..., stream_mode=["updates","messages","custom"], version="v2")`。
- `sse-starlette` 已在 `venv`（3.4.11），**未写入** `requirements.txt`，实现时必须加上。
- Dify：`app/dify_client.py` 的 `DifyClient.run()` 使用 `response_mode=blocking` + `client.post()`，最终走 `parse_dify_workflow_payload`。测试 `tests/test_dify_client.py` 断言 `blocking` 并 mock `.post()`。
- 进度：`app/thread_progress.py` 从 checkpoint 推导 `progress{round_id,phase,steps}`。步骤尚无 `children`，status 尚无 `failed`。`discover_douyin_leads` 只显示正在运行「抖音线索发现与触达」。
- Vue：`frontend/src/api/threads.ts` 用 axios `chatHttp` POST JSON。`ChatView.vue` 发送中 `watch(sending)` 每 1s `getThread` 只更新任务栏，禁止 `applyThread`。`CHAT_TIMEOUT_MS = 360000`。
- 主气泡 pending 文案锁死「正在回复」；有 HITL 时输入框禁用；Skip 本地冻结 done，不进「正在整理回复」。
- 右栏 400px；聊天列主栏内 860px 居中；任务框置顶自滚。这些布局约束保持不变。
- Jobs / morning brief 仍走 ainvoke，在 `app/jobs.py`，不要改成 SSE。
- 现有测试 `tests/test_api.py`、`tests/test_isolation.py` 对 POST `/messages`/`/resume` 调用 `.json()`，实现后必须改 helper。
- 未跟踪的 `.local/` 与 `frontend/src/standalone/DouyinView.vue` 不是本任务，不提交。

## 3. 锁定决策

1. Streamlit 废弃：不改、不删、不做 SSE 兼容；`ui/` 与 `tests/test_streamlit_view_model.py` 不动。
2. `POST /v1/threads/{id}/messages` 和 `POST /v1/threads/{id}/resume` **只返回 SSE**（`text/event-stream`）。不加并行 JSON/stream 端点，不做 Accept 协商。预检 401/404/409 仍 JSON。
3. SSE 事件只允许四种：
   - `progress`：完整 `TaskProgress`（含 `children`）
   - `token`：`{"delta"}`，仅 chatbot 文本
   - `thread`：成功收尾的 `serialize_thread()`（含 HITL interrupted）
   - `error`：流开始后的 `{"detail"}`
4. 流内容：节点进度 + 主气泡 chatbot token。不要转发 text_chunk。不要把 Dify LLM 碎片当 chatbot token。
5. Dify：`response_mode=streaming`；解析 `workflow_started` / `node_started` / `node_finished` / `workflow_finished`；跳过 ping。只转发 `node_id` / `title` / `node_type` / `index` / `status` + error，不要 inputs/outputs。
6. 侧栏：Dify 节点嵌套在「抖音线索发现与触达」下；`kind=dify_node`；status 含 `failed`。
7. Vue：`fetch` + `AbortController`，不要 EventSource。去掉发送期 `getThread` 轮询。token 追加到 pending；`thread` 再 `applyThread`。进入 `phase=running` 时丢掉提前 token，恢复「正在回复」。Skip 冻结不变。
8. Jobs / morning brief 仍走 ainvoke。不改 Dify DSL、LangGraph 官方表、migration、聊天消息表。
9. 旧套餐「不要上 SSE」作废，但不要改那篇旧文档。
10. 标识符继续英文；commit 用中文。不提交 `.local/` 和 `frontend/src/standalone/DouyinView.vue`。

## 4. 不得修改

- 不要改 Streamlit（`ui/`、`tests/test_streamlit_view_model.py`）。
- 不要修改同学 C 的 Dify DSL / `douyin-lead-discovery.yml`。
- 不要改 LangGraph 官方 checkpoint/store 表；禁止 ALTER；不要新增聊天消息表或 migration。
- 不要改图拓扑，不要把 Dify 提成独立图节点。
- 不要新增并行 JSON 聊天端点，不要做 Accept 协商。
- 不要转发 text_chunk。
- 不要 EventSource。
- 不要把发送期进度快照 `applyThread` 到聊天气泡。
- 不要改主列 860px、右栏 400px、Skip 冻结、HITL 同轮、pending 无文本时的「正在回复」。
- 不要改 `docs/modify/Vue聊天页本轮任务流程实施套餐.md`。
- 不要提交 `.local/` 与 `frontend/src/standalone/DouyinView.vue`。
- 不要写入密钥、token、密码。

## 5. SSE 契约

### 5.1 路由行为

| 条件 | 响应 |
| --- | --- |
| 未登录 / token 无效 | HTTP 401 JSON `{"detail":"not authenticated"}` |
| 线程不存在或不属于当前用户 | HTTP 404 JSON `{"detail":"thread not found"}` |
| POST messages 时线程 `interrupted` | HTTP 409 JSON `{"detail":"thread is waiting for review"}` |
| POST resume 时线程不是 interrupted | HTTP 409 JSON `{"detail":"thread is not waiting for review"}` |
| 预检通过 | HTTP 200 `Content-Type: text/event-stream`，用 `sse-starlette` 的 `EventSourceResponse` |

不要根据 `Accept` 切换 JSON/SSE。GET thread、广场、登录、Jobs 保持现有 JSON。

### 5.2 事件格式

每个事件：

```text
event: <name>
data: <json>
```

允许的 `<name>` 只有：

```text
progress
token
thread
error
```

`progress` data 是完整 TaskProgress，字段至少：

```text
round_id, phase, steps[]
```

每个 step：

```text
id, kind, tool, label, status, spin, children?
```

`token` data：

```json
{"delta": "一段 chatbot 文本"}
```

只在 `langgraph_node=="chatbot"`、无 `tool_call_chunks`、有文本时发送。工具模型碎片、Dify `text_chunk` 都不要当 token。

`thread` data 就是现有 `serialize_thread()` JSON，包括 `messages`、`interrupt`、`progress`、`status`。HITL 成功收尾也走 `thread`（`status=interrupted`），不要另发明事件。流正常结束必须有且仅有一次最终 `thread`（实现上可在 generator 结束前 yield 一次；测试取最后一个 `thread`）。

`error` data：

```json
{"detail": "human readable error"}
```

只用于**流已经开始之后**的失败。流开始前的 401/404/409 仍走 JSON，不要改成 `error` 事件。

### 5.3 事件时序

典型一轮：

1. 一个或多个 `progress`（思考 -> 工具/Dify 节点 -> 整理回复）
2. 零个或多个 `token`（仅 chatbot 可见文本）
3. 恰好一个收尾 `thread`
4. 若中途异常：`error`，然后结束；不要再发假成功 `thread`

HITL：工具 interrupt 后发 `thread`（interrupted），不要继续 token。Approve/Skip 的 resume 再开一条新 SSE。

### 5.4 测试 helper

在 `tests/http_helpers.py`（或同级 helper）增加 SSE 解析：

- 按空行拆 event block，读 `event:` 与 `data:`
- 200：解析全部事件，返回最后一个 `thread` 作为「兼容旧 `.json()` 的线程体」
- 401/404/409：继续 `.json()`，不要当 SSE 解析
- `TestClient.post()` 通常能拿到完整 SSE 文本，优先用 `response.text`，不要为测流去打真实网络

旧测试把 `client.post(.../messages).json()` 换成这个 helper，断言气泡/HITL/Skip 的语义不变。

## 6. 进度 JSON（children / failed）

向后兼容：现有 `round_id` / `phase` / `steps` 保留。本套餐只扩展 step。

### 6.1 step 扩展

```text
status: done | running | waiting | failed
spin: status == running
children: 可选数组，结构与 step 相同，但 Dify 子节点 kind 固定为 dify_node
```

Dify 子节点：

```text
id: dify:{node_id}:{index}
kind: dify_node
tool: discover_douyin_leads
label: 节点 title（没有 title 时用 node_id）
status: running | done | failed
spin: status == running
```

不要把 Dify inputs/outputs 放进 progress。error 可以进子节点的可选 `error` 字段，但不要把大段 outputs 当 label。

### 6.2 嵌套规则

- 只有 `discover_douyin_leads` 这一步显示 children。
- 子节点按 `index` 排序，后到的同 id 覆盖先到的。
- 父步骤文案仍是正在运行「抖音线索发现与触达」；失败时 status=`failed`，spin=false，文案可保持工具名，不要改成 Dify 内部标题。
- 父步骤 failed 判定：工具结果 `ok=false`，或归一化 status ∈ {failed, timeout, auth_expired}。
- 普通工具、思考、审核、整理回复不要伪造 Dify children。

### 6.3 回放

live 进度来自 `custom` 事件（见第 7 节）。`GET /v1/threads/{id}` 和最终 `thread` 事件必须能回放已经结束的 Dify 节点：

- 工具 JSON 增加紧凑 `workflow_nodes`（只要 node_id/title/node_type/index/status/error）
- `thread_progress()` 读 `discover_douyin_leads` 的 ToolMessage JSON，把 `workflow_nodes` 填进该 step 的 children
- 不要为回放去再打 Dify

### 6.4 前端类型

`frontend/src/lib/chat.ts`：

- `TaskStepStatus` 增加 `failed`
- `TaskStepKind` 增加 `dify_node`
- `TaskStep` 增加可选 `children?: TaskStep[]`
- `parseStep` 递归解析 children；未知 status 不要当成 running 转圈
- `freezeSkipProgress` 继续去掉 composing，不要动无关 Dify children

## 7. 后端实现

### 7.1 `_arun` 改流

`app/main.py` 预检（鉴权、线程归属、409）保持抛 JSON HTTPException。预检通过后不要再 `ainvoke`。

改成大致结构（标识符保持英文，不必逐字复制）：

```python
async def event_generator():
    async for item in runtime.graph.astream(
        payload,
        config,
        stream_mode=["updates", "messages", "custom"],
        version="v2",
    ):
        mode, data = _unpack_stream_item(item)
        if mode == "updates":
            snapshot = await runtime.graph.aget_state(config)
            progress = overlay_live_dify_children(thread_progress(snapshot), live_children)
            yield {"event": "progress", "data": json.dumps(progress, ensure_ascii=False)}
        elif mode == "custom":
            # 合并 live Dify children 到 discover_douyin_leads，再发 progress
            ...
        elif mode == "messages":
            message_chunk, metadata = data
            if should_emit_chatbot_token(message_chunk, metadata):
                yield {"event": "token", "data": json.dumps({"delta": text}, ensure_ascii=False)}
    snapshot_thread = serialize_thread(runtime, thread_id)
    yield {"event": "thread", "data": json.dumps(snapshot_thread, ensure_ascii=False)}
```

`_unpack_stream_item` 必须兼容 list-mode 的 `(mode, data)` 元组；如果 `version="v2"` 实际给出 dict，按 `type`/`data` 取。不要在实现窗口再争论协议，写一个小单测钉死解包。

返回：

```python
return EventSourceResponse(event_generator(), media_type="text/event-stream")
```

异常：generator 内 catch 后 yield `error`，不要把 traceback 当 detail。

### 7.2 token 过滤

只在同时满足时发 `token`：

- metadata 的 `langgraph_node == "chatbot"`
- 没有 `tool_call_chunks`
- 能抽出非空文本

chatbot 节点可继续 `ainvoke` 绑定模型；LangGraph `messages` 模式会抓 token。若定向测试证明 chatbot `ainvoke` 完全不发 token，再把 chatbot 内部改为模型 `astream`，**不要拆节点、不要改 tools_condition**。

进入工具执行（progress `phase=running`）后，前端会丢掉提前 token；后端仍可选择不再发工具阶段的 chatbot 碎片，但过滤规则以上面三条为准。

### 7.3 Dify streaming

`DifyClient.run()` **对外仍返回现有 dict**（ok/status/outputs/error/job_status 等）。内部改为 streaming：

- body `response_mode=streaming`
- 用 `client.stream("POST", url, headers=..., json=body, timeout=...)`
- 按行解析 SSE/`data:` JSON
- 事件：
  - `ping`：跳过
  - `text_chunk`：跳过，不要转发 text_chunk
  - `workflow_started`：可忽略或只记 run id
  - `node_started` / `node_finished`：回调 `on_event`，只带 node_id/title/node_type/index/status/error
  - `workflow_finished`：用 payload 走现有 `parse_dify_workflow_payload`
- 没有 `workflow_finished` 就 fail closed，不得猜成功
- HTTP 401 / timeout / HTTPError 映射保持现有 `_failure` 语义

签名增加可选回调，默认 None：

```python
def run(self, name, inputs, *, user=None, on_event=None) -> dict
```

现有 `tests/test_dify_client.py` mock 了 `.post()`，必须改为提供 `.stream()`（或 MockTransport 返回 `text/event-stream`）。`response_mode` 断言改为 `streaming`。TimeoutClient 也要有 `stream`。

### 7.4 工具内推送 live 进度

`discover_douyin_leads` / `run_discover_douyin_leads` 把 `on_event` 传给 `DifyClient.run`。回调里：

1. 更新内存中的 children（id=`dify:{node_id}:{index}`）
2. 安全调用 `get_stream_writer()`；图外调用不得抛（try/except 后直接 return）
3. writer 写入 compact payload，例如 `{"dify_nodes":[...]}` 或带 parent tool 名

`_arun` 收到 `custom` 后，把 live children 叠到当前 progress 里 `tool==discover_douyin_leads` 的那一步，立刻发 `progress`。

工具最终 JSON 用现有 `json_tool_result`，额外写入紧凑 `workflow_nodes`，供 GET thread 回放。不要把 Dify inputs/outputs 整包塞进 ToolMessage 之外的新表。

### 7.5 FakeDifyClient

```python
def run(self, name, inputs, *, user=None, on_event=None)
```

默认行为保持现有成功结果。若构造时提供节点事件列表，或 `enqueue` 了带 events 的 payload，则在 return 前按顺序调用 `on_event`。这样不打真实 Dify 也能测侧栏 children。

### 7.6 进度推导

`thread_progress()`：

- 解析 ToolMessage JSON；`discover_douyin_leads` 的 `workflow_nodes` -> children
- 工具失败 -> 该 step `status=failed`，`spin=false`
- Skip / waiting_review / composing / 新 round_id 规则保持旧套餐
- live overlay 只发生在 SSE 期间，不要让 overlay 污染 checkpoint

### 7.7 不要动的后端

- Jobs / morning brief 仍走 ainvoke
- `serialize_thread()` 气泡过滤不变（隐藏 tool_calls，媒体仍挂助手气泡）
- 不要改 `app/sql/`，不要 migration

## 8. 前端实现

### 8.1 HTTP

`postMessage` / `resumeThread` 改为 `fetch` SSE，不要走 axios `chatHttp.post` 当最终结果。`getThread`、广场、登录仍用现有 axios。

要求：

- Header：`Authorization: Bearer ...`、`Accept: text/event-stream`、`Content-Type: application/json`
- 使用 `AbortController`；用 `CHAT_TIMEOUT_MS`（360000）的 timer 调用 `abort()`。不要用 `AbortSignal.timeout`（jsdom 不稳）
- 预检 401/404/409：HTTP 状态不是 200 时按 JSON 读 `detail`，不要当 SSE 解析
- 401 必须 `clearSession`，对齐现有 axios 拦截器
- 建议 `ChatHttpError { status, detail, code? }`，让 `apiErrorMessage` 的 `DETAIL_MAP` 仍可用；timeout abort 时 `code=ECONNABORTED`，这样 `ChatView` 现有 `isTimeoutError` 仍成立
- 解析 body `ReadableStream`：按 `\n\n` 拆块，读 `event:` / `data:`
- 每到 `progress` 回调任务栏；每到 `token` 回调 delta；`thread` 作为 Promise resolve 值；`error` 作为 reject

`frontend/tests/http.test.ts` 改为 mock `fetch`，不再把 `postMessage` 断言建立在 `chatHttp` adapter 上。axios 客户端测试可继续覆盖广场/登录。

### 8.2 ChatView

- 删除 `watch(sending)` 的 `getThread` 轮询和 `progressTimer`
- 发送/Approve 过程中只靠 SSE `progress` 更新 `taskProgress`（仍走 `shouldApplyTaskProgress`）
- token：追加到对应 pending 助手气泡。pending 无文本时仍显示「正在回复」+ 点；有 token 后显示文本，可保留 typing dots
- 收到 `progress.phase==="running"` 时，丢掉提前 token，把该 pending 恢复成「正在回复」（工具阶段不要把第一轮 chatbot 草稿留在主气泡）
- `thread` 事件后再 `applyThread`；不要在 progress/token 阶段 `applyThread`
- Skip 冻结不变：本地 `freezeSkipProgress`，后续非 done 快照不覆盖
- HITL：`thread.status==="interrupted"` 后现有卡片逻辑不变
- 超时/错误：继续 `markRequestMessage`，超时文案可见

### 8.3 侧栏

`ChatSidebar.vue` 在每个 step 下渲染 `children`：

- running：转圈
- done：✓
- failed：✕（不要用等待空心点冒充失败）
- 嵌套缩进，不要把 Dify 节点提升成与「抖音线索发现与触达」平级
- 空 children 不渲染子列表

### 8.4 Vite 代理

`frontend/vite.config.ts` 的 `/v1` proxy 增加：

```ts
timeout: 0,
proxyTimeout: 0,
```

避免 6 分钟聊天流被代理切断。不要改 port 5173 和 target 8000。

## 9. 建议改动文件

后端：

- `requirements.txt`：加入 `sse-starlette`
- `app/main.py`：`_arun` 改 SSE `astream`
- `app/dify_client.py`：`response_mode=streaming` + `on_event`
- `app/leads.py` / `app/tools.py`：`get_stream_writer`、`workflow_nodes`
- `app/thread_progress.py`：children / failed / 回放
- `app/serialize.py`：只跟随 progress 结构，不要改气泡过滤
- `tests/fakes.py`：`FakeDifyClient.run(..., on_event=None)` 可回放节点事件
- `tests/http_helpers.py`：SSE 解析；200 取最后 `thread`；401/404/409 仍 JSON
- `tests/test_api.py`、`tests/test_isolation.py`：改用 helper
- `tests/test_dify_client.py`、`tests/test_discover_leads.py`：`.stream()` + `streaming`
- `tests/test_serialize_progress.py`：children / failed
- 新增定向测试（推荐 `tests/test_chat_sse.py`）：progress/token/thread/error 顺序、Dify children live overlay、chatbot token 过滤、预检 JSON

前端：

- `frontend/src/api/threads.ts`
- `frontend/src/api/http.ts`（ChatHttpError / 401 清 session，可复用 `clearSession`）
- `frontend/src/lib/errors.ts`
- `frontend/src/lib/chat.ts`
- `frontend/src/views/ChatView.vue`
- `frontend/src/components/ChatSidebar.vue`
- `frontend/src/styles/agent.css`：失败 ✕ 与 children 缩进；不要改 400px / 860px
- `frontend/vite.config.ts`
- `frontend/tests/http.test.ts`
- `frontend/tests/chat-view.test.ts`
- `frontend/tests/chat.test.ts`
- `frontend/tests/components.test.ts`

文档（代码通过后才改）：

- `memory-bank/architecture.md`
- `agent_memory/context.md`
- `agent_memory/progress.md`
- `agent_memory/bugs.md`

不要改：

- `ui/`
- `tests/test_streamlit_view_model.py`
- `docs/modify/Vue聊天页本轮任务流程实施套餐.md`
- Dify DSL
- `.local/`
- `frontend/src/standalone/DouyinView.vue`

## 10. 测试要求

默认 pytest 全部 mock，不打真实 Dify，不触发真实抖音发送。

### 10.1 后端

至少覆盖：

1. POST messages 预检 401/404/409 仍是 JSON，`Content-Type` 不含 event-stream。
2. 预检通过后 200，`content-type` 含 `text/event-stream`。
3. 纯文本一轮：事件含 `progress` 与收尾 `thread`；最后一个 `thread` 的气泡协议与现在一致。
4. chatbot 有可见文本：出现 `token`，delta 拼接等于最终助手气泡；带 `tool_call_chunks` 的碎片不出现在 token 里。
5. `discover_douyin_leads` 运行中：父步骤文案为正在运行「抖音线索发现与触达」，children 含 `kind=dify_node`、id 形如 `dify:{node_id}:{index}`。
6. 节点 `node_started` -> running 转圈；`node_finished` succeeded -> done；failed -> failed。
7. 不要转发 text_chunk：SSE 事件名没有 Dify 的 text_chunk，token 也不是 Dify 碎片。
8. 工具 `ok=false` 或 status ∈ failed/timeout/auth_expired：父步骤 `failed`。
9. GET thread 能从 `workflow_nodes` 回放 children，不必再跑流。
10. HITL：resume 前 409 JSON；Approve/Skip 的 resume 也是 SSE；Skip 后 phase=done，没有进行中的整理回复。
11. FakeDifyClient 不传 `on_event` 时旧测试仍通过。
12. Dify 客户端请求 body 为 `response_mode=streaming`；ping 被跳过；workflow_finished 仍走 `parse_dify_workflow_payload`。
13. Jobs / morning brief 仍走 ainvoke：现有 `tests/test_jobs.py` 不得改成 SSE。
14. 现有 HITL / 媒体 / metadata / 进度 round_id 测试继续通过。

### 10.2 前端

至少覆盖：

1. `postMessage` / `resumeThread` 用 fetch，带 Bearer，不用 EventSource。
2. 200 SSE：progress 更新任务栏；token 追加 pending；thread 后才 `applyThread`。
3. 发送期不再轮询 `getThread`。
4. pending 无文本显示「正在回复」+ 点；有 token 显示文本。
5. 收到 `phase=running` 后提前 token 被丢掉，恢复「正在回复」。
6. 401 清 session；409/timeout 仍走现有文案映射。
7. 侧栏 children：running 转圈 / done ✓ / failed ✕，嵌套在「抖音线索发现与触达」下。
8. Skip 冻结不变；Approve 不清空任务栏。
9. 右栏 400px、主列 860px 断言仍在。
10. `http.test.ts` mock fetch，不再依赖 `chatHttp` adapter 完成 `postMessage`。

现有发送、相同文本双发、超时、旧响应防覆盖测试必须继续通过。

## 11. 验证命令

在仓库根目录运行后端测试：

```powershell
D:\iwen-codex\codex\agentdemo\venv\Scripts\python.exe -m pytest -q
```

在前端目录运行：

```powershell
cd D:\iwen-codex\codex\agentdemo\frontend
npm test -- --run
npm run build
```

命令失败时必须先自行定位并修复，再重新执行；不能删除有效测试、放宽断言或屏蔽异常。不要打真实 Dify，不要触发真实抖音发送。

## 12. 文档与 Git 要求

代码和测试通过后更新：

- `memory-bank/architecture.md`：写明聊天 messages/resume 只返回 SSE；事件 progress/token/thread/error；Dify `response_mode=streaming`；侧栏 `dify_node` children；Vue fetch+AbortController；Jobs / morning brief 仍走 ainvoke；Streamlit 废弃不维护。
- `agent_memory/context.md`、`progress.md`、`bugs.md`：只保留当前有效信息。至少记录不要转发 text_chunk、不要 EventSource、发送期不再 getThread 轮询、phase=running 丢提前 token。

提交前检查：

```powershell
git diff --stat
git diff
git status --short
```

确认：

- 没有修改 `.local/`；
- 没有修改或提交 `frontend/src/standalone/DouyinView.vue`；
- 没有写入密钥、token、密码；
- 没有数据库 migration；
- 没有修改 Dify DSL；
- 不要改 Streamlit；
- 没有改旧套餐 `Vue聊天页本轮任务流程实施套餐.md`。

建议中文提交信息：

```text
实现聊天流式输出与Dify节点进度
```

本窗口若只落地手册本身，提交信息用：

```text
新增聊天流式输出与Dify节点进度实施套餐
```

每次改动完成后都必须创建对应的中文 Git commit。

## 13. 验收标准

同时满足以下条件才算完成：

- messages/resume 成功路径只返回 `text/event-stream`，事件只有 `progress` / `token` / `thread` / `error`；
- 401/404/409 仍 JSON；
- 右侧栏能看到 Dify 内部节点嵌套在「抖音线索发现与触达」下，failed 有 ✕；
- 主气泡无 token 时仍是「正在回复」，有 token 时追加，`thread` 后再 `applyThread`；
- 进入 `phase=running` 会丢掉提前 token；
- 不要转发 text_chunk，不要 EventSource，发送期不再 `getThread` 轮询；
- Jobs / morning brief 仍走 ainvoke；
- 不要改 Streamlit，不要修改同学 C 的 Dify，不要新增聊天消息表；
- 前后端测试和前端构建通过；
- 已创建中文 Git commit。

## 14. 交付报告

完成后向用户说明：

1. 修改了哪些文件；
2. SSE 四种事件如何映射 LangGraph `astream` 的 updates/messages/custom；
3. Dify streaming 如何解析节点、如何 `get_stream_writer`、如何 `workflow_nodes` 回放；
4. Vue 如何 fetch+AbortController，如何处理 token / running 清草稿 / thread+applyThread；
5. 侧栏 children 与 failed 如何呈现；
6. 是否修改 Dify、数据库、migration 或 Streamlit；
7. 后端测试、前端测试、前端构建结果；
8. Git commit hash；
9. 尚存风险，例如 Dify 若缺少 node 事件则只能显示父步骤、代理超时依赖 `timeout: 0`。
