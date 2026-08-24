# Recovery Gate R0 New-Conversation Startup Prompt

```text
工作区：

E:\project\graph_engineering

请执行 Graph Engineering Recovery Gate R0：Delivery and Baseline Reconciliation。

必须继续使用 `phase/6-enhancements`，不得另建分支或在 main 开发。完整阅读并遵循 AGENTS.md、
DESIGN.md、README.md、docs/status/CURRENT.md、docs/phases/phase-6.md、
docs/phases/phase-6r.md、docs/phases/phase-6b.md、docs/phases/phase-6b-handoff.md 和相关 ADR、测试、
Schema、fixtures。

开始时只读核实当前 branch/HEAD、origin/main、origin/phase/6-enhancements、tracked/untracked/
ignored、Python/pytest/Ruff/mypy 版本和 Phase 6B handoff。Human 已于 2026-08-24 明确批准
`f9ee0b3` 为 Phase 6B delivery；记录该决定但不得 amend、reset、rebase 或改写历史。

仅完成 R0：修复 README/CURRENT/handoff/prompt 事实漂移；恢复新 checkout 可复现的默认 pytest、
Ruff、mypy、schema、CLI 和 migration 验证路径；核对 Python 3.12 目标与 Python 3.13 支持决定；将
DESIGN.md 未关闭项目逐项映射到证据或后续阶段。不得删除历史 ACL/pytest 目录，除非 Human 对
精确目标另行授权。

完成后创建 docs/phases/phase-6r-handoff.md，更新 README/CURRENT，并保持未提交结果等待 Human
Review。未经再次明确批准，不得 commit、push、创建 PR、修改/合并 main、安装/发布 Plugin、执行
真实 GitHub 写入或开始 Phase 6C。
```
