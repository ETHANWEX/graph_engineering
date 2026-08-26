# Graph Engineering

Graph Engineering 是一个面向自治软件开发的、provider-neutral 的控制层。它把需求、权限、预算、执行状态和验收证据从临时聊天上下文中移出，交给持久化的 Graph Runtime；Coding Agent 只负责需要推理的节点，状态迁移、中断恢复、验证、审查和交付由确定性代码控制。

> 当前成熟度：Phase 0–6G 已合入 `main`，形成可安装的 **0.8.0 MVP / 工程原型**。持久 Runtime、自然语言控制面、串行与并行图、Verifier、交付报告、MCP、Codex Plugin 和本地 UI 已实现并经过确定性测试。真实 Codex 尚未接入 `ge run` 的自治交付入口；该命令目前只允许显式的 deterministic fixture。真实 GitHub、容器、OTLP 和跨平台组合也仍缺少完整环境证据。详见 [当前缺口](docs/missing-items.md)。

## 它解决什么问题

长时间运行的 Coding Agent 容易把需求、状态和验收条件都压在一次会话里：上下文压缩后细节丢失，Agent 可能既实现又自审，CI 等外部副作用难以恢复，Human 查询或改方向又可能污染执行上下文。

Graph Engineering 把这些问题建模为一张可恢复、可审计、可中断的执行图：

```text
Human 自然语言
  → HumanMessage / ControlIntent
  → Discovery / frozen TaskContract
  → prepared ExecutionGraph
  → Implementer → Verifier ⇄ Repair → Reviewer ⇄ Review Fix → Delivery
  → immutable evidence / Final Report
  → Human accept / reject / revise（永不自动 merge）
```

核心约束：

- Runtime SQLite 是 Run 状态的唯一权威；CLI、MCP、Plugin 和 UI 都是薄入口。
- 自然语言先落库，再编译成受限的强类型意图；不会直接修改 Runtime。
- Contract、Verifier 和 acceptance lock 冻结后只读，方向变化创建新 revision 和新 Run。
- `failed`（实现不满足验收）与 `error`（基础设施异常）分开路由。
- Observer/Reviewer 使用独立只读上下文，查询不进入 Implementer Session。
- 外部副作用使用 checkpoint、幂等键和显式的不确定状态；不能证明成功时 fail closed。
- Human accept 只记录验收结论，项目没有自动 merge API。

## 已实现的 MVP

| 领域 | 当前能力 |
|---|---|
| 协议与持久化 | Pydantic 强类型协议、36 个 JSON Schema、SQLite migration 1–10、JSONL Event Store、内容寻址 Artifact Store |
| Runtime | 串行图、显式并行 subgraph/join、本机有界并发、预算、条件路由、checkpoint、pause/resume/interrupt/cancel、崩溃恢复 |
| Agent 边界 | provider-neutral Executor、Codex 0.147.0 Adapter、持久 Session、限长 Context/Repository Map/Handoff、每 Run 独立 Git worktree |
| Discovery 与控制 | 持久 Human Conversation、确定性项目预扫、7 类必答澄清项、Contract freeze/revise/restart lineage、只读 Observer |
| Verifier | Command、HTTP Pipeline、受限 subprocess、container provider；能力 allowlist、secret 引用与多形态脱敏、冻结生命周期 |
| Review 与交付 | 四维独立 Review、review-fix 闭环、requirement matrix、GitHub Checks/PR provider、所有终态的十文件报告包 |
| 产品入口 | Typer CLI、foreground Runtime Service、认证 loopback IPC、MCP server、Codex Plugin、本地 loopback Project UI |
| 工程资格 | Python 3.12/3.13、本地可重复 wheel/sdist、mypy strict、Ruff、262 passed / 4 opt-in real-Codex skipped（Phase 6G 交付证据） |

这里的“已实现”不等于所有真实 provider 组合都已经验证。支持等级和未接线能力见 [docs/missing-items.md](docs/missing-items.md)。

## 安装

要求：Python 3.12 或 3.13，Git。当前仓库尚未发布到 PyPI，请从源码安装。

### Windows PowerShell

```powershell
git clone https://github.com/ETHANWEX/graph_engineering.git
cd graph_engineering
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\ge --help
```

开发环境：

```powershell
.venv\Scripts\python -m pip install -e ".[dev]"
```

### Linux / macOS

```bash
git clone https://github.com/ETHANWEX/graph_engineering.git
cd graph_engineering
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/ge --help
```

Linux/macOS 的安装命令是标准 Python 用法，但项目当前没有这两个平台的正式资格矩阵，不能据此宣称完整支持。

## 五分钟体验

### 1. 创建持久对话并生成 Contract / Graph

在一个你允许写入 `.ge/` 的 Git 仓库中运行：

```powershell
ge start --project-root . --message "为订单服务增加批量取消接口"
```

随后继续运行 `ge start --project-root .`，按提示回答验证命令、验收行为、依赖、规范、权限、交付方式和预算。最后输入 `confirm`。系统会冻结 Contract、创建 acceptance lock 并准备 Execution Graph，同时明确提示：**自治执行尚未开始**。

这个版本没有 `ge init` 命令；首次 `ge start` 会在项目中创建 `.ge/` 状态目录。

### 2. 启动 Runtime Service 和本地 UI

终端 A（前台服务）：

```powershell
ge service start --project-root . --project-id project
```

终端 B：

```powershell
ge service status --project-root .
ge ui serve --project-root . --project-id project --actor-id human --port 8765
```

浏览器打开 UI 输出的地址（例如 `http://127.0.0.1:8765`）。UI 只连接 loopback Runtime Service，不直接读取 SQLite、worktree 或 secret；关闭 UI 不会改变权威状态。停止服务：

```powershell
ge service stop --project-root .
```

### 3. 体验确定性自治闭环

准备好 Run 后，可显式运行测试 fixture：

```powershell
ge run <run-id> --project-root . --deterministic-fixture
ge status <run-id>
ge report <run-id>
```

这条路径用于验证编排、恢复和交付语义，不会调用真实 Codex，也不应作为真实自治编码演示。真实 Codex Adapter 可以独立调用并有 opt-in 测试，但尚未接入上述产品入口。

## 常用命令

```text
ge start                         持久自然语言对话、Discovery、Contract/Graph 准备
ge run                           显式启动 prepared Run（当前仅 deterministic fixture）
ge status                        读取 Run snapshot
ge pause|resume|interrupt|cancel 强类型控制
ge report                        读取不可变交付报告
ge accept|reject|revise          记录 Human 决策；accept 不会 merge
ge service start|status|stop     单项目 Runtime Service
ge ui serve                      可选本地 Project UI
ge mcp-server                    stdio MCP 控制面
ge verifier list|validate|...    Verifier 注册与生命周期工具
ge graph validate                静态校验 Execution Graph
ge schema export                 导出公共 JSON Schema
ge qualification collect|report 采集/读取诚实的集成资格证据
```

以 `ge <command> --help` 为准。MCP/Plugin 入口见 [Plugin README](plugins/graph-engineering/README.md)，UI/API 安全边界见 [Project UI contract](docs/contracts/project-ui-api-1.0.md)。

## 架构

```text
CLI · MCP · Codex Plugin · Local UI
                 │
          Human Gateway
  Conversation · Intent · Observer · Confirmation
          │                    │
     Discovery Graph      Runtime Control API
          └──────────┬─────────┘
                     ▼
        Persistent Graph Runtime
 State · Event · Policy · Budget · Checkpoint · Report
          │                         │
   Coding Executors              Verifiers
 Codex Adapter / fakes   Command · HTTP · subprocess · container
          └──────────┬──────────────┘
                     ▼
       Git worktree · shell · GitHub · external systems
```

关键代码入口：

- `src/graph_engineering/runtime/`：状态存储、串行/并行调度、屏障、Session 和恢复。
- `src/graph_engineering/service/`：Human Gateway、认证 IPC、snapshot 和前台 Service。
- `src/graph_engineering/discovery/`、`contracts/`、`compiler/`：澄清、冻结与图编译。
- `src/graph_engineering/adapters/`、`executor/`：Codex 与 provider-neutral Executor 边界。
- `src/graph_engineering/verifier/`：Command、HTTP、subprocess、container 与安全策略。
- `src/graph_engineering/delivery/`、`review/`：自治协调、证据矩阵、GitHub、Review 和报告。
- `src/graph_engineering/ui/`、`mcp_server.py`：可选 UI 与 MCP 前端。

深入理解设计、代码路径、权衡、缺陷和面试问答，请直接在浏览器打开 [面试学习手册](docs/graph-engineering-interview.html)。架构决策索引见 [ADR](docs/adr/README.md)，阶段交付证据见 [Phase 文档](docs/phases/phase-6g-handoff.md)。

## 当前限制与下一步

最重要的产品缺口不是再增加协议，而是把已有组件接成真实用户路径并取得可复现证据：

1. 将 `CodexAdapter` 注入自治协调器，提供明确的真实 provider 配置、权限和恢复策略。
2. 将 `CodexDiscoveryAdapter.missing_information` 接入多轮 Discovery，并设置 `max_rounds`。
3. 让编译器按 Contract 复杂度确定性选择串行/并行模板；当前默认编译器仍输出固定串行模板。
4. 在授权环境完成 Codex Plugin、GitHub、container、OTLP、真实浏览器及 Windows/Linux/macOS 矩阵。
5. 完成发布、升级和卸载的用户级流程；当前只有本地 package qualification，没有 PyPI/安装器发布。

完整、按优先级划分的清单见 [docs/missing-items.md](docs/missing-items.md)。

## 开发与验证

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m mypy src
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
ge schema export --output schemas
```

四个 `real_codex` 测试默认跳过，需要显式环境和授权。贡献流程、分支约定和验收要求见 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [AGENTS.md](AGENTS.md)。

## 项目状态与许可证

- 当前版本：`0.8.0`
- 已合并：Phase 0–6G（`main`）
- 许可证：Apache-2.0
- 当前交接状态：[docs/status/CURRENT.md](docs/status/CURRENT.md)
