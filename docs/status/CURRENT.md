# Current Status

## 当前阶段

Phase 5 已通过 PR #6 合并到远端 main。当前位于 `phase/6-enhancements`，从精确
`origin/main=eedc46d1a607c6169cb43eca79ef56bdd137efac` 创建，仅准备 Phase 6 总路线和 Phase 6A
新对话启动 Prompt；Phase 6 功能实现尚未开始。

## 已核实 baseline 与集成顺序

- Phase 2：`53df64ceea904bdad1f39f04a5d3168f5ae40d25`。
- Phase 3：`b746b3f6b9f70838a6fe063e8a90104be7bca8a8`。
- Phase 4：`7410a66310f36799704e58cf743875d9383f5c87`。
- Phase 5 实现：`db7dd54`；交接：`4ebeb2da969e3cce9210fc3ed8dc23dbf3986662`。
- Phase 2–5 批准提交均为最新 `origin/main` ancestor；提交图确认顺序，Phase 5 由 PR #6 合并。
- Phase 6 分支创建时 HEAD、merge-base 和 `origin/main` 完全一致。
- 未 reset、rebase、cherry-pick 或改写本地 main。

## Phase 5 已完成

- ADR-024–028、Phase 5 scope、SQLite migration 6 和 package 0.6.0。
- Contract/Correctness/Security/Test Adequacy 四维结构化 Review、阻断聚合、error 隔离、fresh
  read-only Session/attempt、fix/reverify 失效和持久上限。
- append-only requirement matrix，逐 acceptance criterion 映射六类 evidence；可变或缺失证据
  fail closed 为 unverified。
- GitHub Checks 精确 repo/SHA 绑定、全部状态/结论、auth/rate-limit/network/API/identity 分类、
  bounded poll 和重启恢复。
- PR intent/handle checkpoint、幂等键、exact base/head、existing discovery、重启防重复、未知创建
  结果停止、barrier、完整 PR body renderer；默认无 merge/auto-merge。
- 所有终态十文件版本化 report bundle；`ge report` 只读；`ge accept/reject` 复用 HumanMessage、
  Intent Compiler 和 append-only acceptance record，accept 不 merge，reject 产生新 revision。
- token/secret 值不进入 prompt、事件、异常、Artifact、PR body 或 report；仅 secret reference 名称。

## 验证

- Windows / Python 3.12.10；Codex CLI 0.147.0，ChatGPT 登录。
- 默认：156 collected / 152 passed / 4 skipped，19.76s（最终完整运行）。
- Phase 0–4：135 / 132 / 3，16.13s；Phase 0–3：108 / 106 / 2，13.40s；
  Phase 0–2：91 / 90 / 1，10.75s；Phase 0–1：62 passed，8.99s。
- mypy strict、Ruff lint/format、30 Schema export/drift、有效/无效 Graph 和 Manifest CLI 通过。
- 真实 Codex Phase 5：Contract/Security/Test Adequacy 三个 fresh read-only structured Review，
  1 passed in 302.10s；首次 sandbox basetemp ACL 失败不计入证据，主机边界独立重跑退出 0。
- 隔离 GitHub local HTTP provider E2E：Checks success、PR create intent/handle、Runtime restart、
  create count=1，1 passed in 0.85s。该结果不冒充真实 GitHub E2E。

## 环境限制与未验证项

- GitHub CLI 2.97.0 已安装；`gh --version` 及 `gh pr/run/api --help` 退出 0。
  `gh auth status` 退出 1，当前未登录任何 GitHub host。
- 未获得 Human 对隔离真实 GitHub repository 的额外写授权，因此真实 GitHub PR E2E 未执行、
  明确 unverified；Graph Engineering 和其他真实 repository 均未产生 PR 副作用。
- 跨平台真实 Codex/GitHub 未验证；当前真实 Codex 证据仅 Windows。
- Runtime 仍为 foreground/recoverable，不是 daemon；Phase 6A 功能实现未开始。

## 下一步

Human 审阅 Phase 6 总路线和持久化启动 Prompt。后续新对话必须先读取
`docs/phases/phase-6.md` 与 `docs/prompts/phase-6a-start.md`，再在同一
`phase/6-enhancements` 分支实现 Phase 6A。路线初始化提交已获 Human 授权；未经后续明确批准
不得推送该分支、创建 Phase 6A 功能提交或开始 Phase 6B。
