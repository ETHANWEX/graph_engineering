# Current Status

## 当前阶段

Phase 4：动态 Verifier 已在 `phase/4-dynamic-verifiers` stacked 分支实现并完成确定性、本地
隔离 HTTP fixture 与真实 Codex generation E2E。Human 已于 2026-08-18 明确批准提交并推送
Phase 4；仍不得创建 PR、修改或推送 main、合并或开始 Phase 5。

## stacked baseline 与集成顺序

- Phase 2 批准提交：`53df64ceea904bdad1f39f04a5d3168f5ae40d25`。
- Phase 3 批准提交：`b746b3f6b9f70838a6fe063e8a90104be7bca8a8`。
- Phase 3 本地/远端 `origin/phase/3-discovery-contract` 已核对为同一完整 SHA。
- Phase 4 从该精确 Phase 3 SHA 创建；当前分支未 rebase、reset、force 或伪合并 main。
- 启动时及最终 fetch 基线 `origin/main=a069b36fc0169dc51400265ea72a64c7b0b2839f`；Phase 2、
  Phase 3 均尚未合并。
- 强制集成顺序：Phase 2 → Phase 3 → Phase 4。

## 已完成

- ADR-019–023 和 Phase 4 scope。
- Verifier Registry/SDK、统一 pending/passed/failed/error/cancelled 结果语义。
- `builtin/command` 兼容注册、`builtin/http-pipeline`、`project/subprocess`。
- HTTP method/URL/header/body、JSON run-ID/status path、idempotency key、poll、timeout、bounded
  retry/backoff、report Artifact、cancel，以及 redirect host 二次校验。
- Runtime external handle owner/checkpoint/recovery；重启只 poll 不 retrigger；interrupt 先持久化
  barrier，再 cancel，并保存 unsupported/unknown residual effect。
- Manifest runtime/entrypoint/network/filesystem/secret/external-side-effect capability；network
  默认拒绝、exact host allowlist、filesystem root 约束与最小 secret 注入。
- raw、URL encoded、base64、overlap 与跨 chunk secret 脱敏；prompt、Artifact、error/event/report
  不保存 secret 值。
- argv-only、`shell=False`、JSON stdin/stdout subprocess 协议；timeout/output/schema/exit 限制，
  failed 与 infrastructure error 隔离。
- validate/test/dry-run/Human permission summary/freeze；Manifest/source/tests/fixtures hash，冻结
  revision 不可替换，漂移在副作用前拒绝，新 Verifier revision 要求新 Contract revision。
- declaration-first Discovery；仅声明式能力不足时调用 Codex 生成 Manifest、implementation、
  fixtures、tests。结构化 bundle、生成 tests、独立 protocol dry-run 与 policy gate 均必须通过。
- `ge verifier list|validate|permissions|test|dry-run|freeze`。

## SQLite migration 5

新增 `verifier_revisions`、`verifier_lifecycle_evidence`、`contract_verifier_bindings`；
`external_handles` 新增 verifier owner/revision、cancel state、report Artifact 和 residual effect。
`schema_version == 2`、`latest_migration_version == 3`、`storage_migration_version == 4` 保持旧阶段
兼容，真实数据库 head 由 `database_migration_version == 5` 报告。

## 协议与运行时事实

- 包版本 `0.5.0`；公共 Schema 1.0 仍为 30 个，无 public schema 漂移。
- Windows，CPython 3.12.10，Codex CLI 0.147.0，`Logged in using ChatGPT`。
- OpenAI Docs 与本机 help 均确认 `codex exec --json`、`--output-schema` 和显式 sandbox；生成器
  使用 `workspace-write` 隔离目录及 approval `never`，未使用 dangerous bypass。

## 验证摘要

- 默认 Phase 0–4：135 collected / 132 passed / 3 real-Codex skipped。
- Phase 0–3：108 collected / 106 passed / 2 skipped；Phase 0–2：91 / 90 / 1；Phase 0–1：62 passed。
- mypy strict、Ruff lint、Ruff format、30 Schema export/drift、有效/无效 Graph CLI、有效/无效
  Verifier Manifest CLI 均通过。
- 本地 loopback HTTP fixture 完成 trigger → pending poll → passed poll → report，单次 trigger 且
  report secret 已脱敏。
- 真实 Codex Phase 4 E2E 最终为 1 passed in 53.63s；前两次生成分别被独立 protocol gate 和
  filesystem capability gate 正确拒绝，收紧 prompt 后第三次通过生成 tests、dry-run、freeze/hash。

## 已知限制

- HTTP fixture 是本地隔离服务；未调用真实生产 CI/webhook。
- subprocess 是 OS 进程边界而非容器；Manifest/policy/Human summary 是首版信任边界。
- CLI/Runtime 仍为前台可恢复流程，不是 daemon。
- GitHub/PR、自动合并、Phase 5 Review/Delivery、Plugin/UI、容器、并行图与 telemetry 未实现。

## 工作区状态与下一步

- Human 已批准将 Phase 4 交付提交推送至 `origin/phase/4-dynamic-verifiers`；ignored 验收
  证据不进入提交。
- 未创建 PR，未修改或推送 main，未合并任何交付分支。
- Phase 4 不得先于 Phase 2、Phase 3 集成。Phase 4 集成前不得开始 Phase 5。
