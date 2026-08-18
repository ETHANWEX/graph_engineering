# Current Status

## 当前阶段

Phase 3：自然语言 Discovery 与 Contract 冻结已在 `phase/3-discovery-contract` stacked 分支
实现并完成确定性及真实 Codex 验证，等待 Human 审阅。未经 Human 批准，不提交、不推送、
不创建 PR、不合并，也不开始 Phase 4。

## 基线与 stacked branch

- 2026-08-17 开始前执行 `git fetch origin`。
- `origin/phase/2-codex-memory`、本地 Phase 2 与批准提交均精确为
  `53df64ceea904bdad1f39f04a5d3168f5ae40d25`。
- `origin/main=a069b36fc0169dc51400265ea72a64c7b0b2839f`，不包含 Phase 2 批准提交。
- 最终交接复核时远端仍保持上述 SHA：`origin/phase/2-codex-memory=53df64c`，Phase 2
  仍未合并；未改写 Phase 3 历史。
- Human 明确授权从 `53df64c` 创建 stacked `phase/3-discovery-contract`；未伪合并、reset、
  rebase 或改写 main。Phase 2 必须先于 Phase 3 合并。
- 启动时工作区无 tracked/untracked 用户修改；ignored `.local/` 证据保留且未纳入提交。

## 已完成

- 新增 Phase 3 范围文档和 ADR-012–018。
- `ge start` 创建或恢复项目级 Human Control Conversation；消息在解释前作为公共 Schema 1.0
  `HumanMessage` 追加持久化。
- Intent Compiler 将 query/status/report 和 pause/resume/interrupt/revise/restart/accept/reject
  编译为现有 query/state_change 判别联合。多动作、低置信度、缺少目标或高风险未确认请求
  fail closed。
- ProjectScanner 基于排序的 Git/文件 inventory，受文件数和总字节限制并记录 truncation。
- Discovery 保存 unknown、逐轮答案、测试建议、draft 与 pending confirmation；重启后恢复。
- `ge start` 强制询问测试/验收方式，并依次确认 acceptance、上下游、conventions、权限、
  delivery 和预算；完成后展示 canonical draft 与风险/权限摘要。
- ContractRepository 只允许显式 Human confirmation 后 freeze；acceptance lock 与 frozen
  revision 原子追加，重复确认幂等，revision 不可覆盖。
- ContractDelta 引用来源 revision 和确认消息，创建 N+1 revision；RunPlanner 创建新 prepared
  Run，parent/supersedes 指向来源且不修改来源 Run。
- ExecutionGraphCompiler 只接受 frozen Contract，按排序 verifier 生成稳定串行 Graph；路由只
  使用现有枚举化 `RouteCondition`，不执行 Python、Shell 或模型文本。
- Phase2Observer 桥接 fresh read-only Observer；NaturalLanguageControlService 比较执行指纹。
- pause/interrupt 仍由 GraphRuntime 在事务中先持久化 barrier；PersistedBarrierGuard 可直接
  保护 Command Verifier 和 Git worktree 写入，DurableExecutorRuntime 保留原 barrier 检查。
- CodexDiscoveryAdapter 使用 read-only sandbox、JSONL、strict output Schema 和 raw Artifact，
  不启动实现，不使用 dangerous bypass。

## SQLite migration 4

新增 `conversations`、`human_messages`、`intent_compilations`、`pending_confirmations`、
`discovery_sessions`、`contract_drafts`、`contract_revisions`、`acceptance_locks`、
`contract_deltas` 和 `planned_runs`。大日志仍进入 Artifact Store；SQLite 只保存状态、结构化
JSON、hash 和 Artifact 引用。

为不破坏 Phase 2 测试和调用方，`schema_version == 2` 与 `latest_migration_version == 3` 保持
兼容；实际数据库 head 由 `storage_migration_version == 4` 报告。

## 协议与兼容性

- 包版本：`0.4.0`。
- 30 个公共 JSON Schema 仍为 Schema 1.0，导出无漂移。
- 复用公共 `HumanMessage`、`ControlIntent`、`TaskContract`、`ContractRef`、`ExecutionGraph`、
  `RunRelationship` 和 `RestartFrom`，没有 provider wire format 进入 Core。
- Contract/Discovery lifecycle、acceptance lock 和 prepared Run 是内部持久化模型；没有伪造
  新公共协议版本。

## 代码入口

- `conversation/`：Conversation repository 与 fail-closed Intent Compiler。
- `discovery/`：ProjectScanner、unknown/draft 状态机与恢复。
- `contracts/`：draft/freeze/lock/delta/revision 与 prepared Run lineage。
- `compiler/`：frozen Contract → deterministic Execution Graph。
- `control/`：persist-first NaturalLanguageControlService 与 Phase 2 Observer bridge。
- `adapters/discovery.py`：Codex structured read-only Discovery 边界。
- `runtime/store.py`、`runtime/barriers.py`：migration 4 与统一 side-effect guard。
- `cli.py`：`ge start` 持续对话、确认界面和不可变 control artifacts。

## 本机运行时事实与官方文档

- Windows，CPython 3.12.10，Codex CLI 0.147.0。
- `codex login status`：`Logged in using ChatGPT`。
- 本机 help 支持 exec JSONL、output schema、last message、resume/review、sandbox 与 approval
  never；dangerous bypass 从未使用。
- OpenAI Docs：`codex exec --json` 是 JSONL 事件流，`--output-schema` 约束最终响应，默认
  非交互 sandbox 为只读：<https://learn.chatgpt.com/docs/non-interactive-mode>。

## 验证结果

最终确定性复跑结果：

- 108 项默认 suite：106 passed、2 real-Codex skipped。
- Phase 0–2 原有 91 项：90 passed、1 skipped；Phase 0–1 原有 62 项保持通过。
- Phase 3：17 项（16 个确定性测试 + 1 个显式 real-Codex 测试）。
- mypy strict：0 issues；Ruff lint/format：通过。
- 30 个公共 Schema 导出退出 0，`git diff --exit-code -- schemas` 退出 0。
- 合法 Graph CLI 退出 0；非法 Graph CLI 退出 2，并报告 `nodes[0].node_type` 与
  `edges[0].condition` 字段路径。
- 真实 Phase 3 Codex Discovery：1 passed in 25.81s；read-only，识别缺失 test/verification，
  fixture Git 状态不变。
- 真实 Phase 2 回归：1 passed in 289.32s；implement/review/fix/verify/observer/recovery/interrupt
  全路径保持通过。
- 首次 sandbox 内真实 Discovery 因宿主无权初始化 `C:\Users\ADMIN\.codex` app-server 而退出
  1；stderr 已保存为 Artifact。相同测试在获批的宿主边界外通过，未用 Fake 替代。

## 已知限制

- `ge start` 当前是前台 CLI Conversation，不是后台 daemon；关闭后状态可恢复。
- 确认 Contract 后创建 frozen inputs 与 `prepared` Run，不自动启动 Codex Implementer。
- accept/reject/revise/restart 会先形成强类型 intent 和 confirmation；具体执行仍受来源 Run
  状态、Contract delta 与 restart root 校验，不能通过自由文本绕过。
- 动态/HTTP Verifier、远程 CI、GitHub PR、auto-merge、Plugin/MCP/UI、并行图和 Phase 4–6
  能力不在本阶段。
- Windows pytest workspace basetemp 仍可能产生不可读 ACL，因此真实测试使用 ignored、预建、
  独立 fixture 根目录。

## 工作区状态

- 分支：`phase/3-discovery-contract`；stacked base：`53df64c`。
- Phase 3 修改保持未提交、未推送，等待 Human review。
- 没有 PR、merge、rebase、reset 或 main 修改。

## 下一阶段第一步

Human 先审阅 Phase 3 的实现、测试、真实 Codex 证据和 stacked 关系。只有明确批准后才提交并
推送 Phase 3 分支；必须先集成 Phase 2，再集成 Phase 3。Phase 3 集成 main 之前不得开始
Phase 4。
