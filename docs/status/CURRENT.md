# Current Status

## 当前阶段

Phase 6A 实现与本地验收已完成，并于 2026-08-19 通过 Human Review，获准在
`phase/6-enhancements` 创建唯一的本地 Phase 6A delivery commit。其基线是 Phase 6 路线提交
`51fad9e05c4b4d68f25d9c8bd1d269dcb0cd129f`。尚未授权推送、创建 PR、修改/合并 main、安装或
发布 Plugin、修改个人 Codex marketplace/config。Phase 6B 尚未开始，应在新对话中按启动 Prompt
重新执行门禁检查后开始。

## 已核实 baseline 与集成顺序

- `origin/main=eedc46d1a607c6169cb43eca79ef56bdd137efac`。
- Phase 5 实现 `db7dd54` 与交接 `4ebeb2da969e3cce9210fc3ed8dc23dbf3986662`
  均为 `origin/main` ancestor；两次 ancestor 检查均退出 0。
- Phase 6 路线提交的 parent 正是 `origin/main`；远端不存在 Phase 6 分支。
- 启动时 tracked/untracked 均为 0；9734 个 ignored 历史环境/pytest/cache 文件保持不变。
- 未 reset、rebase、cherry-pick、提交、推送或改写 main。

## Phase 6A 已实现

- package 0.7.0、ADR-029–031、Phase 6A scope 和 SQLite migration 7；旧 compatibility
  properties 仍为 2/3/4/5/6，实际 service migration head 为 7，Schema 1.0 的 30 个公共文件不变。
- 单 project foreground Runtime Service、私有 endpoint descriptor、health/version、单实例检查、
  authenticated controlled shutdown、stale cleanup，以及 Windows argv/path/subprocess/restart 行为。
- IPC 1.0 loopback JSON framing，request/idempotency/project/workspace identity，typed response/error，
  有限 frame/string/timeout/retry，major compatibility 拒绝和 capability 脱敏。
- mutation replay ledger 持久化 request fingerprint 与完成响应；同 key 不同请求冲突，未确定结果
  停止，重复请求不重复 HumanMessage、Run control 或外部副作用。
- 一个 Human Gateway 复用 ConversationRepository、HumanMessage、Intent Compiler、确认策略和
  typed Runtime control；pending action 绑定 actor/project/protocol/expiry。status/report 与 query
  Runtime snapshot 使用只读连接，不刷新 outbox 或改变执行状态；pause/interrupt 继续由 Runtime
  建立 barrier 后阻止新副作用。
- `ge service start|status|stop` 与 `ge mcp-server`；MCP 仅暴露严格校验的
  `start/message/confirm/status/report`，不直接访问 SQLite/worktree。
- 仓库内 `plugins/graph-engineering` 包含有效 manifest、Graph Engineering Skill、MCP config 和
  兼容/工作流说明；不持有权威 Run 状态。未安装、未发布、未修改个人配置。
- Phase 6B、Claude Code、并行图、容器、OpenTelemetry、UI、分布式 Worker 和自动合并未实现。

## 验证

- 启动 baseline：156 collected / 152 passed / 4 skipped；mypy strict、Ruff lint/format、Schema
  export/drift、Graph/Verifier CLI、migration repeatability 全部退出 0。
- Phase 6A focused：15 passed，覆盖 migration、service/IPC security/idempotency/version/expiry、
  read-only query、barrier、Windows subprocess/restart、MCP schemas/routing 和 repository Plugin。
- 当前 full regression：171 collected / 167 passed / 4 skipped（真实 Codex tests 默认跳过）。
- mypy strict、Ruff lint、Plugin validator 已退出 0；最终 format/Schema/CLI 分层证据见
  `docs/phases/phase-6a-handoff.md`。
- 隔离 MCP stdio → real Runtime Service E2E 和 Windows service subprocess E2E 是确定性本地证据，
  不冒充真实 Codex Plugin E2E。

## 环境限制与未验证项

- Windows / Python 3.12.10；Codex CLI 0.147.0，ChatGPT 登录。
- 未获授权安装仓库 Plugin 或修改个人 Codex 配置，因此真实 Codex Plugin load + MCP E2E 未执行，
  明确 unverified；确定性 MCP fixture 不替代该证据。
- 跨平台 Runtime/IPC/Plugin 行为未验证；Phase 6A 的进程与 endpoint 证据仅 Windows。
- GitHub 未登录且未获真实 repository 写授权；没有产生 GitHub 或其他外部副作用。

## 下一步

Phase 6A 本地 delivery commit 已获 Human 明确批准。下一对话读取 Phase 6A handoff 和
`docs/prompts/phase-6b-start.md`，核实该 delivery commit、干净工作树和分支事实后开始 Phase 6B。
推送仍需另行授权。
