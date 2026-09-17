# 小红书运营助手对话机器人 MVP 总结与逻辑复盘（1）

> 对应仓库：`D:\\iwen-codex\\codex\\agentdemo`  
> 对照方案：`docs/小红书运营机器人MVP方案.md`  
> 对照架构教程：LangGraph get-started 1–5（基础聊天机器人、工具、记忆、HITL、自定义状态）  
> 文档时点：2026-09-17，代码基线 `a383fb6`

本文只复盘已经落地的 MVP，不扩新功能。标识符保持英文，叙述用中文。

---

## 1. 一句话结论

这是一个**本地双进程**的小红书运营助手：用户在 Streamlit 聊天里给产品事实，后端 LangGraph 先检索 Demo 知识库再写稿；只有用户明确要求配图/视频时，才在工具内部 `interrupt()` 等人审，通过后按 cheapest 参数生成媒体并在聊天气泡里预览。系统**不能登录、不能发布**小红书。

当前默认 mock 测试全绿；`RUN_LIVE_API=1` 的四类真实接入冒烟也曾通过。对话模型名由 `.env` 的 `OPENAI_API_MODEL` 决定，改名不改代码，但必须重启 FastAPI 才会生效。

---

## 2. 产品边界

### 2.1 做了什么

| 能力 | 实际行为 |
| --- | --- |
| 对话写稿 | 缺产品/人群/卖点先追问；写稿前必须 `search_kb`；输出 `【标题】【正文】【标签】` |
| 廉价生图 | Gateway `POST /images/generations`，默认 `gpt-image-2` + `quality=low` + `1024x1536`（3:4） |
| 廉价生视频 | DashScope 异步 `video-synthesis` + poll，默认 `2s` + `480P` + `ratio=9:16` |
| 人工审核 | 仅生图/生视频前暂停；可改 prompt 和参数；Approve 才调媒体 API，Skip 不调 |
| 会话记忆 | 生产用 SQLite checkpointer；同一 `thread_id` 可续聊 |
| 媒体预览 | FastAPI 提供 `/v1/media/{images|videos}/{file}`；Streamlit 用 `st.image` / `st.video` |

### 2.2 明确不做

- 不接 Tavily / 外网检索
- 不登录、不发布、不投放小红书
- 不做 time travel / 状态回放产品能力
- 不把教程章节本身当成产品功能
- 不把教程里的并行工具调用搬进来（`parallel_tool_calls=False`）
- 知识库不落盘：`InMemoryStore`，进程重启重建索引

---

## 3. 进程与模块分层

运行时永远是两个进程：

1. FastAPI：`uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000`
2. Streamlit：`streamlit run ui/streamlit_app.py`，默认打 `http://127.0.0.1:8000`

```text
用户
  └─ Streamlit（薄 HTTP 客户端，不持有 Graph）
        └─ FastAPI 合同
              └─ AppRuntime
                    ├─ ChatOpenAI（OpenAI 兼容网关）
                    ├─ StateGraph：chatbot + tools
                    ├─ InMemoryStore（bge-m3 / 测试 hashing）
                    ├─ SqliteSaver（data/checkpoints.sqlite）
                    ├─ ImageClient → Gateway
                    └─ VideoClient → DashScope
```

关键文件：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 配置 | `app/config.py` | env、cheapest 默认、provider 白名单 |
| 图 | `app/graph.py` | `chatbot` + `ToolNode` + `tools_condition` |
| 工具 | `app/tools.py` | `search_kb` 立即执行；媒体工具内部 interrupt |
| 人设 | `app/prompts.py` | 追问、KB、三段输出、禁止声称已发布 |
| 运行时 | `app/runtime.py` | 装配 LLM / store / checkpointer / clients |
| 合同 | `app/main.py` + `app/serialize.py` | 线程、消息、resume、媒体 URL |
| 知识库 | `app/knowledge.py` + `knowledge/*.md` | `##` 切块，约 800/80 |
| UI | `ui/streamlit_app.py` + `ui/view_model.py` | 气泡、HITL 卡、pending 回显 |

`create_app(runtime=None)` 是工厂：导入 `app.main` **不会**启动真实 embedding。测试注入 fake LLM / fake 媒体客户端 / hashing embed。

---

## 4. Graph 逻辑复盘（对照教程 1–5）

教程被压缩成**两个节点**，没有单独的 `review_media` / `run_media` 节点。测试明确断言图上只有 `chatbot` 和 `tools`。

```text
START
  └─ chatbot
        ├─ tools_condition == tools ─► tools ─► chatbot
        └─ tools_condition == END   ─► END
```

对应关系：

| 教程 | 本仓库落地 |
| --- | --- |
| 1 基础聊天机器人 | `chatbot` 调 `bound.invoke([SystemMessage, *messages])` |
| 2 工具 | `search_kb` / `generate_image` / `generate_video` + `ToolNode` |
| 3 记忆 | `SqliteSaver`（生产）/ `InMemorySaver`（测试），`thread_id` |
| 4 HITL | `interrupt()` 写在媒体工具函数内部，resume 用 `Command(resume=...)` |
| 5 自定义状态 | `AgentState = messages + last_image_path + last_video_path` |

`chatbot` 绑定工具时强制 `parallel_tool_calls=False`，并 `assert len(tool_calls) <= 1`。原因：并行 tool_call 在 interrupt/resume 时可能重跑工具，媒体会重复计费。

---

## 5. 三条主路径

### 5.1 只写稿（无媒体）

1. 用户发消息 → `POST /v1/threads/{id}/messages`
2. Graph `invoke({messages: [HumanMessage]})`
3. `chatbot`：若缺产品事实，直接追问，不调工具
4. 信息足够时先 `search_kb`；`ToolNode` 立即检索，**不 interrupt**
5. 回到 `chatbot`，按 KB + 用户事实输出 `【标题】【正文】【标签】`
6. 序列化时 ToolMessage 不进气泡，只把最终 AI 文本给前端

系统提示词硬约束：写稿前必须检索；禁止编造功效、评价、销量；禁止声称已登录/已发布。

### 5.2 生图（HITL）

1. 仅当用户**明确要求配图**时，模型才应调 `generate_image(prompt)`
2. 工具一进函数就 `interrupt({type: review_media, tool, prompt, params})`
3. FastAPI 把 snapshot 标成 `status=interrupted`；此时再发消息返回 409
4. Streamlit 在聊天区上方出审核卡：可编辑 prompt 和 Params JSON，输入框禁用
5. Approve → `Command(resume={action, prompt, params})` → Gateway 生图 → 写入 `outputs/images/{timestamp}-{shortid}.png`
6. 工具用 `Command(update=...)` 同时写入 `last_image_path` 和带 `url` 的 ToolMessage
7. Skip / reject / cancel **不调用** ImageClient，只回 `User skipped media generation.`

默认 cheapest 参数来自 Settings，不写死在工具里：`model/quality/size`，HITL 里改的 params 会覆盖默认值。

### 5.3 生视频（HITL）

与生图同构，区别只在客户端：

1. `POST {DASHSCOPE_ENDPOINT}/services/aigc/video-generation/video-synthesis`，头必须带 `X-DashScope-Async: enable`
2. payload 的 `parameters` 必须含 `duration=2`、`resolution=480P`、`ratio=9:16`（漏 `resolution` 会落到更贵默认档）
3. poll `GET .../tasks/{id}`，成功后下载 mp4 到 `outputs/videos/`

视频比写稿慢一个数量级，属预期，不是 Graph 卡死。

---

## 6. 状态、序列化与前端回显

### 6.1 状态

```text
AgentState
  messages: add_messages
  last_image_path?: str
  last_video_path?: str
```

生产 checkpointer：`data/checkpoints.sqlite`（gitignore）。  
测试：`InMemorySaver`，不碰真实 SQLite。

注意：Streamlit 的气泡历史在浏览器 `session_state`；重启页面后若没有同一 `thread_id`，UI 不会自动把旧会话拉回来。后端 checkpoint 仍在，只是前端没有会话列表。

### 6.2 消息如何变成聊天气泡

`serialize.py` 的规则：

- `HumanMessage` → user 气泡
- 带 `tool_calls` 的 `AIMessage` → 跳过（不把“我要调工具”暴露给用户）
- `ToolMessage`：若 JSON 含 `ok + type + url`，把媒体缓冲起来；否则丢弃
- 下一条纯文本 `AIMessage` 带上缓冲的 media
- 若媒体已经生成但还没有后续文本，补一条空文本助手气泡，保证图/视频仍能预览

因此 HITL 审核卡**不是**历史气泡的一部分。`view_model.interrupt_card()` 单独渲染。

### 6.3 Streamlit pending 回显

真实模型调用经常 10s–1min。`st.chat_input` 提交后会立刻清空输入框；若等 `POST` 返回再画气泡，用户会感觉“我刚打的字没了”。

修复：`session_state.pending_user` + `with_pending_user()` 立即回显用户气泡，并显示「正在回复...」。API 成功后再清 pending 并 rerun。这是联调阶段修过的真实 UX 问题，不是方案原文里的条目。

---

## 7. 知识库

目录：`knowledge/`

| 文件 | 作用 |
| --- | --- |
| `platform-rules.md` | 标题 20 字内、正文短句、标签 5–10 个 |
| `content-structure.md` | 必须 `【标题】【正文】【标签】`，缺信息先问 |
| `visual-specs.md` | 图 3:4、视频 9:16、封面建议 |
| `compliance.md` | 禁止绝对化用语、禁止声称已发布、不编造评价 |

切块：按 `##` 分段，超长再按约 800 字、重叠 80 切。  
索引：`InMemoryStore`，`fields=["text"]`，`dims=EMBEDDING_DIMS`（默认 1024）。  
线上 embedding：SiliconFlow `BAAI/bge-m3`。启动时索引 0 条则直接失败。  
测试：`hashing_embed_documents`，不打真实 embedding。

`search_kb` 过滤 `score <= 0` 的命中；无命中返回字符串 `NO_HITS`。

---

## 8. FastAPI 合同

无鉴权，本地 CORS 默认允许 `http://localhost:8501` 与 `http://127.0.0.1:8501`。

| 方法 | 路径 | 含义 |
| --- | --- | --- |
| GET | `/health` | `{status: ok}` |
| GET | `/v1/config` | 公开 cheapest 配置（不含密钥） |
| POST | `/v1/threads` | 创建 `thread_id` |
| GET | `/v1/threads/{id}` | 序列化后的气泡 + interrupt |
| POST | `/v1/threads/{id}/messages` | 发用户消息；interrupted 时 409 |
| POST | `/v1/threads/{id}/resume` | `{action, prompt, params}`；非 interrupted 时 409 |
| GET | `/v1/media/{images|videos}/{file}` | 只读子目录，防 `..` 逃逸 |

媒体路径铁律：解析后不能是盘符根（如 `D:\\`），也不能是项目根。文件名 `{YYYYMMDDTHHMMSS}-{8位hex}.png|.mp4`。

改 `.env` 里的模型名（例如改成 `grok-4.6`）**不需要改代码**；`Settings` 启动时读一次，所以必须重启 uvicorn。Streamlit 不必因模型名重启，除非改了 `STREAMLIT_API_BASE`。

---

## 9. 与方案文档的对照

方案原文里 Graph 曾写成 `assistant → 普通工具直接跑；生图/生视频 → review_media interrupt`。落地时按教程 4 把 interrupt **放进工具函数**，而不是单独节点。这是有意对齐官方 get-started，不是漏实现。

其它锁定项均已落地：

- cheapest 图：`quality=low` + `1024x1536`
- cheapest 视频：必须带 `resolution=480P`
- 视频时长默认 2 秒
- 媒体只进 `outputs/images` 与 `outputs/videos`
- Streamlit 不把媒体降级成纯链接
- 默认 pytest 全 mock；live 冒烟靠 `RUN_LIVE_API=1`

尚未做、且方案也没要求做成产品能力的：流式输出。当前链路是 `graph.invoke` + 阻塞 POST。要做流式需要 SSE/`graph.stream`，不是改一个开关；KB 工具和 HITL 暂停仍然在。

---

## 10. 测试与联调记录

### 10.1 默认套件

`pytest` 默认不打真实 API。覆盖：

- cheapest payload
- 媒体路径拒绝盘符根/项目根
- fake embed 下 KB 能命中相关块
- HITL approve 才调客户端，skip 不调
- FastAPI 线程/409/媒体 Content-Type
- Streamlit view model 把绝对 URL 交给 `st.image` / `st.video`
- pending 用户气泡立即回显

最近一次全量 mock：**38 passed，4 skipped**（live 四条默认 skip）。

### 10.2 真实接入

```powershell
$env:RUN_LIVE_API=1
.\\venv\\Scripts\\python.exe -m pytest tests/test_live_api.py
```

四类各一次：短对话、cheapest 生图、cheapest 生视频、bge-m3 检索。缺 key 则 skip，不把 live 失败算进默认交付门槛。

联调产物曾落到：

- `outputs/images/20260916T175029-9ed06932.png`
- `outputs/videos/20260916T175233-6511cbe4.mp4`

`outputs/` 被 gitignore，不提交。

### 10.3 手工验收用例（页面）

**写稿，不触发 HITL**

> 帮我写一条敏感肌保湿精华的小红书笔记。卖点：敏感肌可用、清爽不黏、长效保湿。人群：敏感肌。不要配图，不要视频。

预期：先检索再给 `【标题】【正文】【标签】`；无审核卡；无媒体。

**只要封面图**

> 给这款敏感肌保湿精华生成一张 3:4 小红书封面图，只要配图，不要写笔记，不要视频。

预期：审核卡 `tool=generate_image`，params 含 `quality=low`、`size=1024x1536`；Approve 后气泡出图；Skip 无文件。

---

## 11. 已修问题与仍开放风险

### 已关闭

- 导入 `app.main` 曾在 pytest 时触发真实 embedding。改为纯工厂，测试注入 runtime。
- 发送后用户消息要等 API 返回才出现。用 `pending_user` 立即回显。

### 仍开放

- 写稿慢（常见 10s–1min，网关极端可到约 2min）是模型+KB 工具耗时，HTTP timeout 180s。
- 向量索引不持久，重启 FastAPI 会重建；embedding 失败则启动失败。
- Streamlit 重启后 UI 会话丢失，旧 `thread_id` 不会自动列出来。
- 当前非流式；HITL 期间必须停住，不能边生成边审。
- live 媒体费用与网关稳定性不是 mock 套件能担保的。

---

## 12. 启动与提交纪律

```powershell
.\\venv\\Scripts\\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
.\\venv\\Scripts\\python.exe -m streamlit run ui/streamlit_app.py
.\\venv\\Scripts\\python.exe -m pytest
```

不要覆盖或提交 `.env`、`venv/`、`outputs/`、`data/`。commit 用中文概括；标识符保持英文。

本篇是第（1）份复盘，覆盖 MVP 落地、教程对齐、三条主路径、测试与联调结论。后续若做流式、会话列表或换前端，另开（2）。
