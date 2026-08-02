# Graph Engineering 设计文档

> 状态：Draft，等待 Review
>
> 文档版本：0.1
>
> 目标：定义一个平台无关的自治软件开发控制层。用户在任务开始阶段通过自然语言完成需求澄清和执行授权，系统随后自动完成实现、验证、修复和审查，最后交付证据充分的成果供用户验收。

## 1. Review 时需要优先确认的决策

以下决策会显著影响实现，请在开始编码前确认：

1. Graph Engineering 是独立控制层，而不是 Codex 专属插件。
2. Codex 是第一个 Coding Executor；Claude Code 在核心协议稳定后接入。
3. 初始交互使用 `ge start` 提供自然语言会话；Codex Plugin 后续作为等价入口。
4. Discovery Graph 和 Execution Graph 严格分离；用户确认后冻结 Contract 与 Verifier。
5. 自治执行期间不询问用户，不降低验收标准；无法完成时停止并生成失败报告。
6. Runtime 外部持久化所有关键状态，不依赖 Codex Session 的上下文或 compact。
7. Verifier 优先使用声明式配置，无法表达时才允许 Codex 生成代码。
8. 已冻结的 Contract、Verifier 和验收证据对实现 Agent 只读。
9. MVP 建议使用 Python 3.12 实现，采用 SQLite、Pydantic、Typer、asyncio 和 pytest；该技术栈仍可在 Review 中调整。
10. MVP 先实现单机、单任务、串行图；并行节点、远程 Worker 和可视化界面后置。

## 2. 背景与问题定义

传统 Coding Agent 通常围绕一次长会话工作。复杂任务容易遇到：

- 需求、约束和验收条件只存在于聊天记录中。
- 上下文不断膨胀，触发 compact 后丢失关键细节。
- Agent 同时承担实现、测试和自我审查，缺少职责隔离。
- 不同项目使用不同的单测、集成测试、压测和 CI。
- 外部流水线是异步过程，单次 Agent 会话难以可靠等待和恢复。
- Agent 可能通过修改测试或验收脚本使错误实现通过。
- 失败后难以判断应该重试、修复代码、重跑基础设施，还是终止。
- 更换 Codex、Claude Code 等工具时，任务状态和工作流无法迁移。

本项目将自治开发过程建模为持久化执行图，由确定性的 Graph Runtime 管理状态、边界和证据，由 Coding Executor 完成需要模型推理的节点。

## 3. 项目定位

GitHub Description 建议：

> 面向自治软件开发的图工程工具：人在起点定义需求与边界，由 Coding Agent 自动规划、实现、测试和审查，最终交付可验证成果供人验收。

核心关系：

```text
Harness Engineering
  保证单个 Coding Agent 节点拥有正确的工具、权限和上下文
          ↓
Loop Engineering
  利用测试、审查和失败反馈使一个任务局部收敛
          ↓
Graph Engineering
  将多个 Agent、确定性工具、反馈循环、外部系统和人工边界
  组织为可组合、可恢复、可审计的执行图
```

## 4. 目标与非目标

### 4.1 目标

- 提供类似 Coding CLI 的自然语言需求澄清体验。
- 将讨论结果编译为结构化、可冻结的 Task Contract。
- 根据 Contract 和项目策略生成可执行 Graph。
- 支持多个 Coding Executor，MVP 首先支持 Codex CLI。
- 支持项目自定义测试、CI、压测和其他 Verifier。
- 支持 Codex 在 Discovery 阶段生成新的 Verifier。
- 支持 checkpoint、恢复、重试、预算和失败分类。
- 将长任务拆成多个上下文受限的 Agent Session。
- 提供从需求到代码、测试、审查和交付物的证据链。
- 最终结果由人验收，MVP 不默认自动合并代码。

### 4.2 非目标

- 不实现新的基础模型或通用聊天机器人。
- 不在 MVP 中实现可视化拖拽编辑器。
- 不在 MVP 中实现分布式调度系统。
- 不要求所有任务使用多 Agent 或并行执行。
- 不以替代 GitHub Actions、Temporal、Dagster 等通用工作流系统为目标。
- 不保证任意自然语言需求都能在无人干预下成功完成。
- 不允许 Agent 在执行阶段自行改变需求或验收标准。

## 5. 用户体验

### 5.1 完整流程

```text
ge init
  ↓
ge start
  ↓
自然语言需求讨论与代码库探索
  ↓
生成 Contract、Verifier、Graph 草案和风险报告
  ↓
用户确认执行
  ↓
冻结 Contract 和 Verifier
  ↓
自治实现、测试、修复、审查和交付
  ↓
ge report
  ↓
ge accept / ge reject
```

### 5.2 交互示例

```text
用户：
为订单服务增加批量取消接口。

系统：
我已检查项目结构。开始前需要确认：
1. 单次最多取消多少个订单？
2. 部分订单失败时整体回滚还是逐项返回？
3. 需要运行哪些测试？
4. 是否必须等待远程 CI？

用户：
最多100个，部分成功。运行单测、集成测试和压测，最后等待公司CI。

系统：
请提供公司CI的触发、状态查询、鉴权、成功状态和超时规则。
```

讨论完成后，系统展示结构化摘要、待执行命令、网络访问、secret 名称、预算和禁止修改路径。只有用户明确确认后才进入自治执行。

### 5.3 自治阶段行为

- 不再发起普通需求问题。
- 不请求扩大权限。
- 不修改冻结的验收标准。
- 遇到实现失败时在预算内自动修复。
- 遇到 Verifier 基础设施错误时按策略重试，不能误判为代码失败。
- 预算耗尽、权限不足或契约矛盾时停止并生成报告。
- 默认创建分支或 Pull Request，不自动合并。

## 6. 总体架构

```text
┌────────────────────────────────────────────┐
│ Frontends                                  │
│ ge CLI | Codex Plugin | future UI          │
└─────────────────────┬──────────────────────┘
                      ↓
┌────────────────────────────────────────────┐
│ Discovery                                  │
│ Conversation | Repo Inspect | Contract     │
│ Verifier Generator | Risk Review           │
└─────────────────────┬──────────────────────┘
                      ↓ freeze
┌────────────────────────────────────────────┐
│ Graph Engineering Core                     │
│ Compiler | Scheduler | State | Policy       │
│ Context Builder | Artifact | Report         │
└───────────────┬─────────────────┬──────────┘
                ↓                 ↓
┌────────────────────────┐  ┌──────────────────────┐
│ Coding Executors       │  │ Verifiers            │
│ Codex | Claude Code    │  │ Command | HTTP | CI  │
└───────────────┬────────┘  └───────────┬──────────┘
                ↓                       ↓
┌────────────────────────────────────────────┐
│ Git Worktree | Shell | Network | GitHub    │
└────────────────────────────────────────────┘
```

### 6.1 核心模块

| 模块 | 职责 |
|---|---|
| CLI | 用户命令、自然语言交互、状态和报告展示 |
| Discovery Engine | 需求澄清、代码库探索、缺失信息识别 |
| Contract Compiler | 将对话编译为 Task Contract |
| Graph Compiler | 根据 Contract、模板和策略生成 Execution Graph |
| Scheduler | 节点调度、路由、重试、超时和终止 |
| State Store | 事务化保存 run、node、attempt、external handle |
| Event Store | 追加式记录所有运行事件 |
| Artifact Store | 保存日志、报告、handoff 和测试证据 |
| Context Builder | 为每个 Agent 节点构建有限、相关、可追溯的上下文 |
| Policy Engine | 权限、路径、命令、网络、secret 和预算控制 |
| Executor Registry | Codex、Claude Code 等适配器注册表 |
| Verifier Registry | 内置、声明式和自定义 Verifier 注册表 |
| Delivery | 分支、commit、patch、Pull Request 和最终报告 |

### 6.2 插件集成与部署形态

Graph Engineering 接入 Codex 或 Claude Code 时采用“薄插件 + 独立 Runtime”，而不是把 Graph Runtime 的全部逻辑运行在插件会话中：

```text
Codex / Claude Code
  ↓ Plugin、Skill 或 MCP tools
ge client
  ↓ local IPC
ge runtime daemon
  ↓
State Store / Executor / Verifier / Git worktree
```

插件负责：

- 暴露自然语言入口和项目命令。
- 提供 Graph Engineering Skill 和使用说明。
- 注册 `ge` MCP tools 或调用 `ge` CLI。
- 展示 Contract 摘要、运行状态和验收报告。

插件不负责：

- 依赖当前聊天上下文保存运行状态。
- 在插件进程内长期等待 CI 或压测。
- 直接管理 checkpoint、worktree 和外部副作用。
- 将 Codex 或 Claude Code 专属数据格式写入核心状态模型。

建议的接入层级：

1. MVP 先提供独立 `ge` CLI。
2. 提供 `ge mcp-server`，向支持 MCP 的 Coding CLI 暴露 `start`、`answer`、`confirm`、`status`、`report` 等工具。
3. Codex Plugin 打包 Skill、命令和 MCP 配置，并检查本机 `ge` Runtime。
4. Claude Code 使用相同 MCP 协议和 Runtime，只替换薄入口与 Executor Adapter。

长任务必须由独立 Runtime 或 daemon 持有。退出 Codex、关闭 Claude Code 或发生 Session compact 后，run 仍能继续或从 checkpoint 恢复。

### 6.3 环境依赖

依赖分为四层，不能全部硬编码为插件安装依赖。

#### 基础必需依赖

- `ge` Runtime。
- Git，用于分支、diff、commit 和 worktree 隔离。
- 至少一个已安装并完成鉴权的 Coding Executor，例如 Codex CLI；使用 Claude Code 时则需要其 CLI 和鉴权。
- 目标操作系统提供的进程、文件权限和本地持久化能力。

开发阶段如果采用本文建议技术栈，需要 Python 3.12。正式发布应优先提供 Windows、Linux 和 macOS 自包含可执行文件，使插件用户不必单独安装 Python、uv 或项目源码依赖。`uvx` 或 `pipx` 可作为开发版和备用安装方式。

#### 项目工具链依赖

目标项目自身可能需要：

- Node.js、Python、Go、Java、Rust 等语言环境。
- npm、pnpm、uv、Maven、Gradle 等包管理器。
- 数据库、Redis、浏览器或本地服务。
- pytest、Playwright、k6 等测试工具。

这些依赖由 Discovery 阶段探测并与用户确认，不能作为 Graph Engineering 的全局固定依赖。Graph Runtime 只负责记录、检查、启动和收集结果。

#### Verifier 依赖

每个 Verifier 必须声明自己的运行环境：

```yaml
requirements:
  commands:
    - k6
  runtimes:
    - name: node
      version: ">=20"
  services:
    - docker
  network:
    - ci.example.com
  secrets:
    - CI_TOKEN
```

声明式 HTTP Verifier 通常不需要额外语言运行时。项目级 subprocess Verifier 需要声明入口程序及其 Runtime。容器化 Verifier 则需要 Docker 或兼容的容器运行时。

#### 可选集成依赖

- Docker，用于更强隔离和复杂测试环境。
- GitHub、GitLab 或企业 CI 的 API 网络访问和凭据。
- 浏览器运行环境，用于端到端测试。
- 远程 Worker，用于压测、GPU 或内网流水线。

### 6.4 Preflight 与兼容性检查

安装插件或启动任务时必须运行环境检查：

```text
ge doctor
ge doctor --project
ge doctor --verifier <name>
```

检查内容：

- `ge`、Git 和 Coding Executor 是否存在及版本是否兼容。
- Coding Executor 是否已鉴权。
- 项目需要的命令、服务和测试工具是否存在。
- Verifier 的网络、secret 和 Runtime 是否可用。
- 工作目录是否为有效 Git 仓库，能否创建 worktree。
- 当前平台是否支持所需 sandbox 和文件权限。

检查结果进入 Contract 附件。自治执行前仍缺失的必需依赖必须标记为阻断项；系统不能等运行到中间才静默安装工具或请求扩大权限。

插件与 Runtime 使用独立版本号，并维护兼容范围：

```yaml
plugin:
  version: 0.1.0
  requires_ge: ">=0.1,<0.2"
  requires_host:
    codex: ">=validated-minimum-version"
```

核心协议、MCP tools 和 Executor Adapter 都需要版本字段。宿主 CLI 变化只应影响薄插件或 Adapter，不应使已有 run 的持久化状态失效。

## 7. 两类 Graph

### 7.1 Discovery Graph

Discovery Graph 是交互式的，允许用户参与：

```text
repository_inspect
        ↓
requirement_analyze
        ↓
identify_unknowns ←──────────┐
        ↓                    │
ask_user                     │
        ↓                    │
update_draft ────────────────┘
        ↓
prepare_verifiers
        ↓
validate_contract
        ↓
user_confirm
        ↓
freeze
```

Discovery 输出：

- `contract.yaml`
- `repository-map.yaml`
- `graph.yaml`
- `risk-report.md`
- Verifier 配置或源码
- `acceptance.lock`

### 7.2 Execution Graph

Execution Graph 是自治的，禁止普通人工交互：

```text
inspect → design → implement → verify → review → deliver
                      ↑           │         │
                      └── repair ─┘         │
                      └── review_fix ───────┘
```

Graph 可以按项目拆分为更细的节点，例如数据库、后端、前端、单测、集成测试、压测和远程 CI。

## 8. Task Contract

Contract 是需求事实来源，确认后不可变。建议结构：

```yaml
version: 1

task:
  id: batch-cancel-orders
  title: 增加批量取消订单接口
  description: "..."

behavior:
  max_batch_size: 100
  failure_strategy: partial_success

interfaces:
  upstream: []
  downstream: []

conventions:
  follow_existing_architecture: true
  formatter: gofmt
  lint: golangci-lint

verification:
  required:
    - verifier: builtin/command
      config:
        command: go test ./...
    - verifier: project/company-ci

delivery:
  type: pull_request
  auto_merge: false

policy:
  protected_paths: []
  allowed_network_hosts: []
  allowed_secrets: []

budget:
  max_duration: 120m
  max_agent_calls: 30
  max_repair_iterations: 5
```

Contract 编译时必须检查：

- 是否有明确成功条件。
- 每个外部依赖是否有参数来源。
- 每个 Verifier 是否有超时和失败语义。
- 是否区分业务失败和基础设施错误。
- 是否定义代码交付方式。
- 是否存在相互矛盾的要求。
- 是否明确敏感权限和 secret 引用。

## 9. Graph 模型

### 9.1 节点类型

MVP 节点类型：

| 类型 | 描述 |
|---|---|
| `agent` | 调用 Coding Executor 完成结构化任务 |
| `command` | 执行确定性本地命令 |
| `verifier` | 执行统一 Verifier 协议 |
| `router` | 根据结构化结果选择下一条边 |
| `delivery` | 生成 commit、patch、PR 或报告 |

后续节点类型：`parallel`、`join`、`subgraph`、`human_gate`、`remote_job`。

### 9.2 节点状态

```text
pending
ready
running
succeeded
failed
error
cancelled
skipped
```

`failed` 表示任务或验收未通过，通常可以进入修复循环；`error` 表示执行器、Verifier 或基础设施异常，不能默认触发业务代码修改。

### 9.3 边与路由

```yaml
edges:
  - from: implement
    to: test

  - from: test
    to: review
    when: result.status == "passed"

  - from: test
    to: repair
    when: result.status == "failed"
    max_iterations: 5

  - from: test
    to: stop
    when: result.status == "error"
```

条件表达式 MVP 应采用受限表达式语言，禁止直接执行任意 Python 或 Shell。

### 9.4 副作用和幂等性

- 所有节点拥有稳定的 `node_id` 和 `attempt_id`。
- 外部触发使用 `run_id + node_id` 作为幂等键。
- 远程任务返回的 run ID 必须先 checkpoint，再开始轮询。
- Runtime 重启后不得无条件重复创建 PR、重复触发 CI 或重复发布。
- 无法保证 exactly-once 的外部系统必须使用查询或补偿逻辑。

## 10. Executor 协议

核心不依赖具体 Coding CLI。建议抽象：

```text
start(request) -> session, event stream, result
resume(session, request) -> event stream, result
review(request) -> event stream, review result
cancel(session) -> result
capabilities() -> capability descriptor
```

统一请求至少包含：

- 当前节点角色和目标
- Context Package
- 工作目录
- sandbox 和权限策略
- 输出 JSON Schema
- 时间、token 和工具预算

统一结果至少包含：

- `status`
- `summary`
- `changed_files`
- `decisions`
- `remaining_risks`
- `next_actions`
- `evidence_refs`
- provider session ID

### 10.1 Codex Adapter

MVP 使用 Codex CLI 的非交互能力：

- `codex exec`
- `--json`
- `--output-schema`
- `--output-last-message`
- `codex exec resume`
- `codex exec review`
- workspace-write sandbox
- approval policy `never`

Runtime 解析 JSONL 事件并保存原始输出。禁止默认使用 `--dangerously-bypass-approvals-and-sandbox`。如果未来支持该模式，必须要求 Graph Engineering 自身运行在外部强隔离容器中。

### 10.2 Session 策略

```yaml
sessions:
  default: fresh_per_node
  resume_same_node: true
  max_continuations: 2
  rotate_after_failed_attempts: 2
  fresh_before_review: true
```

角色变化、独立审查或多次失败后创建新 Session，并通过 Handoff 传递状态。

### 10.3 独立 Reviewer Agent

Reviewer 是与 Implementer 对等的独立 Agent 角色，不是 Implementer 在同一 Session 中执行的一段自检提示词。MVP 可以继续使用同一个 Codex CLI 和模型，但必须使用全新的 Session、独立的 Context Package 和只读权限。

建议配置：

```yaml
executors:
  implementer:
    provider: codex
    sandbox: workspace-write

  reviewer:
    provider: codex
    mode: review
    sandbox: read-only
    fresh_session: always
```

Reviewer 输入：

- 冻结的 Contract 和相关验收条目。
- 基准 commit、待审 commit 和完整 diff。
- Repository Map 与项目代码规范。
- Verifier 原始结果和 evidence 引用。
- Implementer 的结构化 decisions 与 remaining risks。
- 受保护路径、权限和安全策略。

Reviewer 默认不接收 Implementer 的完整对话、自由形式推理或“实现已经正确”的说服性总结。Reviewer 必须从代码、Contract 和客观证据独立得出结论。

Reviewer 职责：

- 检查实现是否满足 Contract，而不只是测试是否通过。
- 检查正确性、边界条件、错误处理和兼容性。
- 检查是否遵循项目架构与代码风格。
- 检查测试是否覆盖关键行为，是否存在为通过测试而弱化断言的情况。
- 检查安全、权限、secret、数据迁移和外部副作用风险。
- 将每个 finding 定位到具体文件和行，并说明影响和修复要求。
- 对未能验证的内容明确标记，不能用推测给出批准。

Reviewer 统一输出：

```json
{
  "verdict": "changes_requested",
  "summary": "批量取消接口缺少重复订单ID处理",
  "findings": [
    {
      "severity": "high",
      "category": "correctness",
      "file": "internal/service/order.go",
      "line": 142,
      "description": "重复ID会导致同一订单被执行两次取消",
      "requiredChange": "在进入业务循环前去重，并补充边界测试",
      "contractRefs": ["behavior.max_batch_size"]
    }
  ],
  "unverified": [],
  "evidenceRefs": []
}
```

`verdict` 仅允许：

- `approved`：没有阻断交付的问题。
- `changes_requested`：发现可以由 Implementer 修复的问题。
- `blocked`：缺少必要证据、环境或 Contract 存在矛盾，不能可靠审查。

Reviewer 不能直接修改代码。审查路由必须是：

```text
verify passed
  ↓
reviewer
  ├─ approved → deliver
  ├─ changes_requested → implementer_fix → relevant_verifiers → fresh reviewer
  └─ blocked → stop and report
```

每次修复后必须重新运行受影响的 Verifier；不能直接复用修复前的通过结果。新的审查 attempt 默认使用新的 Reviewer Session，并设置最大 review-fix 次数。

MVP 实现一个综合 Reviewer。后续可以拆成 Contract Review、Code Review、Security Review 和 Test Adequacy Review，并通过 join 汇总结论。

### 10.4 Claude Code Adapter

Claude Code 支持放在协议稳定之后。其适配器必须复用同一个 Executor 请求和结果模型，不允许核心层出现大量 provider 分支判断。

## 11. Memory 与 Context 管理

### 11.1 原则

```text
模型上下文是临时缓存，不是数据库。
Git 是代码事实。
Contract 是需求事实。
Verifier 是验收事实。
Artifact 是执行证据。
Graph Runtime 是状态事实。
```

### 11.2 Memory 分层

| 类型 | 内容 | 是否可摘要 |
|---|---|---|
| Contract Memory | 需求、约束、验收和权限 | 否 |
| Repository Memory | 模块、入口、约定和相关文件 | 可重建 |
| Execution State | 节点、attempt、预算和外部 handle | 否 |
| Handoff Memory | 节点结构化交接 | 可分层摘要 |
| Evidence Memory | Git、测试、CI 和报告 | 原始证据不可改 |
| Event Memory | 完整事件流 | 可按需查询 |

### 11.3 Context Builder

每次调用 Agent 只注入：

1. 当前节点职责。
2. 与节点相关的 Contract 子集。
3. 不可违反的全局策略。
4. 当前 Git 状态。
5. 直接上游 Handoff。
6. 当前失败的原始证据。
7. 相关文件和 artifact 引用。
8. 输出 Schema。

优先通过文件路径和 artifact 引用提供大内容，由 Agent 按需读取，不把完整日志塞入 prompt。

### 11.4 Handoff Schema

```json
{
  "status": "completed",
  "summary": "已实现批量取消服务",
  "changedFiles": [],
  "decisions": [],
  "remainingRisks": [],
  "nextActions": [],
  "evidenceRefs": []
}
```

### 11.5 长期项目知识

Run Memory 不自动升级为 Project Memory。只有任务最终验收通过后，稳定的测试命令、架构约定和目录职责才能成为候选项目知识。MVP 可先生成候选文件，由人 Review 后更新 `AGENTS.md` 或 `.graph-engineering/project.yaml`。

MVP 不引入向量数据库。代码搜索、Repository Map、结构化 Handoff 和 artifact 引用足以支持第一阶段；后续由真实评测决定是否需要语义检索。

## 12. Verifier 系统

### 12.1 设计原则

Verifier 是验收插件，不只是测试命令。优先级：

1. 内置 Verifier。
2. 声明式 Verifier。
3. Codex 生成的项目级 Verifier。
4. 容器化 Verifier。

能配置就不生成代码。生成代码时必须测试、审计和冻结。

### 12.2 Verifier 类型

MVP：

- `builtin/command`
- `builtin/http-pipeline`
- `project/subprocess`

后续：

- GitHub Actions
- GitLab CI
- Playwright
- k6、JMeter、Locust
- 安全扫描
- 容器化自定义 Verifier

### 12.3 统一结果

```json
{
  "status": "passed",
  "summary": "流水线全部通过",
  "metrics": {},
  "evidence": [],
  "externalHandle": null,
  "retryable": false
}
```

状态：`pending`、`passed`、`failed`、`error`、`cancelled`。

### 12.4 HTTP Pipeline Verifier

应支持：

- 请求方法、URL、headers 和 body 模板。
- 从 JSON 响应提取 external run ID。
- 定时轮询。
- pending、passed、failed 状态映射。
- timeout、重试和退避。
- 下载报告和保存 URL 证据。
- secret 引用但不暴露其实际值。
- 网络 host allowlist。

### 12.5 动态生成 Verifier

Discovery 阶段流程：

```text
用户描述外部验收方式
  ↓
Codex 判断内置或声明式能力是否足够
  ↓ 不足
生成 project verifier + manifest + tests + fixtures
  ↓
schema validate + contract tests + dry run + policy scan
  ↓
展示权限和行为摘要给用户
  ↓
随 Contract 一起确认并冻结
```

实现阶段 Agent 不能修改已冻结 Verifier。

### 12.6 Verifier 权限 Manifest

```yaml
name: company-ci
version: 1
runtime: subprocess
entrypoint: dist/verifier

capabilities:
  network:
    allow:
      - ci.example.com
  secrets:
    - CI_TOKEN
  filesystem:
    write:
      - ${artifact_dir}
```

Runtime 只提供声明过的能力。Secret 由 Runtime 在 Verifier 执行时注入，不进入 Agent prompt、事件日志和最终报告。

### 12.7 冻结机制

```yaml
acceptance_lock:
  contract_sha256: "..."
  verifiers:
    company-ci:
      manifest_sha256: "..."
      source_sha256: "..."
      tests_sha256: "..."
```

每次执行前检查 hash。任何变更都必须生成新的 Contract 版本，不能在原 run 中静默替换。

## 13. Policy 与安全边界

### 13.1 工作区隔离

- 每个 run 使用独立 Git branch 和 worktree。
- `.ge/control` 与实现 worktree 分离。
- Contract、Graph、Verifier 和 acceptance lock 对 Agent 只读。
- Artifact Store 不允许实现 Agent 直接覆盖历史证据。

### 13.2 命令执行

- Discovery 阶段展示将要执行的命令和权限类别。
- Contract 确认后，仅执行已允许的命令类别和项目脚本。
- 禁止字符串拼接绕过策略。
- 超时、输出大小和并发数必须有限制。
- 高风险命令默认拒绝并终止 run。

### 13.3 网络与 Secret

- 网络默认拒绝，按 host allowlist 开放。
- Secret 只通过引用出现在 Contract 中。
- Secret 仅注入明确声明的 Verifier 或节点。
- 日志输出经过脱敏。
- Agent 默认不知道 secret 实际值。

### 13.4 信任边界

动态生成的 Verifier 本质上是待执行代码。MVP 即使完成静态扫描和合约测试，也不能宣称完全安全。首版必须在确认页面清晰展示：

- 将执行的入口程序。
- 网络访问范围。
- 文件读写范围。
- secret 名称。
- 外部副作用。

## 14. 持久化、恢复与事件

### 14.1 建议目录

```text
.ge/
├── control/
│   ├── contract.yaml
│   ├── graph.yaml
│   ├── acceptance.lock
│   └── repository-map.yaml
├── runs/
│   └── <run-id>/
│       ├── state.db
│       ├── events.jsonl
│       ├── handoffs/
│       ├── artifacts/
│       ├── prompts/
│       └── responses/
└── worktrees/
    └── <run-id>/
```

### 14.2 SQLite 数据

建议表：

- `runs`
- `nodes`
- `attempts`
- `edges`
- `sessions`
- `external_handles`
- `artifacts`
- `budgets`

原始大日志保存在 Artifact Store，SQLite 只保存元数据和引用。

### 14.3 Checkpoint

至少在以下时机事务化 checkpoint：

- 节点开始前。
- Agent Session ID 获得后。
- Git commit 创建后。
- 外部任务触发并获得 run ID 后。
- 节点结果写入后、路由执行前。
- 预算变化后。

### 14.4 恢复

```powershell
ge resume <run-id>
```

恢复时：

1. 验证 Contract 和 Verifier hash。
2. 验证 worktree 和 Git 状态。
3. 检查 running 节点是否有外部 handle。
4. 能查询则查询，不能确认副作用时停止并报告。
5. 从最后一个已提交状态继续。

## 15. 交付与最终验收

运行结束生成：

```text
summary.md
requirement-matrix.md
changes.diff
test-results.json
review-report.md
execution-trace.json
cost-report.json
pull-request.json
```

`requirement-matrix.md` 将每个验收条件映射到测试、CI、代码或人工检查证据。

命令：

```powershell
ge report <run-id>
ge accept <run-id>
ge reject <run-id> --reason "..."
```

`reject` 创建新的需求修订版，不修改旧 Contract 和历史证据。

## 16. CLI 草案

```text
ge init
ge start
ge plan <request-or-run>
ge confirm <run-id>
ge run <run-id>
ge status <run-id>
ge resume <run-id>
ge cancel <run-id>
ge report <run-id>
ge accept <run-id>
ge reject <run-id>

ge graph validate <file>
ge graph inspect <file>

ge verifier list
ge verifier validate <name>
ge verifier test <name>
ge verifier dry-run <name>
```

MVP 可将 `ge confirm` 和 `ge run` 分开，防止用户在查看摘要时误启动自治执行。

## 17. 建议技术栈

当前建议使用 Python 3.12：

| 能力 | 建议 |
|---|---|
| CLI | Typer |
| 数据模型 | Pydantic v2 |
| YAML | ruamel.yaml 或 PyYAML |
| 状态存储 | SQLite，标准库 `sqlite3` |
| 异步调度 | asyncio |
| HTTP | httpx |
| 测试 | pytest |
| JSON Schema | jsonschema |
| 打包 | uv + pyproject.toml，后续提供独立二进制 |

选择理由：

- 适合快速实现 CLI、子进程、HTTP 和动态插件协议。
- SQLite、JSONL 和 asyncio 足以支持单机 MVP。
- 用户可以通过 `uvx` 或 `pipx` 使用。
- Verifier 协议仍然是语言无关的，不限制项目使用其他语言。

主要代价：需要 Python Runtime，单文件跨平台分发不如 Go/Rust 自然。如果项目从一开始就要求无运行时单二进制，可以在 Review 中改为 Go；核心协议和阶段划分不受影响。

## 18. 测试策略

### 18.1 单元测试

- Contract 和 Graph schema。
- 条件路由。
- 状态转换。
- 重试和预算。
- hash 冻结。
- Context Builder 优先级和大小限制。
- secret 脱敏。
- Codex JSONL 事件解析。
- Verifier 状态映射。

### 18.2 集成测试

- Fake Executor 完成完整图。
- Agent 失败后修复循环。
- Runtime 中断后恢复。
- HTTP Pipeline trigger、poll 和 report。
- 外部任务重复恢复不重复触发。
- Contract 或 Verifier 被修改时拒绝运行。

### 18.3 端到端测试

- 在 fixture Git repo 中调用真实 Codex 完成一个受限小任务。
- 运行单测、生成 commit 和最终报告。
- 真实 Codex 测试默认不进入普通快速测试，使用显式环境开关执行。

## 19. 可观测性

MVP 使用结构化 JSONL 事件，至少包含：

- `run.created`
- `contract.frozen`
- `node.started`
- `executor.session.started`
- `command.finished`
- `verifier.pending`
- `verifier.finished`
- `artifact.created`
- `node.finished`
- `route.selected`
- `budget.updated`
- `run.finished`

所有事件拥有 `run_id`、`node_id`、`attempt_id`、时间戳和相关 artifact 引用。后续可增加 OpenTelemetry adapter，但不作为 MVP 前置条件。

## 20. 分阶段实施计划

每个阶段建议使用一个独立对话完成。任何阶段未通过验收时，不进入下一阶段。

### Phase 0：仓库与协议基础

范围：

- 初始化 Python 项目结构和开发工具。
- 建立 Contract、Graph、Executor Result、Verifier Result 的 Pydantic 模型。
- 建立 JSON Schema 导出。
- 编写 ADR、贡献指南和基础测试。

不包含：真实 Codex、自然语言交互、图执行。

验收：

- 所有 schema 有合法和非法 fixture。
- `ge graph validate` 可以验证静态 Graph。
- 单元测试通过。
- 生成 Phase 0 交接包。

### Phase 1：持久化 Graph Runtime

范围：

- SQLite State Store。
- JSONL Event Store 和 Artifact Store。
- 串行调度、条件边、重试、预算、终止。
- Fake Executor、Fake Verifier。
- checkpoint 和进程中断恢复。

不包含：真实 Coding CLI。

验收：

- Fake Executor 可以跑完实现、失败、修复、审查图。
- 中断后恢复不会重复已完成节点。
- 外部 handle 测试证明不会重复触发。
- 状态机和事件测试通过。

### Phase 2：Codex Executor 与 Memory

范围：

- Codex CLI preflight 和 capability 检测。
- `codex exec --json --output-schema` Adapter。
- Session start、resume、rotate 和 review。
- 独立只读 Reviewer Agent、结构化 findings 和 review-fix 路由。
- Context Builder、Repository Map 和 Handoff。
- Git branch/worktree 隔离。
- 内置 Command Verifier。

不包含：动态 Verifier、GitHub PR。

验收：

- fixture repo 中可由 Codex 完成一个小型修改。
- Agent 节点使用结构化输出。
- 新 Session 可以仅依赖 Handoff 继续任务。
- Reviewer 使用不同于 Implementer 的全新 Session，且不能修改工作区。
- Reviewer 请求修改后由 Implementer 修复，相关 Verifier 重跑，再进入新的审查 attempt。
- Runtime 重启后可从 checkpoint 恢复。
- Contract 控制文件不能被实现 Agent 修改。

### Phase 3：自然语言 Discovery 与 Contract 冻结

范围：

- `ge start` 交互式会话。
- 项目预扫描和未知项识别。
- 多轮问答和 Contract 草案。
- 测试、上下游、代码风格、权限和交付方式确认。
- 风险摘要、确认界面和 acceptance lock。
- 从 Contract 编译标准 Execution Graph。

验收：

- 用户可以仅通过自然语言完成一个任务 Contract。
- 缺失测试方式时系统必须询问或明确建议。
- 确认前不进入自治写代码阶段。
- 确认后 Contract 修改会导致运行拒绝。

### Phase 4：动态 Verifier

范围：

- Verifier Registry 和 SDK。
- HTTP Pipeline Verifier。
- subprocess Verifier 协议。
- Codex 生成 Manifest、实现、fixtures 和 tests。
- capability 校验、secret 脱敏、网络 allowlist。
- verifier validate、test、dry-run 和 freeze。

验收：

- 从自然语言生成一个异步 CI Verifier。
- Runtime 能触发、checkpoint、轮询和收集报告。
- Verifier 基础设施错误不进入业务代码修复。
- 修改冻结 Verifier 后运行被拒绝。
- 日志和 Agent prompt 不泄露 secret。

### Phase 5：Review、GitHub 与交付

范围：

- 多维度 Review 增强，包括 Contract、Security 和 Test Adequacy Review。
- requirement matrix。
- GitHub Actions 状态获取。
- Pull Request 创建和更新。
- 最终报告、accept 和 reject。

验收：

- 完整任务能够自动产生待验收 PR。
- 每个验收条件都有证据或明确标记未验证。
- 默认不自动合并。
- reject 会创建新 Contract 版本。

### Phase 6：插件、Claude Code 与增强能力

范围：

- Codex Plugin 作为 `ge` 的薄入口。
- Claude Code Adapter。
- 并行节点、子图和 join。
- 容器化 Verifier。
- OpenTelemetry 和可选 UI。

这些能力逐项实现，不要求在同一对话完成。

## 21. 跨对话交接规范

### 21.1 每个阶段必须更新的文件

实现开始后建立：

```text
docs/
├── adr/
├── phases/
│   ├── phase-0.md
│   ├── phase-1.md
│   └── ...
└── status/
    └── CURRENT.md
```

每个阶段结束必须更新 `docs/status/CURRENT.md`：

```markdown
# Current Status

## 当前阶段
Phase 2：Codex Executor 与 Memory

## 已完成
- ...

## 未完成
- ...

## 关键决策
- 决策及对应 ADR 路径

## 代码入口
- 重要模块和职责

## 数据与协议
- schema 路径和版本

## 验证结果
- 执行过的命令和结果

## 已知问题
- ...

## 工作区状态
- 分支、最近 commit、未提交文件说明

## 下一阶段第一步
- ...
```

### 21.2 阶段交接包

每个阶段的交付必须包含：

- 当前设计文档版本。
- 阶段目标和验收结果。
- ADR 列表。
- 变更文件列表。
- schema 或协议变化。
- 测试命令及结果。
- 未解决问题和风险。
- Git 状态和未提交变更说明。
- 下一阶段禁止破坏的行为。
- 下一对话的启动提示词。

### 21.3 新对话启动模板

```text
请继续实现 graph_engineering 的 Phase <N>。

开始前必须阅读：
1. DESIGN.md
2. docs/status/CURRENT.md
3. docs/phases/phase-<N>.md
4. docs/adr/ 中被 CURRENT.md 引用的 ADR

先检查 git status 和现有测试，不要重做已完成阶段，也不要回退用户已有修改。
本次只完成 Phase <N> 的范围和验收条件；不要提前实现后续阶段。
完成后运行该阶段测试，并更新 docs/status/CURRENT.md 和阶段交接记录。
```

### 21.4 上下文不足时的提前交接

如果一个阶段在单次对话内仍然过大，应在继续写代码前：

1. 停止扩大实现范围。
2. 将阶段拆为 `Phase N.A`、`Phase N.B`。
3. 保证当前代码处于可测试状态。
4. 更新 `CURRENT.md`，精确记录下一步。
5. 记录未提交修改的来源和意图。
6. 提供新的启动提示词。

不能只依赖聊天摘要完成交接。

## 22. ADR 初始列表

实现 Phase 0 时建议建立：

- ADR-001：核心作为独立控制层。
- ADR-002：MVP 技术栈选择。
- ADR-003：Discovery 与 Execution 分离。
- ADR-004：SQLite 状态与 JSONL 事件。
- ADR-005：Executor 语言无关协议。
- ADR-006：Verifier 生成、权限和冻结。
- ADR-007：Git worktree 隔离。
- ADR-008：Memory 与 Context Builder。

## 23. 风险与待验证假设

| 风险 | 缓解方案 |
|---|---|
| Codex CLI JSONL 格式变化 | capability 检测、版本记录、fixture 和 adapter 隔离 |
| 动态 Verifier 执行恶意代码 | 最小权限、allowlist、冻结、后续容器隔离 |
| Agent 修改测试以通过 | 冻结外部 Verifier、保护路径、独立审查和 diff 检查 |
| 自然语言 Contract 存在歧义 | 缺失项检测、结构化摘要和用户确认 |
| Context Builder 遗漏关键信息 | 不可摘要 Contract、证据引用、handoff schema 和评测 |
| 外部 CI 重复触发 | 幂等键、external handle checkpoint 和恢复查询 |
| 长任务成本失控 | 节点、attempt、时间和调用预算 |
| Python 分发体验不足 | 首版 uvx/pipx，稳定后提供独立二进制或评估 Go 重写 |
| 多平台 shell 差异 | 命令 argv 优先、平台适配和 Windows/Linux CI |

需要通过原型验证的假设：

- Codex JSONL 事件能稳定提供 Session ID 和最终结构化结果。
- `codex exec resume` 适合短范围修复循环。
- 仅使用 Repository Map、Handoff 和按需文件读取即可支撑中型任务。
- HTTP Pipeline DSL 能覆盖多数企业流水线场景。
- 用户愿意在自治执行前 Review 权限与验收摘要。

## 24. MVP 完成定义

满足以下条件才称为 MVP：

1. 用户能在真实 Git 仓库中通过 `ge start` 描述需求。
2. 系统能询问测试、上下游、规范、权限和交付等缺失信息。
3. 用户能确认并冻结 Contract 与 Verifier。
4. Runtime 能在隔离 worktree 中调用 Codex 完成实现。
5. Runtime 能运行本地 Command Verifier 和异步 HTTP Pipeline Verifier。
6. 测试失败可以自动修复，基础设施错误不会误触发代码修改。
7. 长任务跨多个 Codex Session，通过结构化 Handoff 延续。
8. Runtime 中断后能够恢复，不重复关键外部副作用。
9. 独立 Review 节点可以要求修复并重新验证。
10. 最终报告包含需求、代码、测试、CI 和审查证据。
11. 人可以接受或拒绝成果，系统默认不自动合并。

## 25. Review 清单

Review 本文档时建议逐项确认：

- [ ] 项目定位是否准确。
- [ ] 独立 Runtime 与 Plugin 的边界是否合理。
- [ ] Discovery 和 Execution 的人机边界是否符合预期。
- [ ] Contract 是否覆盖需要确认的信息。
- [ ] 动态 Verifier 的生成和冻结机制是否可接受。
- [ ] Codex Session 与外部 Memory 的设计是否足够可靠。
- [ ] 权限、secret、网络和工作区隔离是否满足目标用户。
- [ ] MVP 技术栈是否选择 Python，还是改为 Go/Rust/TypeScript。
- [ ] 分阶段顺序和每阶段验收条件是否合理。
- [ ] GitHub PR 是否必须进入 MVP。
- [ ] MVP 是否需要支持 Windows、Linux 和 macOS。
- [ ] 是否需要在首版支持容器级隔离。
