# 抖音运营智能体 Vue 前端实施套餐

> 给后续新对话的执行手册：本仓库工人 HTTP 已闭环，本套餐只做 Vue 客户端。
> 产品对错仍以 `docs/modify/抖音运营智能体修改设计方案（1）.md` 为准，尤其第 8 节广场/侧边栏。
> 工人阶段切分见 `stage/README.md` 与 `stage/抖音运营智能体分阶段实施套餐.md`（阶段 0–7 已完成，不要重做）。
> 标识符、环境变量、接口路径、表名、状态值保持英文。密钥只写本地 `.env`，不入库、不写本文档、不写 `agent_memory`。
> 例图只参考框架（广场列表、模态新建、对话+右栏），不像素还原腾讯元器。

## 0. 新对话必读

把下面这段贴给新对话（目标模式，一次完整交付）：

```text
读取 docs/modify/抖音运营智能体Vue前端实施套餐.md。
产品决策以 docs/modify/抖音运营智能体修改设计方案（1）.md 为准。
工人阶段 0–7 已完成，不要重做 Dify / 业务表 / Streamlit，不要改 C 的工作流。
本窗口一次完整交付 Vue 前端闭环：CORS、脚手架、登录、广场两步弹窗、对话+只读侧边栏，接到现有 FastAPI 能跑通。
不要停在 CORS 或脚手架；未跑通 登录→新建弹窗→卡片→对话 不算交付。
第 8 节只是本窗口内部施工顺序，不是要开 6 个对话。
使用仓库 venv 跑后端测试；前端用 frontend/ 下的 npm 脚本。
改完补测试并中文 commit。不要把密钥写入 git / 文档 / agent_memory。
```

开工顺序：

1. 读本文、修改设计方案第 8 节（广场/侧边栏）、`memory-bank/architecture.md`、`agent_memory/{context,progress,bugs}.md`。
2. 按第 8 节清单从 CORS 做到对话闭环，本窗口一次做完。
3. 可以按清单分 commit，但不要中途停工等用户说继续。
4. 整条闭环可跑后再更新 `memory-bank/architecture.md` 和 `agent_memory/progress.md`。
5. 不要重做工人，不要删 Streamlit。

本套餐实现前，仓库里还没有 `frontend/`。Streamlit 仍是过渡客户端，不要删。

## 1. 目标与成功标准

非技术人员（以及后续同学的宿主前端）能走完：

```text
登录/注册
  → 「我的智能体」广场
  → 点「新建智能体」弹出模板窗（v1 只有抖音运营助手）
  → 再在同一弹窗填名称/简介/头像（不刷新整页、不改路由）
  → 广场出现卡片（头像、名称、简介、单智能体模式、创建时间、最近编辑时间）
  → 点卡片进入对话（中间聊天 + 右侧只读侧边栏）
  → 本机 DIFY_LIVE_ENABLED=true 时，在 Vue 里手动真发一次 Dify
```

成功定义：Vue 接到现有 FastAPI，整条闭环可跑；自动化测试只 mock，不打 live。真发是手动验收，不是 pytest 门禁。

本轮做成 **可独立启动的模块页**：自带登录方便联调；广场和对话做成独立路由，方便同学以后点左侧「智能体」只贴 `/agents` 与 `/agents/:agentInstanceId`。

后端已经足够，不要重做工人阶段 0–7。

## 2. 后端事实（不要重做）

现网已经够用，Vue 直接接 Bearer JSON。错误体为 `{"detail":"..."}`。

| 能力 | 路径 | 说明 |
| --- | --- | --- |
| 注册 | `POST /v1/auth/register` | `{login_name, password}`，密码至少 8 位；201 `{user_id, login_name}` 不带 token，需再 login |
| 登录 | `POST /v1/auth/login` | 200 `{token, user_id, login_name}` |
| 登出 / 当前用户 | `POST /v1/auth/logout` `GET /v1/me` | Bearer |
| 列表 | `GET /v1/agent-instances` | `{items:[卡片]}` |
| 新建 | `POST /v1/agent-instances` | `{template_code, title, intro, avatar?}`，201 卡片 |
| 打开对话 | `POST /v1/agent-instances/{id}/open` | `{agent_instance_id, thread_id, updated_at}`；点进对话不算最近编辑 |
| 侧边栏 | `GET /v1/agent-instances/{id}/sidebar` | 描述/要点/模式/知识库文档/工作流/工具；无 model |
| 头像 | `GET /v1/agent-instances/{id}/avatar` | 需 Bearer，返回图片字节 |
| 对话 | `GET /v1/threads/{id}` `POST .../messages` `POST .../resume` | 阻塞 `ainvoke`，无 SSE |
| 媒体 | `GET /v1/media/{user_id}/{agent_instance_id}/{kind}/{file_name}` | 生图生视频预览，需 Bearer |

注册失败：空白 `login_name` 400，短密码 400，重名 409 `login_name already exists`。
登录失败：错密 401 `invalid credentials`，停用 403 `user is disabled`。
未登录业务接口 401 `not authenticated`。

卡片字段：`agent_instance_id`、`title`、`intro`、`avatar_url`、`agent_mode`、`created_at`、`updated_at`。`agent_mode` 值为 `single`，界面展示「单智能体模式」。

侧边栏字段：`capability_description`、`development_notes`、`agent_mode` / `agent_mode_label`、`knowledge_documents[].title|filename`、`workflows[].code|display_name`、`tools[].name|display_name|user_facing_summary`。不要把 `SYSTEM_PROMPT` 贴到侧边栏。

名称规则（后端已执行，前端要提前校验并展示错误）：

- 去首尾空白后非空
- 不能含空格或其他空白（400 `title must not contain whitespace`）
- 当前用户未归档实例里大小写不敏感唯一
- 空白 400 `title must not be blank`，冲突 409 `title already in use`

头像：JSON 里的 base64（可带 `data:image/...;base64,`），不是 multipart。可空。解码后上限 1MB。头像 URL 与媒体 URL 都要带 Bearer，用 blob 预览，不要把 token 写进可分享链接。

新建 `douyin_ops` 会自动绑定 `douyin-lead-discovery` 并 seed demo 知识库（`faq.md` 等）。Vue 知识库板块 **列出文档名**，不开放上传。没有文档时板块仍要在。

没有 `GET /v1/templates`。模板窗前端写死 `douyin_ops` / 「抖音运营助手」。

`POST /v1/threads` 不是产品入口，不要调用（会 400 `use POST /v1/agent-instances/{id}/open`）。

v1 界面不要做改名 PATCH、任务取消页、发布/未发布。

默认 CORS 只放行 Streamlit `8501`。Vue 本地 `5173` 必须补源，这是一次交付里的第一步。现网 `CORSMiddleware` 为 `allow_credentials=True`，不能改成 `*`。

对话超时：Streamlit 客户端是 180s；Dify 阻塞上限是 `DIFY_TIMEOUT_S=300`。Vue Axios 超时用 **180000** 对齐现客户端；若手动真发被前端掐断，再升到 300000。全程展示 loading。无 SSE。

`status==interrupted` 时禁止发新消息（后端 409 `thread is waiting for review`），只允许 HITL `resume`。

## 3. 全程锁定

- 不改工人图，不改 C 的 Dify，不改业务表，不改 Streamlit，不把 Dify 包成 MCP。
- 应用描述用 `capability_description`，禁止把 `SYSTEM_PROMPT` 贴到侧边栏。
- 模式展示「单智能体模式」；界面可出现「多智能体模式」这个词，但禁用、不可切。
- 不做广场标签、收藏、未发布、状态筛选、AI 生成头像、上传图/文件进对话框。
- 新建必须在广场上，两步同一弹窗，不刷新整页，不改路由。
- 例图只参考框架。卡片字段按产品：单智能体模式 + 创建时间 + 最近编辑时间。
- 技术栈：Vue 3 + Vite + Vue Router + Pinia + Axios。**轻量自定义组件**，不要引入 Element Plus / Naive UI / Ant Design Vue。
- CSS 模块化前缀必须 `agent-`，用 scoped，方便给同学粘贴。
- 本仓库自带登录/注册。同学嵌入时只取 `/agents` 与 `/agents/:agentInstanceId`，由宿主注入 Bearer token。
- 自动化测试禁止 `RUN_LIVE_DOUYIN=1`。Vue 真发只手动。
- 密钥、token、密码不写入文档、测试、仓库里的非 `.env` 文件、`agent_memory`。

## 4. 例图框架对照

用户给的四张例图是腾讯元器截图。**仅参考框架**，不要像素还原，不要把元器文案/能力搬过来。

| 例图 | 对应产品 | 抄框架 | 不要抄 |
| --- | --- | --- | --- |
| 例图1 | 广场 `/agents` | 页标题「我的智能体」；蓝色「+ 新建智能体」；右上搜索；卡片网格：头像、名称、简介、模式、时间 | 「未发布」角标、「状态」筛选、「标准模式」、底部分页、「共 N 项」 |
| 例图2 | 广场上的新建弹窗第 1 步 | 遮罩 modal、标题「新建智能体」、关闭 X、模板卡片 | 「公众号智能体」「对话式智能体」、底部「发布到腾讯元器/微信」 |
| 例图3 | 同一弹窗第 2 步 | 名称\* 0/30、简介\* 0/150、右侧本机上传头像、新建/取消 | 「AI生成头像」、机关国企审核说明、标题写成「新建对话式智能体」 |
| 例图4 | 对话 `/agents/:agentInstanceId` | 返回广场、顶栏头像+名称、中间对话、右侧只读栏 | 「复制智能体」、体验链接、模型栏、输入框图片/文件按钮、聊天区「包含文档」、水印 |

v1 模板卡片只有一张：标题「抖音运营助手」，说明可写「围绕抖音账号和话题做运营规划，并通过已绑定工作流做线索发现与真实触达」。后续自定义智能体才写成「对话式智能体」，本套餐不要做。

## 5. 页面与交互

### 5.1 登录页 `/login`

- 同一页可切换：登录 / 注册。
- 注册成功后立刻 login，token 写入 `localStorage`，进 `/agents`。
- 未登录访问广场/对话一律重定向 `/login`。
- 登出清 token，回登录。不要做整站左侧导航。

### 5.2 广场 `/agents`（同学嵌入页；对标例图 1 框架）

- 页标题「我的智能体」。
- 蓝色「+ 新建智能体」。
- 前端关键字过滤当前列表，不要新增搜索 API。
- 不要状态筛选、未发布标签、收藏、模型筛选、分页（当前一人实例少，不必封装后端分页）。
- 卡片：头像、名称、简介、「单智能体模式」、创建时间、最近编辑时间。
- 点卡片：`POST /open` 后路由 `/agents/:agentInstanceId`，query 或 store 保存 `thread_id`。
- 可在右上做退出登录，不要做整站壳。

### 5.3 新建弹窗（对标例图 2、3；必须是 modal）

同一层遮罩，关闭后停在 `/agents`。

1. 只有一张模板卡：「抖音运营助手」。不要第二张「对话式智能体」，不要元器那两张示例卡。
2. 点该卡后仍在该弹窗：名称\* 0/30，简介\* 0/150，右侧本机上传头像。不要「AI生成头像」。
3. 名称禁止空白字符；提交 `template_code=douyin_ops`；成功关闭弹窗并 `GET /v1/agent-instances`。
4. 409 把 `title already in use` 显示成用户能看懂的「名称已被使用」。

### 5.4 对话页 `/agents/:agentInstanceId`（对标例图 4 框架）

- 顶栏：返回广场、实例头像、名称。不要「复制智能体」。
- 中间：历史消息、文本输入、发送中 loading、HITL 审核卡（Approve / Skip），行为对齐 Streamlit：`ui/view_model.py` 的 `build_chat_view` / `interrupt_card`。
- 右侧只读：
  - 应用描述 ← `capability_description`
  - 应用开发要点 ← `development_notes`
  - 应用设置 / 模式：单智能体模式；多智能体模式可见但禁用
  - 知识库：列出文档名；没有也要保留板块
  - 工作流：显示目录展示名（同学 C 的 Dify，`douyin-lead-discovery` / 「抖音线索发现与触达」）
  - 工具：显示 `display_name`（如「抖音线索发现」），可用 `user_facing_summary` 做说明
- 去掉模型栏、体验链接。输入框不要图片/文件按钮。

HITL：`interrupt.type==review_media` 时展示卡；`approve` 带上 prompt/params，`skip` 不带媒体。interrupted 时禁用输入。

## 6. HTTP 契约（照此接线，不要发明）

鉴权头：`Authorization: Bearer <token>`。

新建：

```json
{"template_code":"douyin_ops","title":"我的助手","intro":"简介","avatar":"data:image/png;base64,..."}
```

`avatar` 可省略。`template_code` 必须是 `douyin_ops`。

打开：

```json
{"agent_instance_id":"...","thread_id":"...","updated_at":"..."}
```

线程：

```json
{
  "id": "...",
  "status": "idle",
  "messages": [{"role":"user","content":"...","media":[]}],
  "interrupt": null,
  "last_image_path": null,
  "last_video_path": null
}
```

发消息：`POST /v1/threads/{id}/messages` body `{"content":"..."}`。
恢复：`POST /v1/threads/{id}/resume` body `{"action":"approve","prompt":"...","params":{}}` 或 `{"action":"skip"}`。

侧边栏不要出现 `model` 字段；前端也不要自己加模型栏。

## 7. 目录与工程约定

在仓库根新增 `frontend/`，不要写进 `ui/`（Streamlit 保留）。

建议结构（实现时可微调，但职责不要混）：

```text
frontend/
  package.json
  vite.config.ts          # dev server 5173；proxy /v1 -> http://127.0.0.1:8000
  index.html
  src/main.ts
  src/App.vue
  src/styles/agent.css    # 蓝白框架变量，class 前缀 agent-
  src/api/http.ts         # Axios 实例、Bearer、401 清 token
  src/api/auth.ts
  src/api/agents.ts
  src/api/threads.ts
  src/stores/auth.ts
  src/router/index.ts
  src/views/LoginView.vue
  src/views/PlazaView.vue
  src/views/ChatView.vue
  src/components/CreateAgentModal.vue
  src/components/AgentCard.vue
  src/components/ChatSidebar.vue
  src/components/HitlCard.vue
  src/lib/title.ts        # 与后端一致的名称校验
  src/lib/avatar.ts       # File -> base64
  tests/                  # Vitest
```

`.gitignore` 增加 `frontend/node_modules/`、`frontend/dist/`。

`vite.config.ts`：`server.port=5173`，`server.proxy['/v1']` 指向后端。前端默认 `VITE_API_BASE=""` 走同源 proxy；直连后端时才用绝对 URL。

启动（实现完成后写进 README，按此验证）：

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
cd frontend
npm run dev
```

## 8. 一次交付的施工顺序

一次完整交付。下面 阶段 0–5 只是本窗口内部施工顺序，不是要你开 6 个对话。按序做完；未跑通登录→新建→对话不算成功。

### 阶段 0 — CORS 放行 Vite

目标：浏览器从 `5173` 能调 `8000`。

做：

- `app/config.py` 默认 `cors_origins` 增加 `http://localhost:5173,http://127.0.0.1:5173`，保留原 Streamlit `8501`。
- `.env.example` 如需暴露该变量则同步，不要改用户 `.env` 里的密钥。
- `tests/test_config.py` 断言默认列表含 5173 与 8501。

CORS 是清单第一步，做完立刻继续脚手架，不要在这一步停下来等用户。

提交中文：`放行 Vue 开发服务器跨域来源`。

### 阶段 1 — 前端脚手架与鉴权客户端

目标：`frontend/` 能启动，请求能带 Bearer。

做：

- 初始化 Vue 3 + Vite + TS + Vue Router + Pinia + Axios + Vitest。
- `http.ts`：超时 180000；从 `localStorage` 读 token；401 清会话。
- 纯函数测试：token 头、401 处理、`create_instance` payload 锁 `douyin_ops`、名称空白拒绝。

提交中文：`搭建 Vue 模块脚手架与鉴权客户端`。

### 阶段 2 — 登录注册

目标：能拿到 session，进不了广场则重定向。

做：`LoginView` 调 register/login/logout/me。路由守卫。Vitest 覆盖未登录不能进 `/agents`。

提交中文：`用 Vue 接登录注册并守卫广场路由`。

### 阶段 3 — 广场与新建弹窗

目标：一人多实例可见，两步 modal 不改路由。

做：`PlazaView` + `CreateAgentModal` + `AgentCard`。搜索前端过滤。创建成功刷新列表。测试：弹窗两步、payload、409 文案、卡片字段映射。

提交中文：`用 Vue 实现智能体广场与新建弹窗`。

### 阶段 4 — 对话页与只读侧边栏

目标：点卡片能聊，侧边栏只读且字段正确。

做：`ChatView` + `ChatSidebar` + `HitlCard`。`open` → 拉 thread 与 sidebar。interrupted 禁用输入。媒体 URL 走 Bearer 拉 blob 或带 token 的绝对地址。测试：侧边栏含描述/要点/文档名/工作流/工具且无 model；HITL 时不能发新消息。

提交中文：`用 Vue 接对话页与只读侧边栏`。

### 阶段 5 — 收尾与手动真发

目标：独立可跑，架构文档跟上。

做：

- README 增加 Vue 启动命令。
- `memory-bank/architecture.md` 写明入口是 Vue 广场模块，Streamlit 仍是过渡客户端。
- 手动：登录 → 弹窗新建 → 点卡片 → 侧边栏可见工作流「抖音线索发现与触达」和工具名 → 发一条会调 `discover_douyin_leads` 的话。仅当本地 `DIFY_LIVE_ENABLED=true` 时真发；缺配置不要把 skip 写成交付成功。
- 默认 pytest + 前端 Vitest 全绿。

提交中文：`接通 Vue 智能体闭环并更新现网架构说明`。

## 9. 测试与验收

- 文档锁：`tests/test_vue_frontend_playbook_doc.py`（本文件存在且锁定决策未被改丢）。
- 阶段 0：pytest 断言 CORS 默认含 `http://localhost:5173` 与 `http://127.0.0.1:5173` 以及 8501。
- 阶段 1–4：Vitest 覆盖鉴权、名称校验、`douyin_ops` payload、两步弹窗、侧边栏字段、HITL 禁用输入。
- 不要用 Playwright 打 live Dify。不要在 CI 设 `RUN_LIVE_DOUYIN=1`。
- 对照 Streamlit 行为时读 `ui/view_model.py`，不要把 Streamlit 页面逻辑复制进 Vue。

## 10. 明确不做

- 抖音 8 点调度、用户上传知识库、自定义智能体、勾选工具、切换多智能体模式
- 评论/私信待审 API、按用户一人一把 Dify Key
- Playwright 打 live、给同学做整站左侧导航
- 改 `docs/summary/` 脏文件、重建 `stage1/`、把 Streamlit 删掉
- 引入 Element Plus / Naive UI / Ant Design Vue
- 重做工人阶段 0–7、改 C 的工作流、把 Dify 包成 MCP

## 11. 假设与风险

- 同学宿主前端也是 Vue，稍后只贴 `/agents` 与对话页；本轮必须能独立跑。
- 对话无流式，长耗时 Dify 只靠超时和 loading。
- 取消任务页 v1 不做；生图生视频 HITL 要保留。
- 飞书 bot 与本工人可能双发，手动真发前与 C 错开。
- 现网默认 CORS 还只有 8501；交付时必须补 5173。同源 Vite proxy 可辅助联调，但不能代替 CORS 修改。
