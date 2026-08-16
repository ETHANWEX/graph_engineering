# Phase 0：仓库与协议基础

## 目标

建立 Graph Engineering 的可测试工程骨架和语言无关的核心协议，使后续 Runtime、Executor、Verifier 和 Human Control Plane 可以在稳定、版本化的契约上实现。

Phase 0 是第一个实施阶段，但不是可运行自治系统。它只交付模型、Schema、静态验证、CLI 骨架、ADR 和测试。

## 范围

### 工程基础

- Python 3.12 项目结构和 `pyproject.toml`。
- `src` layout。
- pytest、类型检查和格式化/静态检查配置。
- Typer CLI 入口。
- 贡献指南和开发命令。

### 核心协议模型

- Task Contract。
- Execution Graph、Node、Edge 和受限路由条件。
- Executor Result、Verifier Result 和统一错误分类。
- Artifact、Budget 和版本字段。
- HumanMessage、ControlIntent、ControlActionResult。
- RunRelationship 和 `restart_from`。
- LiveReport、FinalReport 和终态原因。

### Schema 与静态验证

- 所有公共模型导出 JSON Schema。
- 为合法和非法输入建立 fixtures。
- 提供 `ge graph validate <file>`。
- 错误输出包含字段路径和可理解原因。
- Schema 输出稳定且可由测试检测意外变化。

### 文档与决策

- 建立 `docs/adr/` 并记录 Phase 0 实际接受的核心决策。
- 更新 README，使“已实现能力”和示例命令与真实代码一致。
- 更新 `docs/status/CURRENT.md` 和 Phase 0 交接记录。

## 不在范围内

- 不调用真实 Codex 或其他 Coding Executor。
- 不实现自然语言意图识别或 Human Gateway。
- 不实现 SQLite Runtime、Scheduler、Event Store 或 Artifact Store。
- 不执行 Graph 节点。
- 不实现 pause、interrupt、resume 或报告编译行为；只定义相关协议。
- 不实现动态 Verifier、HTTP Pipeline、GitHub PR、Plugin 或 UI。

## 建议目录

最终命名可以在实现中小幅调整，但职责必须保持清晰：

```text
src/graph_engineering/
├── __init__.py
├── cli.py
├── models/
│   ├── common.py
│   ├── contract.py
│   ├── graph.py
│   ├── results.py
│   ├── control.py
│   └── reports.py
└── schema.py

tests/
├── fixtures/
│   ├── valid/
│   └── invalid/
├── test_contract_models.py
├── test_graph_models.py
├── test_control_models.py
├── test_report_models.py
├── test_schema_export.py
└── test_cli_graph_validate.py
```

## 必须保持的协议不变量

1. 所有公共协议都有显式版本。
2. 核心协议不出现 Codex、Claude Code 等 Executor 专属 Session 格式。
3. Contract 和冻结证据可被 hash，字段序列化必须确定。
4. 自然语言只作为 `HumanMessage` 输入；Runtime 只接受枚举化、强类型的 `ControlIntent`。
5. Control Intent 必须能够关联原始 Human 消息、actor、目标 Run、原因、确认要求和动作结果。
6. 查询意图与修改状态的意图在类型上可区分。
7. Contract 修订不能覆盖旧版本，RunRelationship 可以表达 parent/supersedes。
8. FinalReport 可以表达所有终态、未验证事项和不可撤销外部副作用。
9. `failed`（任务/验收失败）与 `error`（执行器/基础设施异常）必须可区分。
10. 路由条件不能执行任意 Python 或 Shell。

## Phase 0 验收标准

- [x] Python 包可以在干净环境安装。
- [x] 所有公共模型都能导出合法 JSON Schema。
- [x] Contract、Graph、Result、Control 和 Report schema 都有合法与非法 fixtures。
- [x] `ge graph validate` 对合法 Graph 返回成功，对非法 Graph 返回非零退出码和字段级错误。
- [x] Schema 能表达非阻塞查询、暂停、中断、Contract 修订、Run 继承和所有终态报告。
- [x] 单元测试、类型检查和项目规定的静态检查全部通过。
- [x] Phase 0 ADR 已创建且与实现一致。
- [x] README 只描述已经实现的命令，并继续说明整体目标架构。
- [x] `docs/status/CURRENT.md` 和 Phase 0 交接包已更新。

## 验证证据

Phase 0 结束时至少记录：

- 安装命令和结果。
- 单元测试命令、测试数量和结果。
- 类型检查、格式化和静态检查命令及结果。
- Schema 导出命令和生成文件列表。
- 合法/非法 Graph CLI 验证示例。
- `git status`、当前分支和最终 commit。

## 禁止提前实现

- 不为了演示而添加不可恢复的临时 Runtime。
- 不接入真实 Codex。
- 不创建后台 daemon。
- 不实现自然语言模型调用。
- 不实现 Phase 1 的 SQLite 状态机或 Scheduler。
- 不把 Phase 2–6 的具体产品逻辑塞入 Phase 0 模型层。

如果协议字段在实现中暴露歧义，优先通过 fixture、测试和 ADR 收敛，而不是扩大到后续阶段。

## 完成记录

Phase 0 于 2026-08-16 在 `phase/0-foundation` 分支完成。实际验证命令、结果、Schema
列表、ADR、工作区状态和下一阶段约束见 `docs/phases/phase-0-handoff.md`；权威当前状态见
`docs/status/CURRENT.md`。该分支未自动合并到 `main`，需 Human 审阅和批准。
