# Phase 0 Handoff

## 交付摘要

- 设计版本：`DESIGN.md` v0.2。
- 阶段：Phase 0（仓库与协议基础），验收项全部完成。
- 分支：`phase/0-foundation`；没有自动合并到 `main`。
- 基线提交：`c978ceb`。
- Phase 0 实现提交：在最终验证后创建并记录于本文末尾的工作区状态。

Phase 0 仅交付协议、Schema、fixtures、静态 Graph 校验、工程工具和文档。没有 Runtime、
节点执行、模型调用、Human Gateway 运行逻辑、SQLite、daemon、HTTP、GitHub 或插件入口。

## ADR

1. `docs/adr/001-independent-core.md`
2. `docs/adr/002-python-toolchain.md`
3. `docs/adr/003-protocol-versioning-and-revisions.md`
4. `docs/adr/004-control-routing-and-terminal-semantics.md`

## 协议与 Schema

- 30 个公共模型 Schema 位于 `schemas/*.schema.json`，版本均为 `1.0`。
- `TaskContract` 修订必须追加并引用较低旧 revision。
- `ControlIntent` 是 query/state_change 判别联合；自然语言输入只由 `HumanMessage` 承载。
- `RouteCondition` 只允许枚举字段与比较操作，不接收可执行表达式。
- Result/Report 区分任务或验收 `failed` 与执行/基础设施 `error`。
- `RunRelationship` 同时支持 parent 和 supersedes；`RestartFrom` 支持 clean base、accepted
  commit 和 checkpoint。
- `FinalReport` 支持 succeeded、failed、error、interrupted、cancelled、rejected，以及
  unverified items 和不可撤销 external effects。

## Fixtures 与测试

合法和非法 fixture 分别位于 `tests/fixtures/valid/`、`tests/fixtures/invalid/`，覆盖：

- Contract
- Graph
- Executor Result
- Control Intent
- Final Report

Phase 0 共 36 个 pytest 测试，另有 mypy strict、Ruff 和 JSON Schema 合法性/漂移测试。

## 验证命令与结果

验证日期：2026-08-16。本机解释器为 CPython 3.13.14；项目要求 Python 3.12+。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\ge schema export --output schemas
.venv\Scripts\python -m pytest
.venv\Scripts\python -m mypy src tests
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m ruff format --check src tests
.venv\Scripts\ge graph validate tests/fixtures/valid/graph.yaml
.venv\Scripts\ge graph validate tests/fixtures/invalid/graph.yaml
```

结果：安装成功；30 个 Schema 导出且无漂移；36 tests passed；mypy 0 issues；Ruff lint
和 format check 通过；合法 Graph 返回 0；非法 Graph 返回 2，并提供字段级错误。

## README 一致性

README 的“已实现能力”只列出 Phase 0 的 `ge graph validate` 和 `ge schema export`。
`ge init`、`ge start`、Runtime、Executor、Human control behavior 等均明确位于计划内容或未实现
列表，没有作为当前能力呈现。

## 下一阶段禁止破坏

- Core 不得加入 provider-specific Session wire format。
- 必须保持 `schema_version` 和已提交 Schema 的显式兼容策略。
- 旧 Contract、Run、证据和报告不可被修订覆盖。
- Runtime 只能接受强类型 ControlIntent，且 query 不得变更执行状态。
- `failed` 不得与基础设施 `error` 合并。
- Graph 路由不得执行 Python、Shell 或任意表达式。
- 所有终态报告必须保留未验证事项和不可撤销外部副作用。

## 风险与下一步

- 当前机器未安装 CPython 3.12，因此本地执行证据来自 3.13.14；打包下限和类型目标均为
  3.12。
- 跨字段模型校验是权威校验的一部分，不能假设通用 JSON Schema validator 会执行所有
  Pydantic `model_validator`。
- Human 审阅并批准 Phase 0 后才能合并。Phase 1 的第一步是新建阶段分支，先用 ADR 和
  测试冻结 SQLite/JSONL、状态机、执行屏障与 Fake Executor/Verifier 事务语义。

## 下一对话启动提示词

```text
请在 Human 已审阅并批准 Phase 0 后继续 graph_engineering。先阅读 AGENTS.md、DESIGN.md、
README.md、docs/status/CURRENT.md、docs/phases/phase-0-handoff.md 和其中引用的 ADR；检查
分支、git status、最近提交和全部测试。不要自动合并 phase/0-foundation。若 Human 已明确
批准并完成集成，再从更新后的 main 创建 Phase 1 独立分支，只实施 Phase 1。
```

## 工作区状态

- 当前分支：`phase/0-foundation`。
- 最近基线提交：`c978ceb`。
- 最终 Phase 0 提交：待最终验证后填写。
- 交接文件写入时的未提交修改：Phase 0 实现、用户原有设计对齐文档及本交接更新；将在
  阶段提交中一并记录。
