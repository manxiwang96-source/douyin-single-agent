# 抖音运营智能体：分阶段实施入口

新开对话的 AI **先读本文件**，再读套餐正文，再读锁定设计。不要从已删除的 `stage1/` 起步。

## 文档层级（冲突时从上到下）

1. 产品锁定：`docs/modify/抖音运营智能体修改设计方案（1）.md`
2. 阶段切分与执行顺序：`stage/抖音运营智能体分阶段实施套餐.md`
3. 现网代码与 `memory-bank/architecture.md`（未落地前仍是个人超级助理）
4. 本目录其它草稿一律作废

套餐只回答「按什么顺序改、每一阶段改到哪、测什么」。表字段、状态机、Dify 输入名、侧边栏文案来源仍以修改设计方案为准。

## 新对话怎么开工

一次对话 **只做当前未完成的最小阶段**（默认从阶段 0 开始）。做完就停，更新 `agent_memory/progress.md`，中文 commit，不要连做下一阶段，除非用户明确说「继续下一阶段」。

把下面这段贴给新对话：

```text
读取 stage/README.md 和 stage/抖音运营智能体分阶段实施套餐.md。
产品决策以 docs/modify/抖音运营智能体修改设计方案（1）.md 为准。
先看 agent_memory/progress.md 里的当前阶段，只实现那一个阶段。
不要写阶段范围外的工人代码，不要改 C 的 Dify，不要把密钥写入 git / 文档 / agent_memory。
不要重建 stage1/，不要改 docs/summary/ 下的脏文件。
使用仓库 venv；改完补测试并中文 commit。
```

## 阶段索引

| 阶段 | 文件内标题 | 这一阶段产出 | 是否打真实 Dify |
| --- | --- | --- | --- |
| 0 | 文档与配置 | memory-bank、Settings、目录、prompt、demo KB、默认停调度 | 否 |
| 1 | 业务表与仓库 | SQL + 内存/Postgres 仓库 | 否 |
| 2 | 登录与广场 API | 注册登录、广场、绑定、seed、侧边栏 HTTP | 否 |
| 3 | 对话隔离 | configurable、namespace、chatbot 检索、媒体路径 | 否 |
| 4 | Dify 工具（mock） | DifyClient + discover_douyin_leads + 回写 | 否（注入 fake） |
| 5 | 任务取消 | list_jobs / cancel_job + HTTP，不跑抖音 cron | 否 |
| 6 | Streamlit 过渡客户端 | 登录/广场/侧边栏/对话，只调已有 HTTP | 否 |
| 7 | 真实 Dify 交付 | DIFY_LIVE_ENABLED=true + live smoke | 是，且 no_send=false |

## 已拍板、不要再问

- 一个工人，不是主管，不是 C 的 Dify。
- 图保持 `chatbot` + `tools`。工具 `discover_douyin_leads`，`POST /v1/workflows/run` + `DIFY_API_KEY`，`no_send=false`。
- Streamlit 做 v1 广场，但 FastAPI 必须能给后续前端直接用（Bearer）。
- 真实 `login_name` + 密码哈希登录；默认关掉晨报/喝水 APScheduler；对话里保留邮件/天气/记忆。
- 前 7 个阶段 mock Dify；阶段 7 才允许真发。C 的 `DOUYIN_HTTP_*` 可空（工作流里有默认值）。
- 一人多实例 `douyin_ops`；能力只展示不勾选；点进对话不更新卡片 `updated_at`。

## 禁止

- 把 Dify 包成 MCP，或加 `dify_comment` 节点，或 `create_react_agent`
- 采用 `difyctl` / `DIFY_COMMENT_APP_ID` / `reply_douyin_comment` / `send_douyin_dm`
- 把密钥、token、密码写进文档或记忆
- 改官方 LangGraph 表，或生产默认 SQLite
- 改同学 C 的工作流
- 把 `docs/summary/` 历史复盘或小红书 `knowledge/*.md` 当本轮材料改写