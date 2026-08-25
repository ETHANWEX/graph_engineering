# Graph Engineering

Graph Engineering 是一个面向自治软件开发的图工程控制层。Human 通过自然语言定义需求和授权边界、随时查询或中断开发，并最终验收成果；Graph Runtime 在冻结的 Contract 内组织 Coding Agent、确定性工具、Verifier、反馈循环和外部系统，持续完成实现、验证、修复、审查与证据交付。

> 当前状态：Phase 6G Optional Project UI 已在 `phase/6-enhancements` 上完成本地实现与验证，
> 并进入本次已授权的单一 delivery commit 门禁。实现 baseline 与远端 Phase 6 HEAD 均为已由
> Human 审核、接受并推送的 Phase 6F delivery
> `ba30339922f9412cc369063efa2c136e0a3aef1f`。UI 是可选 presentation layer；Runtime SQLite
> 仍是唯一 Run 权威，Human 消息与确认继续经过既有 Human Gateway。Phase 6 已排期路线至此结束；
> 不会自动开始后续或未排期工作。

## 已实现能力

Phase 0–6F 已交付能力与 Phase 6G 可选 presentation layer 提供：

- Python 3.12–3.13、Pydantic v2 和 Typer 的可安装 `src` layout 包。
- 版本化 Task Contract、Execution Graph、Result、Control、Run 关系和 Report 协议。
- 36 个工作树公共 JSON Schema，以及稳定性测试。
- JSON/YAML Execution Graph 静态校验；错误包含字段路径并返回非零退出码。
- 合法/非法 fixtures、全量回归测试、mypy 严格类型检查和 Ruff 检查。
- SQLite State Store（含迁移、事务状态机、checkpoint 和事件 outbox）。
- 追加式 JSONL Event Store 与内容寻址 Artifact Store。
- 单机、单任务、串行 Graph Runtime：受限条件边、修复循环、重试上限、Run/Node
  调用/时间/修复/成本预算和终止。
- Fake Executor/Fake Verifier，以及 checkpointed external handle 的恢复和防重复触发。
- 强类型 Python Control API、pause/resume/interrupt 执行屏障、只读快照与 LiveReport。
- RunRelationship/RestartFrom 校验、同图 checkpoint 状态继承和来源 Run 不可变性。
- Artifact metadata/角色关联，以及聚合 changed files 和验证证据的基础 FinalReport。
- provider-neutral `start/resume/review/cancel/capabilities` Executor 协议和持久 Session 策略。
- Codex 0.147.0 help-derived preflight、登录/版本记录、安全 argv、JSONL 兼容解析、严格结构化
  输出和原始 stdout/stderr Artifact。
- 确定性、限长 Context Builder、可重建 Repository Map 和结构化 Handoff。
- 每 Run 独立 Git branch/worktree、accepted-commit materialization，以及 control/evidence 外置。
- 全新只读 Reviewer/Observer、Observer 执行指纹隔离和 review-fix→Verifier→fresh review 路由。
- argv-only Command Verifier，区分 failed/error，并限制 timeout 与输出字节数。
- SQLite migration 3：Executor Session、受控进程、review attempt 和 verifier execution 元数据。
- `ge start` 持久 Human Control Conversation；所有自然语言先追加为不可变 `HumanMessage`。
- fail-closed 意图编译：query/status/report 与 pause/resume/interrupt/revise/restart/accept/reject
  保持协议类型隔离；歧义、低置信度、缺少目标或需确认动作不会直接进入 Runtime。
- 确定性限长项目预扫描、未知项识别、多轮 Discovery、缺少测试方式的强制追问与重启恢复。
- 结构化 Contract draft、风险/权限摘要、显式确认、acceptance lock 与不可覆盖的 frozen revision。
- 结构化 Contract delta、append-only revision，以及新 Run 的 parent/supersedes/restart lineage。
- frozen Contract 到标准串行 Execution Graph 的确定性编译，不执行模型文本或任意源码。
- 自然语言 query 复用 fresh read-only Observer；pause/interrupt 使用统一持久化 barrier guard，
  阻止新 Session、Verifier 和 worktree 写入。
- Codex read-only structured Discovery Adapter；JSONL 保留在 Adapter，原始 stdout/stderr 进入
  Artifact Store。SQLite migration 4 保存 Conversation、Discovery、confirmation、Contract 和
  prepared Run 元数据。
- exact-name Verifier Registry/SDK，兼容 `builtin/command`，新增声明式
  `builtin/http-pipeline` 与结构化 `project/subprocess`。
- HTTP trigger/idempotency key、external handle checkpoint、poll/restart recovery、bounded
  retry/backoff、report Artifact、cancel 和 redirect allowlist 复核。
- Manifest runtime/entrypoint/network/filesystem/secret/external-side-effect capability；网络默认
  拒绝、host 精确 allowlist、argv-only subprocess 和 JSON stdin/stdout。
- secret 仅按引用注入；raw、URL encoded、base64、overlap 和跨 chunk 日志在进入 Artifact、
  error 或报告前脱敏，Codex prompt 永不包含 secret 值。
- validate/test/dry-run/Human permission summary/freeze 生命周期；Manifest/source/tests/fixtures
  hash 与 Contract revision 绑定，冻结漂移在副作用前拒绝。
- declaration-first Discovery 与 Codex structured Verifier bundle generation；Manifest、实现、
  fixtures、tests、raw JSONL/stderr 均独立验证或保存。
- SQLite migration 5 保存 Verifier revision/lifecycle evidence/Contract binding，并扩展 external
  handle 的 verifier owner、cancel state、report 和 residual-effect 元数据。
- 四维 Contract/Correctness/Security/Test Adequacy Review、确定性阻断聚合、Reviewer error
  隔离、fresh read-only Session/attempt 和持久化 review-fix 上限。
- 每个冻结验收条件一行的 append-only requirement matrix；只有冻结或内容寻址证据可标记
  verified，缺失/可变证据明确 unverified。
- 精确 repository/commit 绑定的 GitHub Checks 状态、错误分类、bounded poll 和重启恢复查询。
- checkpointed PR intent/handle、精确 head/base 所有权、稳定幂等键、恢复防重复、barrier 和
  不确定创建结果停止；没有 merge API。
- 所有终态的十文件版本化 delivery bundle、只读 `ge report`，以及经 HumanMessage、Intent
  Compiler 和确认策略的 `ge accept` / `ge reject`；accept 永不 merge。
- SQLite migration 6 与 Phase 0–4 compatibility views；公共 Schema 1.0 仍为 30 个且无变化。
- 171 个 pytest 测试（167 passed / 4 个真实 Codex 测试默认跳过）；启动时 Phase 0–5 的
  156 collected / 152 passed / 4 skipped 基线保持。
- Phase 6A foreground Runtime Service、私有 project-local endpoint、health/version 和受控停止；
  Windows 子进程退出与 Runtime 重启后从 SQLite 恢复 Conversation/Run 路由。
- versioned/authenticated loopback IPC、project/workspace/request/idempotency identity、typed error、
  有限 frame/timeout/retry，以及 mutation replay ledger；查询路径不写 Runtime 状态。
- `ge mcp-server` 保留 `start/message/confirm/status/report` 五工具兼容前缀，并加法提供
  `run/pause/resume/interrupt/cancel/accept/reject/revise`；全部复用 Human Gateway、
  HumanMessage、Intent Compiler、确认策略、强类型 Runtime control 和只读 report/status API。
- 仓库内 `plugins/graph-engineering` Codex Plugin（manifest、Skill、MCP config）；它不保存权威
  Run 状态，也不直接写 SQLite/worktree/external handle。
- 强类型 `parallel`、显式 `subgraph` 与 `join` 节点；branch ID 和 join aggregate 不依赖完成顺序。
- 有界本机并发、SQLite 原子共享调用/成本预算、durable branch/node/attempt/checkpoint 状态，
  restart 跳过已完成工作并轮询 checkpointed external handle。
- active/pending branch 的 pause、interrupt、cancel durable barrier；聚合按
  `error > blocked > failed > cancelled > succeeded` fail closed。
- SQLite migration 8 保持 migration 1–7 和 Phase 6A service compatibility 可读；串行 Graph
  canonical SHA、Runtime Service、IPC、MCP 和 Plugin 行为保持兼容。
- `project/container` Verifier provider 与 Docker-compatible adapter；digest/platform/provenance
  不可变镜像身份、精确 allowlist、冻结 config fingerprint 和 typed runtime preflight。
- CPU/memory/PID/wall-clock/output/Artifact/concurrency 限额；已授权 root mount、
  symlink/junction/reparse 逃逸拒绝、只读 frozen/evidence 和显式最小 writable mount。
- 默认 `network=none`；启用网络需 exact protocol/host/port 冻结策略与可靠执行
  adapter，否则 fail closed。Secret 仅引用注入并覆盖 raw/URL/base64/overlap/跨 chunk 脱敏。
- SQLite migration 9 持久化 container owner/attempt/handle/digest/fingerprint/result/cleanup/
  residual state；恢复查询已有 handle、不重复启动，cleanup 失败进入 Event、Artifact
  和 Final Report。历史 migration compatibility views 保持。
- confirmation 与 Run start 是独立幂等动作；durable coordinator 复用 Graph Runtime 完成
  Implementer→Verifier/repair→fresh Review/review-fix→delivery→十文件 Final Report，unknown
  start/provider effect fail closed，accept 永不 merge，revise 创建不可变 successor lineage。
- `ge run/status --watch/pause/resume/interrupt/cancel/report --live/accept/reject/revise` 是 typed
  Runtime/API route；deterministic local Git fixture 明确不冒充真实 Codex/GitHub/container E2E。
- SQLite migration 10 保存 start claim 与 delivery stage checkpoint，并保持 migration 1–10、
  historical database 和旧 compatibility view 可读。
- 225 个 pytest collected 实例（221 passed / 4 个真实 Codex 实例默认跳过）；mypy strict、Ruff、
  36-schema drift、Graph CLI 和 migration 1–10 repeatability 全部通过。
- 独立于 Runtime SQLite 的 qualification evidence 1.0、secret-safe claim matrix、append-only
  evidence 文件和只读 `ge qualification report`；blocked/unverified 永不映射为 passed。
- 固定 `SOURCE_DATE_EPOCH` 的可重复 wheel/sdist、本地 Python 3.12/3.13 clean install、
  Service/IPC/MCP smoke，以及 Phase 6D wheel 到当前 build 的数据保留升级资格证据。
- observability contract 1.0 与 dependency-free OpenTelemetry provider boundary；默认 disabled/
  no-op，支持 deterministic sampling、parent/link、持久 identity correlation、bounded attribute/
  metric labels、buffer/batch/flush/shutdown 和 exporter failure isolation。
- Runtime/parallel/recovery、Service/IPC/MCP、Agent Session、Verifier/container cleanup、Review/
  review-fix、GitHub、Final Report 和 Human decision instrumentation；telemetry 不进入 SQLite、
  route、budget、barrier、terminal 或 external-effect authority。

开发安装：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

当前 CLI 主入口包括：

```powershell
ge start --project-root .
ge service start --project-root . --project-id project
ge service status --project-root .
ge service stop --project-root .
ge ui serve --project-root . --project-id project --actor-id human
ge mcp-server --project-root .
ge report <run-id>
ge accept <run-id>
ge reject <run-id> --reason "..."
ge graph validate tests/fixtures/valid/graph.yaml
ge verifier list
ge verifier validate tests/fixtures/verifier/valid.json
ge schema export --output schemas
ge qualification collect --output qualification.json
ge qualification report qualification.json
```

`ge start` 可跨进程恢复同一 Conversation、Discovery unknown、Contract draft 和待确认状态。
确认前不会创建 acceptance lock、Execution Graph Run 或 Implementer Session；确认后只准备冻结
Contract 和标准 Graph，自治执行仍由显式 Runtime 集成启动。

`graph validate` 只检查结构、节点引用和受限路由条件，不执行节点。开发和贡献命令见 [CONTRIBUTING.md](CONTRIBUTING.md)。

Phase 1–2 Runtime 的确定性 API 保持兼容。Executor 边界仍通过强类型 Python API 组合：

```python
from pathlib import Path

from graph_engineering.adapters.codex import CodexAdapter
from graph_engineering.executor import DurableExecutorRuntime, SessionPolicy
from graph_engineering.runtime import ArtifactStore, SessionRepository, StateStore

state = StateStore(Path(".ge/runs/run-1/state.db"))
adapter = CodexAdapter(artifact_store=ArtifactStore(Path(".ge/runs/run-1/artifacts")))
executor = DurableExecutorRuntime(adapter, SessionRepository(state), SessionPolicy())
```

请求必须显式提供工作目录、workspace-write/read-only sandbox、限长 Context 和输出 Schema。
Adapter 固定 approval policy `never`，拒绝 dangerous bypass。Codex 0.147.0 的原生
`exec review` 不兑现结构化最后消息，因此结构化 Reviewer 使用全新 read-only `codex exec`；
此兼容事实记录于 ADR-008。

官方 OpenAI 文档确认 `codex exec --json` 输出 JSONL 事件，`--output-schema` 约束最终响应，
自动化应使用最小 sandbox 权限：<https://learn.chatgpt.com/docs/non-interactive-mode>。本机实际
CLI help 和登录状态仍是 Adapter 的运行时事实来源。

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
| Phase 6 | Runtime/MCP/Plugin、并行图、R0 状态恢复、容器、自治交付闭环、真实集成认证、遥测和可选 UI；Claude Code 暂未排期 |

Phase 0–5 构成当前 MVP；Phase 6 是后续增强。任何阶段未满足验收条件前，不进入下一阶段。

## 当前开发状态

- 已合并阶段：Phase 0–5；Phase 5 通过 PR #6 进入 `origin/main`，实现/交接提交为
  `db7dd54` / `4ebeb2d`。
- 当前分支：`phase/6-enhancements`；本地与远端 Phase 6 HEAD 均为 Phase 6F delivery
  `ba30339922f9412cc369063efa2c136e0a3aef1f`，其唯一 parent 是 Phase 6E delivery
  `e1aa9c61f568b7dda6c77248bc87a000f539a0ca`。
- 当前活动门禁：创建经本次 Human 授权的单一 Phase 6G delivery commit。Phase 6F 已由 Human
  接受并推送；其冻结 handoff 不重写。Phase 6 已排期路线在 6G 后结束。
- 未授权外推：push、PR、main 修改/merge、package/Plugin/UI 发布或外部 hosting；Phase 6G
  完成后不得开始 Claude Code Adapter、分布式 worker 或未排期阶段。
- GitHub CLI 2.97.0 已安装，`pr`、`run`、`api` 命令入口可用；当前未登录任何 GitHub host，
  因此私有仓库读取和真实 GitHub E2E 仍保持未验证。隔离 provider fixture 不冒充真实 E2E。
- 当前设计：[DESIGN.md](DESIGN.md)
- 跨对话状态：[docs/status/CURRENT.md](docs/status/CURRENT.md)
- Phase 0 范围：[docs/phases/phase-0.md](docs/phases/phase-0.md)
- Phase 0 交接：[docs/phases/phase-0-handoff.md](docs/phases/phase-0-handoff.md)
- Phase 1 范围：[docs/phases/phase-1.md](docs/phases/phase-1.md)
- Phase 1 交接：[docs/phases/phase-1-handoff.md](docs/phases/phase-1-handoff.md)
- Phase 2 范围：[docs/phases/phase-2.md](docs/phases/phase-2.md)
- Phase 2 交接：[docs/phases/phase-2-handoff.md](docs/phases/phase-2-handoff.md)
- Phase 3 范围：[docs/phases/phase-3.md](docs/phases/phase-3.md)
- Phase 3 交接：[docs/phases/phase-3-handoff.md](docs/phases/phase-3-handoff.md)
- Phase 4 范围：[docs/phases/phase-4.md](docs/phases/phase-4.md)
- Phase 4 交接：[docs/phases/phase-4-handoff.md](docs/phases/phase-4-handoff.md)
- Phase 5 范围：[docs/phases/phase-5.md](docs/phases/phase-5.md)
- Phase 5 交接：[docs/phases/phase-5-handoff.md](docs/phases/phase-5-handoff.md)
- Phase 6 总路线：[docs/phases/phase-6.md](docs/phases/phase-6.md)
- Phase 6A 范围：[docs/phases/phase-6a.md](docs/phases/phase-6a.md)
- Phase 6A 启动 Prompt：[docs/prompts/phase-6a-start.md](docs/prompts/phase-6a-start.md)
- Phase 6B 范围：[docs/phases/phase-6b.md](docs/phases/phase-6b.md)
- Phase 6B 交接：[docs/phases/phase-6b-handoff.md](docs/phases/phase-6b-handoff.md)
- Recovery Gate R0：[docs/phases/phase-6r.md](docs/phases/phase-6r.md)
- Recovery Gate R0 交接：[docs/phases/phase-6r-handoff.md](docs/phases/phase-6r-handoff.md)
- Recovery Gate R0 启动 Prompt：[docs/prompts/phase-6r-start.md](docs/prompts/phase-6r-start.md)
- Phase 6C 启动 Prompt：[docs/prompts/phase-6c-start.md](docs/prompts/phase-6c-start.md)
- Phase 6C 范围：[docs/phases/phase-6c.md](docs/phases/phase-6c.md)
- Phase 6C 交接：[docs/phases/phase-6c-handoff.md](docs/phases/phase-6c-handoff.md)
- Phase 6D 启动 Prompt：[docs/prompts/phase-6d-start.md](docs/prompts/phase-6d-start.md)
- Phase 6D 范围：[docs/phases/phase-6d.md](docs/phases/phase-6d.md)
- Phase 6D 交接：[docs/phases/phase-6d-handoff.md](docs/phases/phase-6d-handoff.md)
- Phase 6E 范围：[docs/phases/phase-6e.md](docs/phases/phase-6e.md)
- Phase 6E release readiness：[docs/qualification/phase-6e-release-readiness-v1.md](docs/qualification/phase-6e-release-readiness-v1.md)
- 协作约定：[AGENTS.md](AGENTS.md)

README 是项目对外的首要入口。每个阶段完成时都必须同步更新这里的架构、已实现能力、安装方式、示例命令和限制，避免 README 描述超前于代码。
