# Current Status

## 当前基线

- 日期：2026-08-26
- 产品版本：`0.8.0`
- `origin/main`：`3cc79eb`，PR #7 已将 Phase 6G 和完整 Phase 6 路线合入 `main`
- 已完成实现阶段：Phase 0–6G
- 当前工作分支：`docs/mvp-user-and-interview-guide`
- 当前工作性质：合并后的产品文档与实现审计；不新增 Runtime、Schema、SQLite migration 或 provider 行为

Phase 6G 原交付证据保持在 [phase-6g-handoff.md](../phases/phase-6g-handoff.md)，不在本次文档工作中重写。

## 本次目标

1. 审查远端 `docs/interview-study-guide` 相对最新实现所列的缺失项。
2. 把 README 从阶段流水账改为用户可理解的安装、体验、能力、架构和限制入口。
3. 将面试 HTML 迁移到 Phase 6G 基线，纠正超前描述，并补充实现细节、缺陷、证据边界和未来路线。

## 审计结论

旧 docs 分支从 Phase 5 的 `eedc46d` 分叉，只增加：

- `docs/missing-items.md`
- `docs/graph-engineering-interview.html`

旧清单中的 Phase 6G 未实现、Phase 6 未合入 `main` 和文档缺少 Phase 6 基线等项已经关闭。以下三项仍是阻塞真实用户闭环的实现缺口：

1. `HumanGateway.run()` / `ge run` 只接受 `deterministic_git_fixture`，真实 `CodexAdapter` 未注入 `AutonomousDeliveryCoordinator` 产品入口。
2. `DiscoveryService` 仍固定七问；`CodexDiscoveryAdapter.missing_information` 未接主流程，没有动态 unknown、去重或 `max_rounds`。
3. 默认 `ExecutionGraphCompiler` 始终产生标准串行模板；Phase 6B 虽支持显式 parallel/subgraph/join，Compiler 尚不会根据 Contract 复杂度选择拓扑。

真实 GitHub、container、OTLP、浏览器和 Linux/macOS 仍主要缺授权环境与资格证据，性质不同于“代码不存在”。详细分级见 [missing-items.md](../missing-items.md)。

## 本次文档变更

- `README.md`
  - 明确 0.8.0 是 MVP / 工程原型，而非开箱即用的真实自治产品。
  - 删除不存在的 `ge init` 使用方式。
  - 增加 Windows 与 Linux/macOS 源码安装、五分钟体验、Service/UI 双终端流程和命令速查。
  - 明确 `ge run --deterministic-fixture` 不调用真实 Codex。
  - 用能力表、架构图、代码地图、限制和下一步替代阶段流水账。
- `docs/missing-items.md`
  - 以最新 `main` 重做 P0/P1/P2 分类。
  - 区分产品接线缺口、真实环境证据不足和产品化工作。
  - 记录已关闭旧项与推荐实施顺序。
- `docs/graph-engineering-interview.html`
  - 从远端 docs 分支移植到 Phase 6G 基线。
  - 纠正“动态 Discovery 已实现”“Compiler 已按复杂度选图”“ge run 使用真实 Codex”等错误表述。
  - 补充 Phase 6A–6G 能力、真实使用方式、三大代码缺口、结构性缺陷、未来路线和三分钟面试讲述模板。

## 验证结果

- README 的 11 个本地相对链接均存在。
- `ge --help`、`start --help`、`run --help`、`status --help`、`report --help`、`service --help`、`ui --help`、qualification/schema help 已与示例对照；期间修正了 `status/report` 不接受 `--project-root` 的文档错误。
- HTML 有 7 个 tab、7 个按 `tab0`–`tab6` 排列的 content 区、37 组 header/body；HTML、DIV、Script 开闭数量平衡，无重复 ID。
- 旧超前表述扫描已清理；所有动态 Discovery、复杂度模板和真实 provider 提法现在都明确标注“已实现边界”或“未接通”。
- `git diff --check` 最终通过。
- 相关回归：`tests/test_phase3_cli_start.py tests/test_phase6d_autonomous_delivery.py tests/test_phase6g_project_ui.py` 在宿主临时目录为 **29 passed in 9.38s**。
- 同一回归首次在 sandbox 临时目录运行时为 13 passed、14 个 setup/cleanup ACL error，最终 session cleanup 也触发 `PermissionError`；该结果仅记录环境失败，不冒充测试通过。
- 本次没有代码行为变化，因此未重复 Phase 6G 的双 Python 全量与可重复 package 构建。

## 已知环境与证据限制

- 现有工作区包含历史未跟踪 `.pytest-tmp-*` 目录，其中部分 ACL 拒绝读取；它们不是本次创建，必须保留。
- Phase 6G 的确定性测试证据为 Python 3.12/3.13 各 `262 passed / 4 skipped`；四个 skip 是 opt-in real-Codex cases。
- 真实 Codex Plugin load/autonomous run、真实 GitHub、Docker/Podman、OTLP collector、真实浏览器矩阵、Linux/macOS 仍不能标记为完整 passed。

## 下一门禁

本次只交付文档分支，不自动 push、开 PR 或合并。Human review 后可选择：

1. 接受文档并授权提交/推送/PR；或
2. 先要求修订对外定位、使用示例或面试叙事。

后续实现建议按三个独立阶段进行：真实 Codex 自治接线 → 动态 Discovery → 确定性多模板 Graph Compiler。任何阶段都不得直接在 `main` 开发，且不得把 fixture 证据升级为真实 provider claim。
