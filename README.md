# Graph Engineering

Graph Engineering 是一个面向自治软件开发的图工程控制层。Human 通过自然语言定义需求和授权边界、随时查询或中断开发，并最终验收成果；Graph Runtime 在冻结的 Contract 内组织 Coding Agent、确定性工具、Verifier、反馈循环和外部系统，持续完成实现、验证、修复、审查与证据交付。

> 当前状态：Phase 1（持久化 Graph Runtime）已经实现并通过本阶段验证。现在可安装的是公共协议、静态 Graph 校验，以及使用 Fake Executor/Verifier 的单机串行 Runtime；真实 Coding CLI、自然语言控制面和后台 daemon 尚未实现。

## 已实现能力

Phase 0–1 当前提供：

- Python 3.12+、Pydantic v2 和 Typer 的可安装 `src` layout 包。
- 版本化 Task Contract、Execution Graph、Result、Control、Run 关系和 Report 协议。
- 30 个提交到 `schemas/` 的公共 JSON Schema，以及稳定性测试。
- JSON/YAML Execution Graph 静态校验；错误包含字段路径并返回非零退出码。
- 合法/非法 fixtures、36 个单元测试、mypy 严格类型检查和 Ruff 检查。
- SQLite State Store（含迁移、事务状态机、checkpoint 和事件 outbox）。
- 追加式 JSONL Event Store 与内容寻址 Artifact Store。
- 单机、单任务、串行 Graph Runtime：受限条件边、修复循环、重试上限、Run/Node
  调用/时间/修复/成本预算和终止。
- Fake Executor/Fake Verifier，以及 checkpointed external handle 的恢复和防重复触发。
- 强类型 Python Control API、pause/resume/interrupt 执行屏障、只读快照与 LiveReport。
- RunRelationship/RestartFrom 校验、同图 checkpoint 状态继承和来源 Run 不可变性。
- Artifact metadata/角色关联，以及聚合 changed files 和验证证据的基础 FinalReport。
- 62 个 pytest 测试（Phase 0 的 36 个与 Phase 1 的 26 个）。

开发安装：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

当前 CLI 命令仍为：

```powershell
ge graph validate tests/fixtures/valid/graph.yaml
ge schema export --output schemas
```

`graph validate` 只检查结构、节点引用和受限路由条件，不执行节点。开发和贡献命令见 [CONTRIBUTING.md](CONTRIBUTING.md)。

Phase 1 Runtime 通过强类型 Python API 使用；它只接受已验证的 `ExecutionGraph`、`Budget`、
`QueryControlIntent`/`StateChangeControlIntent` 和 Fake 执行边界：

```python
from pathlib import Path

from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime

runtime = GraphRuntime(
    Path(".ge/runs/run-1"),
    executor=FakeExecutor({...}),
    verifier=FakeVerifier({...}),
)
runtime.create_run("run-1", "project-1", graph, contract_hash, budget)
terminal_status = runtime.run("run-1")
report = runtime.final_report("run-1")
```

该 API 是 Phase 1 的确定性内核入口，不会调用真实模型、Shell、HTTP 或 Coding CLI。

## 为什么需要 Graph Engineering

Prompt Engineering 关注一次指令，Context Engineering 关注一次任务所见的信息，Harness Engineering 为单个 Agent 提供工具、权限和环境，Loop Engineering 利用测试和反馈使局部任务收敛。Graph Engineering 继续向上组织：

```text
Harness Engineering
  单个 Agent 节点拥有正确的上下文、工具和权限
          ↓
Loop Engineering
  实现、验证、失败反馈和修复形成局部闭环
          ↓
Graph Engineering
  将多个 Agent、确定性工具、循环、外部系统和 Human 边界
  组织为可组合、可恢复、可观察、可中断、可审计的执行图
```

它要解决的不是“再包装一次模型调用”，而是长时间自治开发中的控制问题：

- 需求、权限和验收标准不能只存在于聊天记录。
- Coding Agent 的上下文可能被压缩、轮换或丢失。
- 实现、验证和审查需要职责隔离。
- 外部 CI 和其他副作用需要可靠等待、恢复和幂等处理。
- Human 查询进度不能污染正在执行的 Agent Session。
- Human 发现方向错误时必须能通过自然语言立即暂停、中断和修订。
- 成功、失败或中断都必须留下可交付报告。

## 核心原则

1. **边界内自治**：Human 定义目标、权限、预算和验收标准，系统在已确认边界内自主工作。
2. **自然语言控制面**：Human 不需要记忆控制命令，通过项目主对话即可查询、暂停、中断、修订、恢复和验收。
3. **查询不干扰执行**：Observer/Reporter 与 Implementer Session 隔离，只读取持久化状态和证据。
4. **Human 保留最终控制权**：Human 可以随时中断错误方向，最终成果必须由 Human accept/reject，默认不自动合并。
5. **冻结契约**：确认后的 Contract、Verifier 和 acceptance lock 对实现 Agent 只读；方向变化创建新 Contract 和新 Run。
6. **Runtime 是事实来源**：任务状态不依赖 Codex、Claude Code 或某个聊天 Session。
7. **所有终态都有报告**：成功、失败、中断、取消和拒绝都必须生成 Final Report。

## 架构

```text
┌────────────────────────────────────────────────────┐
│ Frontends                                          │
│ ge CLI · Codex Plugin · MCP · future Web/IDE UI    │
└────────────────────────┬───────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────┐
│ Human Gateway                                      │
│ Control Conversation · Intent Compiler             │
│ Observer/Reporter · Confirmation Policy            │
└───────────────┬──────────────────────┬─────────────┘
                ↓                      ↓
┌───────────────────────────┐  ┌─────────────────────┐
│ Discovery Graph           │  │ Runtime Control API │
│ Repo Inspect · Contract   │  │ Query · Pause       │
│ Verifier · Risk Review    │  │ Interrupt · Revise  │
└───────────────┬───────────┘  └──────────┬──────────┘
                ↓ freeze                  ↓
┌────────────────────────────────────────────────────┐
│ Graph Runtime                                      │
│ Compiler · Scheduler · State · Events · Policy     │
│ Context · Artifact · Report · Checkpoint/Resume    │
└──────────────────┬──────────────────────┬──────────┘
                   ↓                      ↓
┌───────────────────────────┐  ┌─────────────────────┐
│ Coding Executors          │  │ Verifiers           │
│ Codex · future Claude Code│  │ Command · HTTP · CI │
└──────────────────┬────────┘  └──────────┬──────────┘
                   └───────────┬──────────┘
                               ↓
              Git worktree · Shell · Network · GitHub
```

自然语言不会直接操作 Runtime。Human Gateway 先将消息编译为受限、强类型、可审计的 Control Intent，再由确定性 Control API 校验状态和权限后执行。

```text
Human: “这个实现方向不对，先停下来，改成事件驱动。”
  ↓
interrupt_and_revise
  ↓
阻止新副作用 → 安全 checkpoint → 冻结旧 Run 报告
  ↓
Contract v2 草案 → Human 确认 → 新 Run
```

## 计划中的使用方式

初始化项目并开始自然语言对话：

```powershell
ge init
ge start
```

Human 可以在同一个项目对话中直接表达：

```text
“为订单服务增加批量取消接口，最多 100 个，允许部分成功。”
“现在做到哪里了，还有什么风险？”
“先暂停，我想看看当前 diff。”
“这个方向不对，停止当前实现，改用事件驱动。”
“按修订后的 Contract 重新开始。”
“我接受这次交付，但不要自动合并。”
```

查询由只读 Observer/Reporter 回答，不会进入 Implementer Session。明确的暂停或中断会先建立执行屏障，阻止启动新节点和外部副作用；如果需求发生变化，Runtime 不会修改旧 Contract，而是生成新版本供 Human 确认。

CLI 仍会提供确定性控制命令，主要用于自动化、调试和底层集成；普通用户不需要依赖这些命令完成控制。

## 一次任务的生命周期

```text
自然语言需求与仓库探索
  → Contract / Verifier / Graph 草案
  → Human 确认并冻结
  → 自治实现 / 验证 / 修复 / 独立审查
  → Human 可随时无干扰查询或中断
  → 每个终态生成 Final Report
  → Human accept / reject / revise
  → 明确批准后才允许 merge
```

Final Report 计划包含：需求与 Contract 版本、代码变更、测试和 CI、Review findings、执行时间线、Human 控制历史、成本、未验证事项、外部副作用、残留风险以及恢复或修订建议。

## 实施路线

| 阶段 | 交付目标 |
|---|---|
| Phase 0 | Python 工程骨架、核心协议模型、JSON Schema、静态 Graph 校验 |
| Phase 1 | SQLite/JSONL 持久化、串行 Runtime、非阻塞查询、中断与恢复 |
| Phase 2 | Codex Executor、Context/Memory、独立 Reviewer 和 Observer |
| Phase 3 | 持续自然语言控制对话、Discovery、Contract 冻结与修订 |
| Phase 4 | 动态 Verifier、HTTP Pipeline、secret 和外部副作用控制 |
| Phase 5 | 多维 Review、GitHub PR、证据矩阵和所有终态 Final Report |
| Phase 6 | Codex Plugin、Claude Code、并行图、容器、遥测和可选 UI |

Phase 0–5 构成当前 MVP；Phase 6 是后续增强。任何阶段未满足验收条件前，不进入下一阶段。

## 当前开发状态

- 已完成阶段：Phase 0；Phase 1 已在 `phase/1-runtime` 实现、通过本阶段验证并获 Human 认可，交付分支等待集成。
- 已实现边界：协议、Schema、静态 Graph 校验、SQLite/JSONL/Artifact 持久化、串行 Fake Runtime、控制屏障、恢复和基础报告。
- 尚未实现：真实 Executor/Verifier Adapter、Codex、Context Builder、Git worktree、自然语言 Human Gateway、daemon、HTTP、GitHub、Plugin/MCP/UI。
- 当前设计：[DESIGN.md](DESIGN.md)
- 跨对话状态：[docs/status/CURRENT.md](docs/status/CURRENT.md)
- Phase 0 范围：[docs/phases/phase-0.md](docs/phases/phase-0.md)
- Phase 0 交接：[docs/phases/phase-0-handoff.md](docs/phases/phase-0-handoff.md)
- Phase 1 范围：[docs/phases/phase-1.md](docs/phases/phase-1.md)
- Phase 1 交接：[docs/phases/phase-1-handoff.md](docs/phases/phase-1-handoff.md)
- 协作约定：[AGENTS.md](AGENTS.md)

README 是项目对外的首要入口。每个阶段完成时都必须同步更新这里的架构、已实现能力、安装方式、示例命令和限制，避免 README 描述超前于代码。
