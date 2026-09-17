# LangGraph 智能体创建知识地图：多智能体协作与任务编排

> 资料来源：[LangGraph 中文文档](https://langgraph.com.cn/)
> 整理日期：2026-09-17
> 阅读目标：从“会调用模型”进阶到“能够设计、实现、测试并运行可控的智能体系统”。

---

## 1. 核心结论

使用 LangGraph 创建智能体，重点不只是提示词工程，而是围绕大模型构建一套**有状态、可编排、可恢复、可观测的控制流系统**。需要掌握的知识可归纳为六层：

1. **模型与工具基础**：消息、提示词、结构化输出、工具调用和 ReAct 循环。
2. **图与状态建模**：`State`、`Node`、`Edge`、Reducer、条件路由、`Send`、`Command`、Subgraph。
3. **任务编排**：顺序、并行、路由、规划—执行、编排器—工作者、评估—优化等工作流。
4. **多智能体协作**：Supervisor、Network、Handoff、层级团队，以及代理间的上下文边界和通信协议。
5. **上下文与记忆**：运行配置、短期状态、持久化检查点、长期存储，以及上下文裁剪。
6. **生产化能力**：人工介入、错误恢复、幂等、流式输出、可观测性、评估与部署。

一句话概括：**智能体开发是“以 LLM 参与决策的状态机和工作流工程”，多智能体则是在此基础上进一步解决职责划分、协作协议和任务所有权问题。**

---

## 2. 创建智能体需要侧重的知识

### 2.1 大模型、消息与工具调用

先理解单智能体最小闭环：

```text
用户消息 → 模型判断 → 调用工具 → 工具返回结果 → 模型继续判断 → 输出答案或结束
```

应重点掌握：

- `SystemMessage`、`HumanMessage`、`AIMessage`、`ToolMessage` 的职责和顺序。
- 提示词如何规定角色、边界、输出格式和停止条件。
- 使用结构化输出约束分类、路由、计划和评估结果。
- 工具的输入 Schema、输出格式、副作用、超时、重试和异常表达。
- ReAct 循环何时继续调用工具，何时结束，如何避免无限循环。
- 对高风险工具设置审批、权限和幂等保护。

学习入口：

- [构建基础聊天机器人](https://langgraph.com.cn/tutorials/get-started/1-build-basic-chatbot/index.html)
- [向聊天机器人添加工具](https://langgraph.com.cn/tutorials/get-started/2-add-tools/index.html)
- [工具（Tools）](https://langgraph.com.cn/agents/tools.1.html)
- [智能体架构概念](https://langgraph.com.cn/concepts/agentic_concepts.1.html)

### 2.2 LangGraph 图模型与状态管理

LangGraph 的核心不是“多个 Prompt 串在一起”，而是显式图模型：

- **State**：图运行期间共享的数据契约，例如消息、计划、检索结果、任务状态和错误。
- **Node**：执行模型调用、工具调用、校验、人工审批或普通业务逻辑。
- **Edge**：确定节点执行顺序。
- **Conditional Edge**：根据结构化判断进行分支或循环。
- **Reducer**：定义多个节点更新同一状态字段时如何合并。
- **`Send`**：动态创建并行分支，适合 map-reduce 或编排器—工作者模式。
- **`Command`**：在一个返回值中同时更新状态和指定下一跳，也可用于代理间 Handoff。
- **Subgraph**：封装独立工作流或专业智能体，并定义父图与子图的状态边界。

关键设计原则：

1. 状态字段应是清晰的业务事实，不要把所有临时信息都塞进 `messages`。
2. 节点职责要单一，节点输入输出要可测试。
3. 能用确定性规则表达的流程，不要全部交给模型路由。
4. 每个循环都要有最大步数、完成标记或明确终止条件。
5. 并行写入同一字段时必须设计 Reducer，避免覆盖或合并歧义。

学习入口：

- [低层级概念：图、状态、节点与边](https://langgraph.com.cn/concepts/low_level.1.html)
- [自定义状态](https://langgraph.com.cn/tutorials/get-started/5-customize-state/index.html)
- [子图](https://langgraph.com.cn/concepts/subgraphs.1.html)

### 2.3 任务编排模式

任务编排关注的是：**任务如何拆分、依赖如何表达、执行顺序如何决定、失败后从哪里恢复、结果如何聚合。**

| 模式 | 核心结构 | 适用场景 | 主要风险 |
| --- | --- | --- | --- |
| Prompt Chaining | A → B → C | 步骤固定、后一步依赖前一步 | 前序错误逐步放大 |
| Parallelization | A → B1/B2/B3 → 汇总 | 子任务相互独立 | 并发成本、合并冲突 |
| Routing | 分类器 → 专用分支 | 输入类型明确、处理流程不同 | 错误路由、类别漂移 |
| Orchestrator-Worker | 编排器拆任务 → 工作者并行 → 汇总 | 子任务数量或内容运行时才能确定 | 拆分质量、重复工作 |
| Evaluator-Optimizer | 生成 → 评价 → 修改 | 有明确质量标准且允许迭代 | 循环不收敛、成本失控 |
| Autonomous Agent | 模型自行决定下一步 | 开放式问题、路径难预设 | 不可控、难复现、难估算成本 |

编排设计时应明确：

- 任务 DAG、前置依赖和可并行部分。
- 每项任务的输入、输出、负责人、完成标准和超时。
- 重试针对的是节点、工具还是整个工作流。
- 失败状态、补偿逻辑和恢复入口。
- 聚合规则以及部分成功时的处理策略。
- 最大迭代次数、Token/费用预算和总执行时限。

建议优先采用**确定性的工作流骨架 + 局部受限的智能体决策**。只有执行路径确实无法预先定义时，才扩大模型自主权。

深入学习：

- [工作流与智能体教程：六种编排模式](https://langgraph.com.cn/tutorials/workflows/index.html)
- [低层级概念：条件边、Send 与 Command](https://langgraph.com.cn/concepts/low_level.1.html)
- [子图：封装可复用任务或智能体](https://langgraph.com.cn/concepts/subgraphs.1.html)

### 2.4 多智能体协作

多智能体不是简单地“多创建几个 Agent”，真正的难点是定义：

- **责任边界**：每个代理负责什么、不负责什么。
- **任务所有权**：当前任务由谁持有，谁有权宣告完成。
- **通信协议**：代理传递自然语言、结构化对象，还是状态字段。
- **上下文范围**：共享完整历史、摘要、任务单，还是仅共享最终结果。
- **Handoff 载荷**：转交时必须包含目标、已有事实、约束、期望输出和返回地址。
- **终止条件**：何时回到 Supervisor，何时交给用户，何时结束整个图。

常见拓扑：

#### Network

每个代理可把控制权交给其他代理。适合协作关系动态、中心协调较弱的任务；缺点是容易产生环路，调试困难。

#### Supervisor

中心 Supervisor 选择下一个专业代理，并汇总最终结果。适合职责明确、需要统一调度和审计的系统，是业务项目中较容易控制的起点。

#### Tool-calling Supervisor

将专业代理包装成 Supervisor 可调用的工具。接口清晰、输出容易结构化，也便于限制代理看到的上下文。

#### Hierarchical

上层 Supervisor 管理多个团队，下层 Supervisor 再管理团队内代理。适合复杂组织或大型任务，但应避免为了形式而增加层级。

#### Custom Workflow

用普通节点、确定性逻辑和代理节点混合构图。生产系统通常最实用，因为可以把高风险步骤做成确定性流程，把开放性步骤交给模型。

多智能体上下文建议：

- 默认让每个代理保留自己的内部消息历史。
- 跨代理优先共享必要的结构化结果，而不是完整思维过程和全部对话。
- 用统一任务 Schema，例如 `task_id`、`objective`、`constraints`、`inputs`、`owner`、`status`、`result`、`error`。
- Supervisor 不应重复完成 Worker 的专业工作，只负责任务分配、状态跟踪、冲突处理和结果验收。
- 为 Handoff 和循环设置次数上限，防止代理互相转交而没有产出。

深入学习：

- [多智能体系统概念](https://langgraph.com.cn/concepts/multi_agent.1.html)
- [多智能体系统 How-to](https://langgraph.com.cn/how-tos/multi_agent/index.html)
- [子图与多代理记忆边界](https://langgraph.com.cn/concepts/subgraphs.1.html)
- [`Command` 与控制流](https://langgraph.com.cn/concepts/low_level.1.html)

### 2.5 上下文、短期记忆与长期记忆

应区分三种数据：

| 类型 | 典型内容 | 生命周期 |
| --- | --- | --- |
| Runtime Context / Config | 用户 ID、模型配置、权限、依赖句柄 | 单次运行或调用配置 |
| Graph State | 当前消息、任务计划、阶段结果、错误 | 一个线程/工作流运行过程 |
| Store / Long-term Memory | 用户偏好、跨会话事实、长期知识 | 跨线程、跨会话持久化 |

重点知识：

- Checkpointer 如何按 `thread_id` 保存和恢复状态。
- 短期消息过长时的裁剪、摘要和窗口策略。
- 长期记忆的写入触发、命名空间、检索和遗忘策略。
- 不把敏感数据、无关历史或内部推理无差别地共享给所有代理。
- 状态 Schema 版本变化后的兼容和迁移。

学习入口：

- [添加记忆](https://langgraph.com.cn/tutorials/get-started/3-add-memory/index.html)
- [Context](https://langgraph.com.cn/agents/context/index.html)
- [Memory](https://langgraph.com.cn/agents/memory/index.html)
- [持久化与 Checkpoint](https://langgraph.com.cn/concepts/persistence.1.html)
- [时间旅行与状态回放](https://langgraph.com.cn/tutorials/get-started/6-time-travel/index.html)

### 2.6 人工介入与生产化

智能体进入生产环境后，应重点补齐：

- **Human-in-the-loop**：在付款、发布、删除、外发消息等高风险操作前暂停和审批。
- **可恢复执行**：通过 Checkpoint 从中断或故障处继续，而不是整条流程重跑。
- **幂等性**：工具重试不能重复扣款、重复发消息或重复创建资源。
- **错误处理**：区分可重试错误、业务拒绝、模型输出错误和永久失败。
- **流式输出**：区分 Token、节点更新、工具事件和自定义进度事件。
- **可观测性**：记录节点耗时、路由选择、工具参数、费用、失败原因和最终状态。
- **评估**：同时评估最终答案、工具选择、轨迹、路由、延迟和成本。
- **安全性**：最小权限、输入验证、工具白名单、输出审查和敏感信息隔离。

学习入口：

- [添加人工介入](https://langgraph.com.cn/tutorials/get-started/4-human-in-the-loop/index.html)
- [Human-in-the-loop 指南](https://langgraph.com.cn/agents/human-in-the-loop/index.html)
- [流式处理](https://langgraph.com.cn/concepts/streaming.1.html)
- [智能体评估](https://langgraph.com.cn/agents/evals/index.html)
- [部署](https://langgraph.com.cn/agents/deployment/index.html)

---

## 3. 多智能体与任务编排的关系

二者不是同一个概念：

- **任务编排**解决“工作按什么顺序和规则执行”。
- **多智能体协作**解决“不同专业角色如何分工、通信和交接”。

单智能体也需要任务编排；多智能体则必须建立在可靠编排之上。一个推荐的生产结构是：

```text
用户请求
   ↓
Router：识别请求类型和风险等级
   ↓
Planner / Orchestrator：生成结构化任务计划
   ↓
Supervisor：分配任务、跟踪状态、处理冲突
   ├─ Research Worker
   ├─ Domain Worker
   ├─ Tool Worker
   └─ Writing Worker
   ↓
Evaluator：按验收标准检查，不通过则有限次数返工
   ↓
Human Approval：高风险操作人工确认
   ↓
最终结果 / 外部动作
```

其中 Router、审批、权限、次数上限等应尽量确定性；Worker 的内容生成和工具选择可以保留适度自主性。

---

## 4. 什么时候应该使用多智能体

适合使用多智能体：

- 单代理工具过多，选择准确率明显下降。
- 不同领域需要不同提示词、工具、模型或安全权限。
- 上下文过长，需要把信息隔离在不同专业代理中。
- 多项独立任务可以并行执行并统一汇总。
- 组织流程本身就要求明确的责任人、审批和交接。

不应急于使用多智能体：

- 一个代理加少量工具已经可以稳定完成任务。
- 所有代理共享相同上下文、工具和目标，没有实际职责差异。
- 任务很短，多代理通信成本高于业务价值。
- 尚未定义状态、完成标准、错误处理和终止条件。

判断原则：**先证明单代理或确定性工作流不够，再引入多智能体；不要把架构复杂度误当成智能程度。**

---

## 5. 推荐学习顺序（每步含具体网址）

### 第 1 步：完成单智能体与工具闭环

**目标**：理解消息、模型、工具和 ReAct 循环，能够让代理正确选择工具并返回结果。

按顺序阅读：

1. [构建基础聊天机器人](https://langgraph.com.cn/tutorials/get-started/1-build-basic-chatbot/index.html)
2. [向聊天机器人添加工具](https://langgraph.com.cn/tutorials/get-started/2-add-tools/index.html)
3. [工具设计与错误处理](https://langgraph.com.cn/agents/tools.1.html)
4. [智能体架构概念](https://langgraph.com.cn/concepts/agentic_concepts.1.html)

**练习**：实现一个带 2 个无副作用工具的 ReAct 代理。

**验收**：能解释消息序列、工具调用闭环、终止条件和工具失败时的行为。

### 第 2 步：掌握 StateGraph 与持久化

**目标**：能够显式设计状态、节点、边、条件分支和恢复机制。

按顺序阅读：

1. [低层级概念](https://langgraph.com.cn/concepts/low_level.1.html)
2. [添加记忆](https://langgraph.com.cn/tutorials/get-started/3-add-memory/index.html)
3. [自定义状态](https://langgraph.com.cn/tutorials/get-started/5-customize-state/index.html)
4. [持久化与 Checkpoint](https://langgraph.com.cn/concepts/persistence.1.html)
5. [时间旅行](https://langgraph.com.cn/tutorials/get-started/6-time-travel/index.html)

**练习**：实现“分析 → 执行 → 校验”的三节点图，保存 `thread_id` 对应状态并从检查点恢复。

**验收**：能说明 Reducer、条件边、检查点和 Graph State 各自解决什么问题。

### 第 3 步：学习任务编排模式

**目标**：根据任务依赖选择串行、并行、路由、编排器—工作者或评估—优化模式。

按顺序阅读：

1. [工作流与智能体教程](https://langgraph.com.cn/tutorials/workflows/index.html)
2. [低层级概念中的 Send 与 Command](https://langgraph.com.cn/concepts/low_level.1.html)
3. [子图](https://langgraph.com.cn/concepts/subgraphs.1.html)

**练习**：实现“编排器生成子任务 → `Send` 并行执行 → Reducer 聚合 → Evaluator 验收”。

**验收**：能画出任务 DAG，标出并行点、聚合点、重试边界、最大迭代次数和失败出口。

### 第 4 步：进入多智能体协作

**目标**：设计 Supervisor、专业 Worker、Handoff 和代理间上下文隔离。

按顺序阅读：

1. [多智能体系统概念](https://langgraph.com.cn/concepts/multi_agent.1.html)
2. [多智能体系统 How-to](https://langgraph.com.cn/how-tos/multi_agent/index.html)
3. [子图与状态边界](https://langgraph.com.cn/concepts/subgraphs.1.html)
4. [`Command` 与控制流](https://langgraph.com.cn/concepts/low_level.1.html)

**练习**：实现一个 Supervisor，加“研究”和“写作”两个 Worker；Handoff 只传结构化任务单和必要结果。

**验收**：每个代理职责互斥、输入输出明确，循环有上限，Supervisor 能判断完成并汇总结果。

### 第 5 步：补齐上下文、记忆和人工审批

**目标**：控制代理看到的信息，支持跨步骤恢复，并保护高风险动作。

按顺序阅读：

1. [Context](https://langgraph.com.cn/agents/context/index.html)
2. [Memory](https://langgraph.com.cn/agents/memory/index.html)
3. [持久化](https://langgraph.com.cn/concepts/persistence.1.html)
4. [添加人工介入](https://langgraph.com.cn/tutorials/get-started/4-human-in-the-loop/index.html)
5. [Human-in-the-loop 指南](https://langgraph.com.cn/agents/human-in-the-loop/index.html)

**练习**：在具有副作用的工具前 `interrupt`，审批后恢复；让 Worker 只看到完成本任务所需的上下文。

**验收**：拒绝审批时不执行工具，批准后只执行一次；恢复运行不会重复产生副作用。

### 第 6 步：生产化、观测与评估

**目标**：让系统可监控、可回归测试、可部署，并能够衡量质量、成本和稳定性。

按顺序阅读：

1. [流式处理](https://langgraph.com.cn/concepts/streaming.1.html)
2. [智能体评估](https://langgraph.com.cn/agents/evals/index.html)
3. [部署](https://langgraph.com.cn/agents/deployment/index.html)

**练习**：建立固定测试集，记录路由、工具调用、任务轨迹、延迟和 Token 成本，并测试超时、重试和恢复。

**验收**：关键节点有日志与指标；提示词或模型变更后能执行回归评估；失败可以定位到具体节点并安全恢复。

---

## 6. 学完后的能力检查表

完成上述顺序后，应能够回答并实现：

- [ ] 为什么该任务需要智能体，而不是普通函数或固定工作流？
- [ ] State 中有哪些字段，各字段由谁读写，如何合并？
- [ ] 哪些分支使用确定性规则，哪些决策交给模型？
- [ ] 任务是否可并行，结果如何聚合，部分失败怎么办？
- [ ] 多智能体中每个代理的职责、工具权限和上下文范围是什么？
- [ ] Handoff 传递什么数据，由谁收回控制权？
- [ ] 每个循环的停止条件和最大次数是什么？
- [ ] 高风险工具在哪里暂停，如何批准、拒绝和恢复？
- [ ] 重试是否会产生重复副作用，如何保证幂等？
- [ ] 如何评估最终答案、路由、工具选择、轨迹、成本和延迟？

如果这些问题尚无法明确回答，通常说明系统还停留在“能演示”，没有达到“可控、可测试、可运行”的阶段。

---

## 7. 最终建议

1. 从**单智能体 + 少量工具**开始，先把状态、错误和终止条件做正确。
2. 用 LangGraph 表达明确的任务编排，不要让模型接管本可确定的控制逻辑。
3. 当工具数量、领域差异、上下文隔离或组织职责确有需要时，再引入多智能体。
4. 多智能体优先从 Supervisor 模式起步，并采用结构化 Handoff。
5. 生产环境必须同时建设 Checkpoint、HITL、幂等、观测、评估和安全边界。
6. 把“最终答案正确”与“执行轨迹正确”分开测试；智能体可能偶然得到正确答案，但走了错误或危险的路径。

> 注：本文链接已于 2026-09-17 按 HTTP 状态核验。中文镜像的内容和路径可能晚于上游 LangGraph 官方文档更新，长期使用时应定期复查。
