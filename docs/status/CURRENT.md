# Current Status

## 当前阶段

Phase 1：持久化 Graph Runtime 已在 `phase/1-runtime` 实现、通过本阶段验证并获 Human
认可；交付分支等待 Human 集成，未创建 PR，也未合并到 `main`。

## 已完成

- 保持 Phase 0 的公共 Schema 1.0 与 30 个提交 Schema 完全不变。
- 实现 SQLite State Store、单调迁移、外键/WAL、显式 writer 事务与只读快照。
- 状态事务同步写入 event outbox；JSONL Event Store 使用稳定 event ID 幂等 flush、fsync。
- 实现内容寻址、原子落盘、不可覆盖的最小 Artifact Store。
- 实现单机、单任务、串行 Runtime，覆盖 node/attempt/edge/run/budget 的确定性状态变化。
- 实现受限条件边、修复循环、边遍历上限、executor-call/repair budget 与终止语义。
- Run 和 Node 均执行调用次数、持续时间、修复次数预算；显式 cost charge 同时更新并执行
  Run/Node cost budget。
- 实现 checkpoint、Contract/Graph hash 校验、已完成节点恢复去重。
- 实现 Fake Executor/Fake Verifier；外部 handle 先记录 trigger intent，再 checkpoint handle，
  恢复时只查询不重触发；无法确认时停止并在报告中披露。
- 实现强类型 Control API、pause/resume/interrupt 屏障、取消、只读 snapshot 与 LiveReport。
- 屏障持久化后 Scheduler 不启动新的 node、attempt 或外部 trigger。
- 校验 `RunRelationship` 引用存在性和 checkpoint 所有权/hash；同图 checkpoint restart
  继承 node/result/route/Artifact link、重置新 Run budget，且不修改来源 Run。
- Artifact Store 已接通 SQLite metadata、role-scoped Run link、审计事件和 Result checkpoint；
  基础 FinalReport 聚合 changed files 与 Verifier evidence。
- 为 `succeeded`、`failed`、`error`、`interrupted`、`cancelled` 生成基础 FinalReport。
- 新增 26 个 Phase 1 测试和串行 Graph/Fake result fixtures；合计 62 个 pytest 测试。

## 未完成

- 不包含真实 Codex、Claude Code 或其他 Executor Adapter。
- 不包含 Context Builder、Session、独立 Reviewer/Observer Agent、Git branch/worktree 隔离。
- 不包含自然语言模型、意图识别、Human Gateway 产品逻辑或持续对话。
- 不包含动态 Verifier、Command/HTTP Pipeline、网络、secret、远程 CI。
- 不包含 daemon、GitHub PR、Plugin、MCP 产品入口、UI、并行图或 Phase 2–6 能力。

## 关键决策

- [ADR-001](../adr/001-independent-core.md)：provider-neutral 独立核心。
- [ADR-002](../adr/002-python-toolchain.md)：Python 3.12+ 与严格工程工具链。
- [ADR-003](../adr/003-protocol-versioning-and-revisions.md)：显式协议版本与追加式修订。
- [ADR-004](../adr/004-control-routing-and-terminal-semantics.md)：强类型控制、安全路由、终态语义。
- [ADR-005](../adr/005-persistent-runtime-storage.md)：SQLite 权威状态、事务 outbox、JSONL 与内容寻址 Artifact。
- [ADR-006](../adr/006-runtime-control-and-recovery.md)：状态机、控制屏障、恢复与外部副作用语义。

## 代码入口

- `src/graph_engineering/runtime/store.py`：SQLite migration、事务、只读连接和 event outbox。
- `src/graph_engineering/runtime/events.py`：幂等追加 JSONL Event Store。
- `src/graph_engineering/runtime/artifacts.py`：内容寻址 Artifact Store。
- `src/graph_engineering/runtime/engine.py`：串行 Scheduler、Control API、恢复与报告编译。
- `src/graph_engineering/runtime/fakes.py`：Fake Executor/Verifier 与 external handle 查询。
- `src/graph_engineering/runtime/types.py`：强类型只读 RunSnapshot。
- `tests/test_runtime_*.py`：Phase 1 存储、执行、控制和恢复验收测试。

## 数据、迁移与状态机

- 包版本：`0.2.0`；公共协议版本仍为 `1.0`。
- SQLite migration 版本：`2`；表包括 runs、nodes、attempts、edge_traversals、budgets、
  checkpoints、external_handles、control_intents、reports、artifact_metadata、run_artifacts、
  event_outbox。
- Run 运行态：`running → pause_requested/quiescing → paused/running`；终态使用公共
  `succeeded/failed/error/interrupted/cancelled`。
- Node/attempt 内部态：pending、ready、running、succeeded、failed、error、cancelled。
- JSONL 是 outbox 的追加式审计投影；SQLite 是权威状态。

## 验证结果

2026-08-16，CPython 3.12.10（另在 CPython 3.13.14 完成兼容性复跑）：

- `py -3.12 --version`：`Python 3.12.10`。
- `py -3.12 -m venv .local\venv312`：成功创建隔离环境（`.local/` 已忽略）。
- `.local\venv312\Scripts\python -m pip install -e ".[dev]"`：成功安装 `graph-engineering 0.2.0`。
- `.local\venv312\Scripts\python -m pytest --basetemp C:\Users\ADMIN\AppData\Local\Temp\graph-engineering-phase1-review-py312-final2`：62 passed。
- `.local\venv312\Scripts\python -m mypy src tests`：0 issues（30 source files）。
- `.local\venv312\Scripts\python -m ruff check src tests`：通过。
- `.local\venv312\Scripts\python -m ruff format --check src tests`：30 files already formatted。
- `.local\venv312\Scripts\ge schema export --output schemas`：导出 30 个 Schema。
- `git diff --exit-code -- schemas`：通过，无 Schema 漂移。
- CPython 3.13.14 独立复跑：同样 62 passed，mypy/Ruff 检查通过。

## 已知风险

- SQLite 与 JSONL 采用事务 outbox，状态/event intent 原子，但 JSONL 投影是 crash-recovery
  后最终一致，不宣称跨文件原子写。
- 无 handle 的 `triggering` 外部操作只能标记为 uncertain 并停止，无法提供 exactly-once；
  真实外部系统的查询/取消/补偿留到后续阶段。
- Phase 1 只使用同步 Fake 边界；真实进程终止、Session 恢复和 worktree 安全属于 Phase 2。
- `accepted_commit` 仅完成强类型记录；实际 Git worktree materialization 属于 Phase 2。
- FinalReport 是 Phase 1 基础版本；完整 requirement matrix、多维 Review/GitHub 证据属于 Phase 5。

## 工作区状态

- 分支：`phase/1-runtime`。
- 基线：`ece58b0`（已合并 Phase 0 的 `origin/main`）。
- Phase 1 实现提交：`5bad314`；最终交接元数据提交为本分支 `HEAD`。
- Phase 1 修改已全部提交；没有未提交修改，也没有覆盖或回退用户修改。
- Human 已认可交付；未创建 PR、未合并。

## 下一阶段第一步

由 Human 控制将 `phase/1-runtime` 集成到 `main`；集成后，才可从更新后的 `main` 创建
Phase 2 分支。Phase 2 第一步是冻结 Codex capability/
preflight 与 provider-neutral Adapter 边界，不得把 provider Session wire format写入 Core。
