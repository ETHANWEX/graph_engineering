# Phase 6B New-Conversation Startup Prompt

Copy the text below only after Human has approved and recorded the Phase 6A delivery commit.

```text
工作区：

E:\project\graph_engineering

请开始实现 Graph Engineering Phase 6B：Parallel Graphs。

必须继续使用 `phase/6-enhancements`，不得另建分支，也不得在 main 开发。开始前先完整阅读
AGENTS.md、DESIGN.md、README.md、docs/status/CURRENT.md、docs/phases/phase-6.md、
docs/phases/phase-6a.md、docs/phases/phase-6a-handoff.md、全部 ADR、全部现有测试/Schema/fixtures、
Runtime/Graph/Compiler/Executor/Verifier/Barrier/Budget/Checkpoint/Event/External Handle 代码。

先执行 `git fetch origin`，核实并报告：当前分支、HEAD、origin/main、远端 Phase 6 分支、tracked/
untracked/ignored、Phase 6A delivery SHA 与 handoff 是否一致、Phase 6A delivery 是否是当前 HEAD 的
ancestor、是否存在未归属修改，以及 Phase 0–6A 全量 baseline。若 Phase 6A 尚未形成 Human 批准的
delivery commit、工作树不干净或事实不一致，立即停止，不得开始 6B。

`docs/phases/phase-6.md` 是范围、顺序、单分支提交策略和不变量的权威定义。先更新 README/CURRENT
活动阶段，创建 `docs/phases/phase-6b.md`，再从最新 ADR 编号继续写 ADR 和失败测试。

Phase 6B 仅实现：

- parallel nodes、显式 subgraph 和 deterministic join；
- bounded concurrency、共享 budget 原子协调与确定性 result aggregation；
- 并行 branch checkpoint/restart recovery，已完成 branch 不重复执行；
- active/pending branch 的 pause/interrupt/cancel durable barrier；
- failed/blocked/error branch 不得被成功 branch 抵消；
- 保持现有 serial Graph 行为与 Phase 0–6A 数据/API/Runtime Service/IPC/MCP/Plugin 兼容。

不得实现 Phase 6C+、container Verifier、OpenTelemetry、UI、Claude Code Adapter、distributed
worker、系统服务、自动合并或绕过 branch protection。不得弱化 Phase 0–6A 测试与不变量。

优先验收 race-free budget、join 与完成顺序无关、restart 不重复副作用、barrier 覆盖 active/pending
branch、external handle 幂等恢复、失败语义聚合、serial compatibility、migration repeatability、
Windows deterministic stress tests、全量 pytest、mypy strict、Ruff 和 Schema drift。

完成后创建 `docs/phases/phase-6b-handoff.md` 并更新 README/CURRENT，保持未提交结果，先报告并等待
Human Review。未经再次明确批准，不得创建 Phase 6B delivery commit、推送、创建 PR、修改/合并
main、安装/发布 Plugin，或开始 Phase 6C。
```
