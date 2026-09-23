# Vue 聊天页本轮任务流程实施套餐

> 本文是后续新对话执行「右侧栏本轮任务流程」的唯一实施手册。请先完整阅读本文，再按“实施要求、测试要求、验收标准”完成一次闭环，不要只改 CSS 或只加轮询。
>
> 产品边界以 `docs/modify/抖音运营智能体修改设计方案（1）.md`、`memory-bank/architecture.md` 和仓库现有接口为准。标识符、环境变量、接口路径、数据字段和技术标识保持仓库原有英文命名，不因中文沟通而改名。
> 不要修改同学 C 的 Dify 工作流，不要改 LangGraph 官方 checkpoint/store 表，不要新增聊天消息表或 migration，不要把密钥写入 git、文档或 `agent_memory`。

## 0. 新窗口直接执行指令

将下面这段作为新窗口 AI 的第一条任务指令，或让 AI 读取本文后按本文执行：

```text
读取 docs/modify/Vue聊天页本轮任务流程实施套餐.md，并严格按照本文在当前仓库完成实现。

本次任务：在 Vue 聊天页右侧栏新增「本轮任务流程」面板，让用户看到当前任务做到哪一步。
- 主气泡文案仍是「正在回复」，不要改成任务步骤。
- Dify 内部节点不可见，只能显示正在运行「抖音线索发现与触达」加转圈。
- LangGraph ToolNode 工具必须具名显示，并留在本轮历史里。
- HITL 与本轮是同一轮：Approve 只追加/更新步骤，不清空任务栏。
- 点 Skip 算本轮完成，任务栏立刻 done，不进入「正在整理回复」。
- 本轮结束后历史保留，直到用户发出下一条消息才重置。
- 右侧栏加宽到 400px，但聊天内容列仍按主栏内 860px 居中，不要按整页重算。
- 聊天可滚，右栏不随聊天滚；任务框置顶自滚，目录在下方另滚。

必须先阅读根目录 AGENTS.md、memory-bank/architecture.md、memory-bank/design-document.md、agent_memory/context.md、agent_memory/progress.md、agent_memory/bugs.md，并检查 Git 状态。

严格遵守本文的文件范围、协议边界、测试要求和提交要求。不要改 Dify DSL，不要上 SSE，不要改 Streamlit，不要把 .local/ 或 frontend/src/standalone/DouyinView.vue 等已有无关未跟踪内容加入提交。

完成后运行后端测试、前端测试和前端构建，更新必要的 memory-bank/ 和 agent_memory/ 文档，创建中文 Git commit，并最终报告修改文件、进度如何推导、HITL/Skip 行为、布局约束、测试结果和 commit hash。
```

开工顺序：

1. 读取本文、`docs/modify/抖音运营智能体修改设计方案（1）.md` 第 8 节、`memory-bank/architecture.md`、`memory-bank/design-document.md` 和 `agent_memory/{context,progress,bugs}.md`。
2. 阅读 `app/serialize.py`、`app/graph.py`、`app/tools.py`、`app/catalog.py`、`app/main.py`、`frontend/src/views/ChatView.vue`、`frontend/src/components/ChatSidebar.vue`、`frontend/src/lib/chat.ts`、`frontend/src/styles/agent.css` 以及现有聊天测试。
3. 先补后端 `progress` 推导测试，再改 `serialize_thread()`。
4. 再改 Vue 侧栏布局、任务框和发送/Approve/Skip 轮询，禁止用轮询结果改聊天气泡。
5. 补前端测试，先跑定向测试，再跑完整前后端测试和前端构建。
6. 测试通过后更新 `memory-bank/architecture.md` 与 `agent_memory/{context,progress,bugs}.md`，创建中文 Git commit。

## 1. 任务目标

当前 Vue 聊天页无法告诉用户「任务做到哪一步了」。聊天请求走阻塞 `ainvoke`，主区只有 pending 气泡「正在回复」；`serialize_thread()` 会丢掉 `tool_calls` / `ToolMessage`；右侧 `ChatSidebar` 只有只读目录。Dify 工作流是 `response_mode=blocking`，内部节点不可见。

本套餐交付后，用户在右侧栏顶部能看到**当前这一轮用户问题**的步骤历史：已完成步骤可上翻，正在执行的步骤在底部，HITL 等待审核时不转圈。主聊天列、发送合并、超时回显和 HITL 卡片行为保持不变。

## 2. 当前能力与限制（不要猜错）

必须按现状实现，不要先改图或改 Dify：

- 主客户端是 Vue `frontend/`，不要跟 Streamlit。
- `POST /v1/threads/{thread_id}/messages` 和 `POST /v1/threads/{thread_id}/resume` 都是 `await runtime.graph.ainvoke(...)`，没有 SSE。
- `GET /v1/threads/{thread_id}` 是同步 FastAPI，内部 `serialize_thread()` → `graph.get_state()`。同步路由走线程池，生产 `AppPostgresSaver` 用 `asyncio.to_thread`，连接池 `max_size=10`，工具执行期间轮询 GET 可行。
- `api_messages_from_state()` 跳过带 `tool_calls` 的 `AIMessage`，`ToolMessage` 只提取媒体 URL。聊天气泡协议不要改。
- 图节点只有 `chatbot` 和 `tools`，`parallel_tool_calls=False`。LangGraph 只在节点之间写 checkpoint，因此首个工具 checkpoint 出现前，「正在思考」主要靠前端本地步骤。
- `generate_image` / `generate_video` 在工具内部 `interrupt()`，类型 `review_media`。Skip 后图仍回到 chatbot 出一句回复；任务栏把 Skip 视为本轮结束。
- `discover_douyin_leads` 调 Dify blocking POST，`leads.py` 在 POST 前把 `workflow_runs.status` 写成 `running`。不要解析 Dify 内部节点，不要展示发送条数。
- 侧栏现在只有 `GET /v1/agent-instances/{id}/sidebar` 的目录字段。
- 布局：`.agent-chat-layout` 为 `minmax(0, 1fr) 320px`；`.agent-chat` 是 `min-height: 100vh`，消息区和侧栏都能滚。聊天列是主栏内 `.agent-chat-column`：`max-width: 860px; margin: 0 auto`。

## 3. 已确认的产品决策

执行时不要重新讨论，不要扩大范围。

### 3.1 展示粒度

- 右侧栏新增本轮任务滚动框；主列 pending 文案保持「正在回复」。
- 只展示具名长步骤，不展示 Dify 内部节点。
- 能显示正在调用的 LangGraph 工具；不能显示 Dify 工作流内部节点。
- 历史是**每一轮用户消息**，不是整段会话时间线。
- 空进度文案：`暂无进行中的任务`。打开已完成对话时，重建并展示最后一轮已完成步骤。

### 3.2 本轮边界

- 新的用户消息 = 新一轮，任务栏重置。
- `round_id` = 该轮用户消息的 `client_message_id`；Approve / resume 沿用同一 id。
- 本轮结束条件只有两个：
  1. 助手气泡返回结果；
  2. 用户在等待审核时点 Skip。
- Approve 后若本轮还没走完，右侧任务栏不能清空或整表刷新，只能追加或更新步骤。
- 本轮结束后任务历史保留，直到用户发出下一条消息才刷新。
- Skip 后图仍可回 chatbot 出气泡，但任务栏立刻 `phase=done`，不进入「正在整理回复」，后续 composing 轮询必须忽略。

### 3.3 可达步骤

固定顺序：

1. `正在思考`
2. 运行工作流 / 生图 / 生视频 / 具名工具
3. `等待审核「生成图片」` 或 `等待审核「生成视频」`（仅 HITL）
4. `正在整理回复`

Skip 后审核步改为 `已跳过「生成图片」` 或 `已跳过「生成视频」`，不再追加整理回复。

### 3.4 工具文案

| 工具名 | 进行中 | HITL / Skip |
| --- | --- | --- |
| `discover_douyin_leads` | 正在运行「抖音线索发现与触达」 | 无 HITL |
| `generate_image` | 正在生成图片 | 等待审核「生成图片」；Skip 后已跳过「生成图片」 |
| `generate_video` | 正在生成视频 | 等待审核「生成视频」；Skip 后已跳过「生成视频」 |
| `search_kb` | 知识库检索 | 无 |
| `remember_fact` | 记住事实 | 无 |
| `recall_facts` | 回忆事实 | 无 |
| `send_email` | 发送邮件 | 无 |
| `list_jobs` | 查看任务 | 无 |
| `cancel_job` | 取消任务 | 无 |
| 未知 / MCP（如 `get_weather`） | 正在调用「{name}」 | 无 |

具名工具步骤必须留在本轮历史，不能闪一下就消失。同一标签用对勾/转圈区分状态；HITL 等待不转圈。

### 3.5 布局

- 侧栏宽 `320px` → `400px`。
- 聊天列继续在主栏内 `860px` + `margin: 0 auto`，加宽右栏时不要按整页重算居中。
- `.agent-chat` 锁视口高度；聊天区可滚，右栏不随聊天滚。
- 任务框固定在侧栏顶部并自滚；目录在下方独立滚动，不能把任务框顶走。
- 窄屏 `max-width: 900px` 仍堆叠；任务框给 `min-height`。

## 4. 不得修改的内容

- 同学 C 的 Dify DSL / 工作流内部节点进度；
- LangGraph 官方 `checkpoints*` / `store` 表，禁止 ALTER；
- 新增聊天消息表或任何 migration；
- 主气泡 pending 文案「正在回复」；
- 聊天气泡过滤规则（继续隐藏 tool 消息，只把媒体挂到助手气泡）；
- SSE / websocket / 新进度专用 HTTP 路径；
- Streamlit 客户端；
- 取消任务页或其他广场功能；
- `.local/`、`frontend/src/standalone/DouyinView.vue` 等无关未跟踪内容。

允许的协议变化只有一种：现有 `GET /v1/threads/{thread_id}`、发消息和 resume 的 JSON **只读附加** `progress` 字段。旧字段保持兼容。

## 5. 进度 JSON 契约

`serialize_thread()` 在现有字段旁增加：

```json
{
  "progress": {
    "round_id": "client-message-id-or-null",
    "phase": "idle|thinking|running|waiting_review|composing|done",
    "steps": [
      {
        "id": "thinking",
        "kind": "thinking|tool|review|composing",
        "tool": null,
        "label": "正在思考",
        "status": "done|running|waiting",
        "spin": false
      }
    ]
  }
}
```

字段规则：

- `round_id`：最后一条 `HumanMessage` 的 `client_message_id`；没有则回退该消息 `id`；没有用户消息则为 `null`。
- `phase`：
  - `idle`：没有本轮用户消息；
  - `thinking`：已有本轮用户消息，尚无工具/HITL/最终助手文本，且未 Skip；
  - `running`：本轮有未完成 ToolNode 工具，且不是 HITL 等待；
  - `waiting_review`：存在 `review_media` interrupt；
  - `composing`：工具已完成（非 Skip），正在生成最终助手文本；
  - `done`：最终助手气泡已产出，或本轮媒体工具已被 Skip。
- `steps[]` 按发生顺序追加，用稳定 `id` 更新同一条目，不要每秒生成新 id。
- 推荐 `id`：`thinking`、`tool:{tool_name}:{tool_call_id}`、`review:{tool_name}`、`composing`。
- `spin` 仅 `status=running` 为 true；`waiting` 必须 false。
- 前端只渲染 `label` + `status` + `spin`，不要自己再翻译工具名。

没有本轮时：

```json
{ "round_id": null, "phase": "idle", "steps": [] }
```

## 6. 后端实现

主要改 `app/serialize.py`。推导逻辑可留在同文件；只有文件明显过大时才抽 `app/thread_progress.py`，不要新开 HTTP。

从 `snapshot` 读取：

- `snapshot.values["messages"]`
- `snapshot.next`
- `interrupt_payload(snapshot)`
- 最后一条 `HumanMessage` 之后的本轮消息

推导步骤：

1. 没有 `HumanMessage`：返回 idle 空步骤。
2. 本轮永远先有 `正在思考`。若后面已经出现工具、HITL、Skip 或最终助手文本，思考步为 `done`；否则为 `running`。
3. 本轮 `AIMessage.tool_calls`：按映射表追加/更新工具步，初始 `running`。
4. 对应 `ToolMessage` 到达后，该工具步改为 `done`。
5. 若 `ToolMessage.content` 为 `User skipped media generation.`：该媒体步改为 `已跳过「生成图片/视频」`，`phase=done`，**不要**再追加 `正在整理回复`。即使 `snapshot.next` 含 `chatbot` 也保持 done。
6. 若存在 `review_media` interrupt：思考步 done；对应生图/生视频步更新为 `等待审核「生成图片/视频」`，`status=waiting`，`spin=false`，`phase=waiting_review`。Approve 后 interrupt 消失、工具仍在执行时，同一轮把该步改回 `正在生成图片/视频` + `running`。
7. 工具完成且非 Skip、尚无无 `tool_calls` 的最终 `AIMessage`，或 `next` 含 `chatbot`：追加 `正在整理回复` 为 `running`，`phase=composing`。
8. 最终无 `tool_calls` 的助手文本已写入，且无 interrupt、无未完成工具：`phase=done`，整理回复步 `done`。
9. 无工具的纯回复：只走思考 → 整理回复 → done。首个 checkpoint 前可以只有思考 running。

兼容：

- `api_messages_from_state()` 和 `interrupt` 结构不变。
- Streamlit 忽略多余 `progress` 字段即可，不要为它改 UI。
- 现有 `tests/test_api.py` 的消息/HITL/媒体断言必须继续通过。

## 7. 前端布局

改 `frontend/src/styles/agent.css`、`frontend/src/components/ChatSidebar.vue`、`frontend/src/views/ChatView.vue`。

CSS 锁定：

- `.agent-chat`：`height: 100vh; overflow: hidden;`，不要再用页面整体撑高让右栏跟着聊天一起滚。
- `.agent-chat-layout`：`grid-template-columns: minmax(0, 1fr) 400px;`，并 `min-height: 0; overflow: hidden;`。
- `.agent-chat-main` / `.agent-messages`：继续让消息列表自己 `overflow: auto`。
- `.agent-chat-column`：保持 `max-width: 860px; margin: 0 auto;`。
- `.agent-sidebar`：`display: flex; flex-direction: column; overflow: hidden; min-height: 0;`，去掉整栏单滚动。
- `.agent-task-progress`：侧栏顶部，`flex: 0 1 auto; min-height: 120px; max-height: 42%; overflow-y: auto;`。
- `.agent-sidebar-catalog`：包住原目录区块，`flex: 1 1 auto; min-height: 0; overflow-y: auto;`。
- `@media (max-width: 900px)`：布局仍 `1fr` 堆叠；侧栏可保留 `max-height: 40vh`，但任务框必须有 `min-height`，不能被目录挤没。

`ChatSidebar` 在目录上方新增任务框：

- 标题：`当前任务`。
- `steps` 为空时显示 `暂无进行中的任务`。
- 每步显示 `label`；`spin=true` 显示转圈；`status=done` 显示完成对勾；`status=waiting` 不转圈。
- 不要展示原始工具英文名，除非文案本身就是 `正在调用「{name}」`。

## 8. 前端轮询与 HITL

改 `frontend/src/views/ChatView.vue` 和 `frontend/src/lib/chat.ts`。不要改 `mergeChatMessages` 的气泡合并语义。

状态：

- `activeRoundId`：当前任务栏对应的用户 `clientMessageId`。
- `skipFrozen`：本轮是否已 Skip 收口。
- `taskProgress`：当前渲染的 `progress`。

行为：

1. 新发送：`activeRoundId = clientMessageId`，`skipFrozen = false`，本地立刻写入思考 running，并重置任务栏。
2. `sending === true`（含 Approve 后的 resume）时每 1s `getThread`。轮询**只更新任务栏**，禁止调用 `applyThread`。
3. 轮询到的 `progress.round_id` 必须等于 `activeRoundId` 才接受；否则忽略。
4. Approve：不重置步骤，不改 `activeRoundId`，进入 `sending` 并继续轮询。
5. Skip：本地立刻把审核步改为已跳过、`phase=done`，`skipFrozen = true`。此后本轮忽略 `thinking` / `running` / `composing` 更新。`resumeThread` 返回后可以 `applyThread` 更新聊天气泡，但任务栏保持 done 历史。
6. 新步骤默认滚到任务框底部；用户若已上翻查看历史，不要抢滚动。
7. `postMessage` / `resumeThread` 的正式响应仍用 `applyThread` 更新消息和 HITL 卡片；同时用响应里的 `progress` 更新任务栏，但 Skip 冻结后不得把任务栏改回进行中。
8. 页面刷新 / bootstrap：用服务端最后一轮 `progress` 重建任务栏。若最后一轮已 done 或 waiting_review，直接展示，不要当成空闲。

主列 HITL 卡片、输入禁用、pending「正在回复」、超时/失败回显保持现有行为。

## 9. 建议改动文件

后端：

- `app/serialize.py`（必要）
- 需要时新增 `app/thread_progress.py`
- 不要为进度改 `app/main.py` 路由签名；GET/POST 继续返回 `serialize_thread()` 即可

前端：

- `frontend/src/views/ChatView.vue`
- `frontend/src/components/ChatSidebar.vue`
- `frontend/src/lib/chat.ts`
- `frontend/src/styles/agent.css`

测试：

- `tests/test_api.py`
- 新增 `tests/test_serialize_progress.py`（推荐）
- `frontend/tests/chat.test.ts`
- `frontend/tests/chat-view.test.ts`
- `frontend/tests/components.test.ts`

文档：

- `memory-bank/architecture.md`
- `agent_memory/context.md`
- `agent_memory/progress.md`
- `agent_memory/bugs.md`

## 10. 测试要求

### 10.1 后端

至少覆盖：

1. 空线程：`progress.phase=idle`，`steps=[]`。
2. 刚有用户消息、尚无工具 checkpoint：思考步 running 或等价 thinking。
3. `discover_douyin_leads` 运行中：步骤文案为正在运行「抖音线索发现与触达」，`spin=true`。
4. `search_kb` 等普通工具：具名步骤，完成后 done 且仍保留。
5. 未知/MCP 工具：正在调用「{name}」。
6. 生图 HITL：`phase=waiting_review`，文案等待审核「生成图片」，`spin=false`。
7. Approve 后 `round_id` 不变，已有步骤不丢，可更新为正在生成图片。
8. Skip 后 `phase=done`，文案已跳过「生成图片」，步骤中**没有**进行中的整理回复。
9. 最终助手气泡返回后 `phase=done`，整理回复 done。
10. 新的用户消息产生新 `round_id`，旧步骤不再出现。
11. 聊天气泡 JSON 仍不含 tool 消息；媒体仍挂在助手气泡。

现有 HITL / 媒体 / metadata 测试必须继续通过。

### 10.2 前端

至少覆盖：

1. 侧栏存在任务框，位于目录上方。
2. 发送后本地出现「正在思考」，主气泡仍是「正在回复」。
3. 发送中会轮询 `getThread`，轮询结果不把 pending 气泡/用户消息清掉。
4. Approve 后任务栏不重置，不先变成空或只剩思考。
5. Skip 后任务栏变为已跳过/done，不会闪成思考或整理回复。
6. 正式结果气泡返回后，任务历史仍在。
7. 再发下一条用户消息后，任务栏才重置。
8. CSS 断言从 `320px` 改为 `400px`；`.agent-chat-column` 仍是 `max-width: 860px`。
9. 右栏 `overflow: hidden`，任务框和目录各自 `overflow-y: auto`。
10. HITL 时输入框仍禁用；空步骤显示 `暂无进行中的任务`。

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

- `memory-bank/architecture.md`：写明 thread JSON 的 `progress`、侧栏任务框、400px 右栏、主列 860px 居中、右栏固定与任务框自滚、HITL 同轮、Skip 收口。
- `agent_memory/context.md`、`progress.md`、`bugs.md`：只保留当前有效信息。至少记录轮询不 `applyThread`、Skip 冻结、Dify 内部节点不可见、首个 checkpoint 前思考靠前端本地步骤。

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
- 没有改 Streamlit UI。

建议中文提交信息：

```text
新增聊天右侧栏本轮任务流程
```

## 13. 验收标准

同时满足以下条件才算完成：

- 右侧栏顶部能看到本轮任务步骤，已完成步骤可上翻，当前步骤可下看到；
- 主气泡仍显示「正在回复」；
- Dify 只显示正在运行「抖音线索发现与触达」，不展示内部节点；
- LangGraph 工具具名显示并保留在本轮历史；
- Approve 不清空任务栏，本轮继续；
- Skip 后任务栏立刻结束为已跳过，不进入整理回复；
- 结果气泡返回后历史仍在，用户下一条消息才重置；
- 右栏 400px，聊天列仍按主栏 860px 居中；
- 聊天可滚、右栏不随聊天滚，任务框与目录分别自滚；
- 没有 SSE、没有新进度 endpoint、没有表结构变更；
- 前后端测试和前端构建通过；
- 已创建中文 Git commit。

## 14. 交付报告

完成后向用户说明：

1. 修改了哪些文件；
2. `progress` 如何从 checkpoint 推导；
3. 工具文案和 Dify 不可见内部节点如何处理；
4. Approve / Skip / 新用户消息分别如何影响任务栏；
5. 右栏加宽后聊天列如何保持居中；
6. 是否修改 Dify、数据库、migration 或 Streamlit；
7. 后端测试、前端测试、前端构建结果；
8. Git commit hash；
9. 尚存风险，例如首个工具 checkpoint 前只能显示本地「正在思考」。
