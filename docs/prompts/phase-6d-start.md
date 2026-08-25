# Phase 6D New-Conversation Startup Prompt

Use this prompt only after the Human-approved Phase 6C delivery commit has been created and the same
commit is the current local and remote `phase/6-enhancements` HEAD. The delivery SHA must be obtained
from Git after creation; it is intentionally not embedded in content that determines that SHA.

```text
工作区：

E:\project\graph_engineering

请开始实现 Graph Engineering Phase 6D：Autonomous Delivery Closure。

必须继续使用 `phase/6-enhancements`，不得另建分支，也不得在 main 开发。开始前完整阅读并遵循：

- AGENTS.md
- DESIGN.md
- README.md
- docs/status/CURRENT.md
- docs/phases/phase-6.md
- docs/phases/phase-6c.md
- docs/phases/phase-6c-handoff.md
- docs/phases/phase-6a.md / phase-6a-handoff.md
- docs/phases/phase-6b.md / phase-6b-handoff.md
- docs/phases/phase-6r.md / phase-6r-handoff.md
- ADR-001 至 Phase 6C 最新 ADR
- 相关 Discovery、Contract freeze、Graph compiler、Runtime、Verifier、Review、GitHub、delivery
  report、Human decision、Service、IPC、MCP、Plugin、parallel 与 container 实现/测试

先执行 `git fetch origin`，并核实/报告：

- 当前 branch、HEAD、`origin/phase/6-enhancements` 和 `origin/main`
- local/remote ahead-behind
- tracked、untracked 和 ignored 状态
- 当前 HEAD 是 Human 批准的 Phase 6C delivery，是
  `b7da3c4c7712db0f8fb01f14cd2d141008c5186a` 的单一 Phase 6C delivery child，且
  本地/远端 SHA 精确一致
- Phase 6C handoff、CURRENT、README 和实际 Git 事实一致

如果 branch、SHA、handoff、远端或工作区存在任何未归属不一致，立即停止。不得擅自
reset、rebase、cherry-pick、amend、force-push、另建替代分支、修改 main 或删除历史证据。

修改前运行 Python 3.13 与可用的 Python 3.12 全量 baseline，mypy strict、Ruff lint/format、
Schema export/drift、migration 1–9 repeatability、历史/parallel Graph CLI 和 Verifier CLI。正常 baseline
应为 215 collected / 211 passed / 4 skipped；四个 skip 只能是既有 opt-in 真实 Codex 实例。
受管 sandbox 的 tmp_path ACL 失败必须与宿主产品证据分开记录，不得删除历史 pytest 目录。

`docs/phases/phase-6.md` 是 Phase 6 顺序、单分支策略和不变量的权威来源。baseline 通过后：

1. 将 README 和 CURRENT 活动阶段更新为 Phase 6D。
2. 创建 `docs/phases/phase-6d.md`。
3. 从最新 ADR 编号继续记录决策。
4. 先写失败测试，再实现功能。

Phase 6D 仅闭合从已确认 Contract 到显式启动 durable Run 的产品路径，至少包含：

- confirmed Discovery/acceptance lock -> prepared Run -> 显式 run 动作；确认绝不静默启动副作用
- 将 Implementer、Verifier/repair、fresh multidimensional Review、delivery provider、PR/report
  和 Human accept/reject/revise 组成可持久、可恢复的自治闭环
- 提供强类型 CLI 与 MCP/Plugin 路由：run、status、pause、resume、interrupt、cancel、
  report 和 terminal Human decisions
- 所有自然语言继续先持久化 `HumanMessage`，再经 Intent Compiler、confirmation policy 和
  typed Runtime control；不得增加 frontend 直接写 Runtime/SQLite/worktree/provider 的旁路
- restart/pause/resume/interrupt/revise 保持 Run lineage、durable barrier、checkpoint、external
  idempotency 和 parallel/container 恢复语义
- 明确分流 verifier failed、container/provider infrastructure error、Review blocked/changes requested、
  delivery/GitHub error、cancellation 和 residual effect
- 每个 terminal outcome 均生成版本化十文件 delivery bundle 和 Final Report；Human accept 永不 merge
- 增加真实 Git fixture 的产品级 CLI/MCP 闭环测试，同时清晰区分 deterministic fixture
  与尚未授权/不可用的真实 Codex、GitHub、Plugin 或 container E2E

必须保持：Phase 0–6C 串行/并行 Runtime、SQLite migration 1–9、Service、IPC 1.0、
MCP、Plugin、历史 Graph SHA、只读 query/status/report、durable barrier、冻结 Contract/Verifier/
evidence、Secret redaction、无任意 Python/shell/expression source、默认不自动 merge。

公共协议、SQLite 或 Schema 变化必须同时包含 ADR、compatibility analysis、migration、fixture、
JSON Schema export/drift 和历史数据读取测试。

不得实现 Phase 6E+、OpenTelemetry、UI、Claude Code Adapter、distributed worker、系统启动服务、
Plugin 安装/发布、自动 merge 或 branch-protection bypass。不得为通过测试弱化历史验收、
安全、Secret、network、barrier 或错误分类。

完成后运行双 Python 全量 pytest、Phase 6D focused suite、mypy、Ruff、Schema drift、migration、
Graph/Verifier CLI 和产品级 deterministic E2E；记录命令、退出码、数量、耗时、版本、真实/
fixture 证据边界、未验证项与残留副作用。

创建 `docs/phases/phase-6d-handoff.md`并更新 README/CURRENT。保持全部 Phase 6D 结果未提交，
先报告并等待 Human Review。未经再次明确批准，不得创建 delivery commit、push、PR、
修改/合并 main、安装/发布 Plugin、执行未授权外部写入或开始 Phase 6E。
```
