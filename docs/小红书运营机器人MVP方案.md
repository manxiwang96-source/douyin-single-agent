# 小红书运营机器人 MVP 方案

> 本文档是当前已锁定的套餐方案，供后续实现直接执行。标识符、环境变量、接口路径保持英文。

## 1. 摘要

基于 LangGraph get-started 1–5 做架构（StateGraph、工具、SQLite 记忆、HITL、自定义 state），**不做 time travel、不登录/发布小红书**。MVP 能力：对话写稿、简单生图、简单生视频。按六步：信息 → 提示词 → 知识库 → 工具 → 模型 → 测试发布。

硬约束：

- 媒体只写到项目 `outputs/` 子目录（已在 D 盘），禁止落到 `D:\` 或项目根。
- Demo 知识库：Markdown → LangGraph `InMemoryStore` + SiliconFlow `BAAI/bge-m3` 语义检索。
- Streamlit 薄 HTTP 客户端：聊天气泡；图/视频嵌在助手气泡内预览。
- 默认 pytest 全 mock；`RUN_LIVE_API=1` 才对 LLM / 图 / 视频 / 向量各做一次 cheapest 冒烟。

不在范围：Tavily、小红书登录/发布、time travel、六套教程功能当产品功能交付。

## 2. 已锁定决策

| 主题 | 选择 |
| --- | --- |
| UI | Streamlit 薄 HTTP 客户端 + `st.chat_input` 聊天气泡 |
| 后端 | FastAPI（合同给后续真实前端复用） |
| 人设 | 通用运营助手；平台规则在知识库；用户提供产品信息 |
| 记忆 | SQLite checkpoints + 生图/生视频前 HITL |
| HITL | 聊天区上方审核卡，可改 prompt 和生成参数，Approve / Skip；审核期间禁用聊天输入 |
| 对话模型 | Gateway `https://aitokens.website/v1`，模型 `gpt-5.6-sol` |
| 生图 | Gateway `POST /images/generations`，默认 `IMAGE_MODEL=gpt-image-2` |
| 生视频 | DashScope `wan3.0-video`（经典 `dashscope.aliyuncs.com`） |
| 成本 | 默认与测试一律 cheapest。图：`quality=low` + `1024x1536`。视频：`2s` + `480P`。参数来自配置，禁止写死 |
| 知识库 | Markdown → LangGraph `InMemoryStore` + `bge-m3` 语义检索 |
| 媒体目录 | 项目 `outputs/{images,videos}` |
| 文档 | `agent_memory/` 与 `memory-bank/` 都建 |

后续可通过 env 换模型（例如回到 `qwen-image-3.0-pro` 的 `1K` / `3:4`）。MVP 只实现 `IMAGE_PROVIDER=gateway` 和 `VIDEO_PROVIDER=dashscope`。未知组合启动失败。旧值 `VIDEO_PROVIDER=aliyun_wan3` 视为 `dashscope` 别名。

## 3. 配置 / `.env.example`

实现时第一个文件。只写 `.env.example`，不覆盖现有 `.env`。

```
OPENAI_API_KEY=
OPENAI_API_BASE_URL=https://aitokens.website/v1
OPENAI_API_MODEL=gpt-5.6-sol
IMAGE_PROVIDER=gateway
IMAGE_MODEL=gpt-image-2
IMAGE_QUALITY=low
IMAGE_SIZE=1024x1536
IMAGE_TIER_PARAM=quality
IMAGE_REQUEST_EXTRAS=
VIDEO_PROVIDER=dashscope
VIDEO_MODEL=wan3.0-video
VIDEO_DURATION=2
VIDEO_RESOLUTION=480P
VIDEO_SIZE=9:16
VIDEO_ASPECT_PARAM=ratio
VIDEO_POLL_INTERVAL_S=3
VIDEO_TIMEOUT_S=180
VIDEO_REQUEST_EXTRAS=
DASHSCOPE_API_KEY=
DASHSCOPE_WORKSPACE_ID=
DASHSCOPE_REGION=cn-beijing
DASHSCOPE_ENDPOINT=https://dashscope.aliyuncs.com/api/v1
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=
EMBEDDING_DIMS=1024
MEDIA_OUTPUT_DIR=outputs
APP_HOST=127.0.0.1
APP_PORT=8000
STREAMLIT_API_BASE=http://127.0.0.1:8000
```

补充规则：

- 切回 qwen：`IMAGE_MODEL=qwen-image-3.0-pro`，`IMAGE_QUALITY=1K`，`IMAGE_SIZE=3:4`，`IMAGE_TIER_PARAM` 按该模型字段名。
- 模型名、尺寸、时长全部来自 env，代码不写死。
- `EMBEDDING_BASE_URL` 去尾斜杠。使用 `OpenAIEmbeddings(..., check_embedding_ctx_length=False)`。
- 视频请求必须带 `resolution`（DashScope 默认 1080P，漏传会变贵）。

## 4. 媒体落盘

- `MEDIA_OUTPUT_DIR` 相对路径相对项目根。默认 `D:\iwen-codex\codex\agentdemo\outputs`。
- 启动创建 `images/`、`videos/`。文件名 `{timestamp}-{shortid}.png|.mp4`。
- 解析后若等于盘符根（如 `D:\`）或项目根，直接报错。
- `.gitignore`：`.env`、`venv/`、`data/`、`outputs/`。
- FastAPI `GET /v1/media/{images|videos}/{file}` 只从上述子目录读；正确 `Content-Type`（`image/png`、`video/mp4`）。

## 5. 知识库（向量 RAG）

- Demo Markdown：`knowledge/platform-rules.md`、`knowledge/content-structure.md`、`knowledge/visual-specs.md`、`knowledge/compliance.md`。
- 内容覆盖：标题/正文/标签规范、3:4 图、9:16 视频、合规、禁止声称已发布。
- 启动按 `##` 切块，超长二次切分（约 800 字、重叠 80）→ `InMemoryStore.put`。
- `index.embed` 包一层 `embeddings.embed_documents`，`dims=EMBEDDING_DIMS`（默认 1024）。
- 进程内索引，重启重建。Embedding 失败则启动失败（测试注入 fake embed）。
- 工具 `search_kb(query, k=4)` 返回 `source + text`。写稿前先搜 KB。

## 6. Agent / API

工具：`search_kb`、`generate_image`、`generate_video`。

- 图：Gateway `POST {OPENAI_API_BASE_URL}/images/generations`，payload `model/prompt/{IMAGE_TIER_PARAM}/size`。默认 cheapest：`quality=low` + `1024x1536`。
- 视频：DashScope `POST {DASHSCOPE_ENDPOINT}/services/aigc/video-generation/video-synthesis` + `X-DashScope-Async: enable`，再 poll `GET .../tasks/{id}`。默认 cheapest：`2s` + `480P`。
- Graph：assistant → 普通工具直接跑；生图/生视频 → `review_media` interrupt（可改 prompt 和生成参数）→ approve/skip → assistant。
- State：`MessagesState` + `last_image_path` + `last_video_path`。Checkpointer：`data/checkpoints.sqlite`。
- 人设：通用运营助手；缺产品信息先问；输出【标题】【正文】【标签】；不声称已发布。

FastAPI（无鉴权、本地 CORS）：

- `GET /health`
- `GET /v1/config`
- `POST /v1/threads`
- `GET /v1/threads/{id}`
- `POST /v1/threads/{id}/messages`
- `POST /v1/threads/{id}/resume`
- `GET /v1/media/{images|videos}/{file}`

线程消息带媒体引用：`{type: image|video, url: /v1/media/...}`。

## 7. Streamlit 聊天 UI

- 薄 HTTP 客户端，两个进程：`uvicorn` + `streamlit`。
- 主界面是聊天框：`st.chat_message("user"|"assistant")` 气泡 + 底部 `st.chat_input`。
- 助手文本直接进气泡；若消息含图片/视频，同一气泡内用 `st.image(api_url)` / `st.video(api_url)` 预览，不改成纯链接。
- 会话：`session_state.thread_id` 对应后端 thread；刷新后尽量 `GET /v1/threads/{id}` 还原气泡（含媒体 URL）。
- HITL：聊天区上方固定审核卡（可编辑 prompt + 生成参数，Approve / Skip）。审核完成前禁用 `st.chat_input`，审核控件不写入历史气泡。
- CORS 允许 Streamlit 源（默认 `http://localhost:8501`），浏览器才能加载媒体 URL。

## 8. 文档与工程纪律

- 同时建 `agent_memory/{context,progress,bugs}.md` + `archive/`（若有 `~/.codex/templates/agent_memory/` 则按模板原样）和 `memory-bank/`（vibe-coding）。
- 标识符英文；commit 中文；每次改动补测试并提交。
- 依赖（实现阶段安装）：`fastapi`、`streamlit`、`pytest`、`langgraph-checkpoint-sqlite`；现有 venv 已有 langgraph、langchain、langchain-openai、httpx、uvicorn、pydantic-settings、python-dotenv。

## 9. 测试计划

### 9.1 默认 pytest（必须全绿）

- mock chat / image / video / embedding，零真实调用。
- 断言 cheapest payload：图 `quality=low` + `1024x1536`；视频 duration=2 且带 `480P`。
- 媒体路径写入 `outputs/images|videos`；拒绝盘符根和项目根。
- fake embed 下 `search_kb` 命中相关块。
- HITL：interrupt 后 approve 才调媒体客户端，skip 不调。
- FastAPI thread/message/resume/媒体 GET；消息 JSON 含 image/video URL。
- Streamlit 不测像素，但客户端把媒体 URL 交给 `st.image` / `st.video`。

### 9.2 `RUN_LIVE_API=1` 冒烟（四类各一次，cheapest）

- 短对话走真实 `OPENAI_API_MODEL`。
- 真实生图（当前 env 的 cheapest 图参）。
- 真实生视频 `2s` + `480P`。
- 真实 `bge-m3` 检索一条 demo KB。
- 缺对应 key 则该条 skip 并说明原因，不把 live 失败当成默认套件失败。
- Live 媒体仍写入 `outputs/`，不落根目录。
- 交付前必须默认 mock 套件全绿。Live 套件人工按需跑，不作为无网络交付门槛。

## 10. 假设

- 现有 `.env` 已有 `IMAGE_MODEL=gpt-image-2` 和 SiliconFlow `EMBEDDING_*`；实现不改用户密钥。
- MVP 只实现 `IMAGE_PROVIDER=gateway` 与 `VIDEO_PROVIDER=dashscope`（含 `aliyun_wan3` 别名）。
- Tavily 不在范围。`InMemoryStore` 不持久化向量，重启重建即可。
- 后续可换前端，本轮 API 合同保持不变。
