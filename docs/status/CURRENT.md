# Current Status

## 当前阶段

Phase 0：仓库与协议基础已完成并通过本阶段验证，等待 Human 审阅；未合并到 `main`。

## 已完成

- 建立 Python 3.12+、`src` layout 和 `pyproject.toml` 可安装包。
- 建立 Typer CLI 骨架与 `ge graph validate`、`ge schema export`。
- 实现平台无关的 Task Contract、Execution Graph/Node/Edge、Executor/Verifier Result、
  Artifact、Budget、Error、HumanMessage、ControlIntent、ControlActionResult、RunRelationship、
  RestartFrom、LiveReport 和 FinalReport。
- 所有公共协议使用显式 `schema_version: "1.0"`；模型拒绝未知字段并支持确定性
  canonical JSON/SHA-256。
- Contract revision 以旧版本引用追加，查询/状态变更 ControlIntent 在类型上分离。
- 路由条件使用受限字段、操作符和值，不接受 Python 或 Shell 表达式。
- `failed` 与 `error` 的字段要求和终态原因已通过模型校验区分。
- 导出并提交 30 个 JSON Schema；Contract、Graph、Result、Control、Report 均有合法与
  非法 fixtures。
- 建立 pytest、mypy strict、Ruff lint/format 和 Schema 漂移检查。
- README 已明确区分 Phase 0 已实现能力与 Phase 1–6 计划能力。

## 未完成

- 未实现 SQLite/JSONL Runtime、Scheduler、Event/Artifact Store 或 Graph 节点执行。
- 未实现真实 Codex/其他 Executor 调用、自然语言模型调用或 Human Gateway 运行逻辑。
- 未实现 pause/interrupt/resume 行为、动态 Verifier、HTTP Pipeline、daemon、GitHub PR、
  Plugin、MCP 产品入口或 UI。
- 不得在 Phase 0 分支提前开始 Phase 1–6。

## 关键决策

- [ADR-001](../adr/001-independent-core.md)：核心是独立、provider-neutral 控制层。
- [ADR-002](../adr/002-python-toolchain.md)：Python 3.12+、Pydantic v2、Typer、pytest、
  mypy strict 和 Ruff。
- [ADR-003](../adr/003-protocol-versioning-and-revisions.md)：公共协议显式版本、确定性
  序列化、Contract append-only revision 和 Run 继承关系。
- [ADR-004](../adr/004-control-routing-and-terminal-semantics.md)：强类型 ControlIntent、
  受限路由、failed/error 与所有终态报告语义。

SQLite 状态、JSONL 事件及其事务边界仍是 Phase 1 的决策，不在 Phase 0 中实现或冻结
具体存储结构。

## 代码入口

- `src/graph_engineering/models/`：六组公共 Pydantic v2 协议。
- `src/graph_engineering/schema.py`：公共模型注册表和稳定 Schema 导出。
- `src/graph_engineering/cli.py`：Typer CLI 与静态 Graph 验证。
- `schemas/`：30 个提交的 JSON Schema 快照。
- `tests/fixtures/{valid,invalid}/`：五类合法/非法协议样例。
- `tests/`：36 个 Phase 0 测试。

## 数据与协议

- 当前公共 Schema 版本：`1.0`。
- 包版本：`0.1.0`。
- Schema 文件：`schemas/*.schema.json`（30 个）。
- Graph 输入支持 JSON/YAML；Phase 0 只验证，不执行。
- Core 中不存在 Codex 或 Claude Code 专属 Session 字段。

## 验证结果

2026-08-16 使用 CPython 3.13.14 验证（项目声明并由打包元数据约束为 Python 3.12+）：

- `.venv\\Scripts\\python -m pip install -e ".[dev]"`：成功。
- `.venv\\Scripts\\ge schema export --output schemas`：成功，导出 30 个 Schema。
- `.venv\\Scripts\\python -m pytest`：36 passed。
- `.venv\\Scripts\\python -m mypy src tests`：成功，0 issues。
- `.venv\\Scripts\\python -m ruff check src tests`：成功。
- `.venv\\Scripts\\python -m ruff format --check src tests`：成功。
- 合法 Graph：退出码 0；非法 Graph：退出码 2，报告 `nodes[0].node_type` 和
  `edges[0].condition`。

最终复跑和独立干净环境安装证据记录在 `docs/phases/phase-0-handoff.md`。

## 已知问题

- 当前机器只有 Python 3.13.14；`requires-python = ">=3.12"` 与 mypy 的 Python 3.12
  目标已配置，但尚未在本机用 CPython 3.12 二进制执行测试。
- Pydantic `model_validator` 施加的跨字段不变量不能全部仅由 JSON Schema validator
  复现；权威验证入口是 Pydantic 模型/`ge graph validate`。
- 首个正式发布的平台支持矩阵和容器隔离仍未冻结。

## 工作区状态

- 分支：`phase/0-foundation`。
- 基线提交：`c978ceb`（`main`/`origin/main`）。
- Phase 0 实现提交：`c1a56b2`；该分支不得自动合并。
- 开始时用户已有的 `DESIGN.md`、`README.md` 和新增 Phase 文档修改均已保留并纳入
  Phase 0 对齐，没有回退或重新生成。

## 下一阶段第一步

Human 审阅并明确批准 Phase 0 后，才可合并本分支。Phase 1 应从更新后的 `main` 创建独立
分支，先为 SQLite State Store、JSONL Event Store、事务屏障和 Fake Executor/Verifier
编写 ADR 与状态机测试；不得复用或放宽 Phase 0 的公共协议不变量。
