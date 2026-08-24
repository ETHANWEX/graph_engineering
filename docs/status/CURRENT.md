# Current Status

## 当前阶段

Recovery Gate R0 已于 2026-08-24 通过 Human Review，并获授权在 `phase/6-enhancements` 创建
单一本地 delivery commit。该 delivery 的身份是包含本 CURRENT 与 R0 handoff、且 parent 为
`f9ee0b3` 的提交；SHA 在创建后通过 Git 核实，不尝试嵌入决定自身 SHA 的内容。Phase 6C 尚未
开始；push 和 6C 启动仍需分别明确授权。

Human 已于 2026-08-24 明确批准
`f9ee0b330a5a22a99d48cb787356445d044fb2ae` 为 Phase 6B delivery。该 SHA 同时是当前本地 HEAD
和 `origin/phase/6-enhancements`，R0 不 amend、reset、rebase 或改写该历史。

## R0 已完成

- README、CURRENT、Phase 6B handoff、Phase 6 路线和启动 prompts 已与实际 Git 状态及 Human
  授权对齐；6B handoff 保留 pre-delivery snapshot，并追加可审计事实说明。
- `pyproject.toml` 将支持窗口明确为 Python `>=3.12,<3.14`，声明 3.12/3.13 classifiers；mypy 和
  Ruff 继续以 Python 3.12 作为最低语义目标。
- pytest 不再强制复用仓库内 `.pytest-tmp`；正常宿主默认命令使用平台管理的临时根。Ruff
  root discovery 排除 `.local` 与历史 `.pytest-*` ACL evidence。
- 新增三个 R0 tooling contract tests，锁定 Python 窗口、非仓库全局 basetemp 和 Ruff 排除规则。
- DESIGN 历史 locks 已核账：协议版本/迁移、Codex Session/Memory 原型、动态 Verifier 和容器进入
  正式版本的决策已引用既有 ADR/阶段证据关闭；跨平台正式支持矩阵明确转入 Phase 6E。
- 纠正 Phase 6B handoff 中非法 Graph CLI 退出码：实现和锁定测试的契约是 exit 2，不是误记的
  exit 1。

## 最终验证

- Python 3.13.14，默认宿主 pytest：190 collected / 186 passed / 4 skipped，34.58s，exit 0。
- Python 3.12.10，同一最终快照默认宿主 pytest：190 collected / 186 passed / 4 skipped，33.95s，
  exit 0。
- R0 + Schema/CLI + migration + Phase 6A Service/MCP + Phase 6B Parallel focused：45 passed in
  12.98s，exit 0。
- mypy strict：124 source files，无问题；Ruff root lint 全部通过；Ruff format：124 files clean。
- Schema export：36 files，committed drift 为零；migration 1–8 repeatability 由 focused/full suite
  覆盖。
- 历史和 Phase 6B valid Graph CLI exit 0；Phase 6B invalid Graph exit 2 并包含字段路径；Verifier
  manifest validate exit 0。

受管沙箱会主动使 pytest 临时目录不可读，因此沙箱内 full run 的 fixture `PermissionError` 不是
产品断言证据。正常宿主边界无需自定义 `--basetemp` 即可完成上述双版本全量回归。历史 ACL 目录
均被保留，未删除或纳入 delivery source。

## 未完成与未验证

- 四个真实 Codex collected 实例仍默认跳过；真实 Plugin load + MCP、真实 GitHub PR/Checks、
  Linux/macOS Runtime/IPC/worktree/parallel 仍未验证，统一进入 Phase 6E。
- Phase 6C Container Verifiers、Phase 6D Autonomous Delivery Closure、Phase 6E Integration
  Qualification、Phase 6F Observability 和 Phase 6G Optional UI 尚未开始。
- Claude Code Adapter、分布式 Worker、系统启动服务和自动合并未排期。

## 工作区与授权边界

- `origin/main=eedc46d1a607c6169cb43eca79ef56bdd137efac`；本地 `main=a069b36` 落后 9 个提交，
  不影响当前 Phase 6 baseline。
- Human 已授权创建包含本文件的单一 R0 本地 delivery commit。该授权不包含 push、PR、main
  修改/merge、Plugin 安装/发布、真实 GitHub 写入、历史重写或 Phase 6C 实现。
- 精确变更与证据见 `docs/phases/phase-6r-handoff.md`。

## 下一步

创建并核实单一 R0 reconciliation delivery commit，确保其 parent 为 `f9ee0b3`、内容仅为已审
R0 变更且工作树清洁。不要推送；push 需另行授权。本地与远端 R0 SHA 一致后，仍需单独授权才
允许使用 `docs/prompts/phase-6c-start.md`。
