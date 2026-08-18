# Phase 6C New-Conversation Startup Prompt

Copy the text below only after Human Review approves Phase 6B and records its delivery commit.

```text
工作区：

E:\project\graph_engineering

请开始实现 Graph Engineering Phase 6C：Container Verifiers。

必须继续使用 `phase/6-enhancements`，不得另建分支，也不得在 main 开发。开始前完整阅读并遵循
AGENTS.md、DESIGN.md、README.md、docs/status/CURRENT.md、docs/phases/phase-6.md、
docs/phases/phase-6b.md、docs/phases/phase-6b-handoff.md、全部 ADR、全部测试/Schema/fixtures，
以及 Runtime、Verifier、secret、subprocess、HTTP、checkpoint、barrier、budget、Artifact、report 和
Phase 6B parallel 实现。

先执行 `git fetch origin`，核实并报告当前分支、HEAD、origin/main、远端 Phase 6 分支、tracked/
untracked/ignored、Phase 6B delivery SHA 与 handoff 是否一致、delivery 是否为当前 HEAD，以及
Phase 0–6B 全量 baseline。若分支、HEAD、handoff、工作树或远端事实不一致，立即停止；不得
reset、rebase、cherry-pick、另建分支或改写历史。

`docs/phases/phase-6.md` 是范围、顺序、单分支提交策略和不变量的权威定义。先更新
README/CURRENT 活动阶段并创建 `docs/phases/phase-6c.md`，再从最新 ADR 编号继续编写 ADR 和失败
测试。

Phase 6C 仅实现 container Verifier provider：immutable image identity、provenance/allowlist、
CPU/memory/process/time/output limits、mount policy、default-deny networking、secret references、
checkpoint、cancellation、cleanup 和 residual-effect reporting。必须区分 verifier failed 与
container infrastructure error，拒绝 mount escape 和 frozen image/config drift，确保 secret 不进入
命令、日志、事件、Artifact 或报告，并保持 Phase 0–6B serial/parallel Runtime、SQLite、Service、
IPC、MCP 和 Plugin 兼容。

不得实现 Phase 6D+、OpenTelemetry、UI、Claude Code Adapter、distributed worker、系统服务、
自动合并或绕过 branch protection。不得安装/发布 Plugin，不得弱化现有测试或安全不变量。

完成后创建 `docs/phases/phase-6c-handoff.md` 并更新 README/CURRENT。保持未提交结果，先报告并
等待 Human Review；未经再次明确批准，不得创建 delivery commit、推送、创建 PR、修改/合并
main、安装/发布 Plugin 或开始 Phase 6D。
```
