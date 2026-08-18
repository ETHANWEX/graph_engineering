# Current Status

## 当前阶段

Phase 2：Codex Executor 与 Memory 已在 `phase/2-codex-memory` 实现并完成本地及真实 Codex
验收，等待 Human 审阅。未提交、未推送、未创建 PR、未合并，也未开始 Phase 3。

## 基线与同步

- 开始前执行 `git fetch origin`，`origin/main` 从 `ece58b0` 更新为 `a069b36`。
- `origin/main=a069b36` 直接包含 `5bad314` 和 `69dc5e9`，确认 Phase 1 已合并。
- 本地 `main` 从 `ece58b0` 以 `git pull --ff-only origin main` 安全快进到 `a069b36`。
- Phase 2 分支从该提交创建；开始时没有 tracked/untracked 修改。
- `.local/graph-engineering-interview-prep.md` 是既有 ignored 用户文件，未读取、未修改。

## 已完成

- 新增 ADR-007–011 和 Phase 2 可验证范围文档。
- provider-neutral Executor 协议：capabilities、start、resume、review、cancel；Core 不保存 Codex
  JSONL 或 argv。
- Codex preflight 记录版本、认证和 help-derived capabilities；0.147.0 + ChatGPT login 可用。
- Codex Adapter 使用 argv、approval `never`、workspace-write/read-only、JSONL、
  `--output-schema`、`--output-last-message`，拒绝 dangerous bypass。
- Pydantic JSON Schema 在 Adapter 内转换为 Codex Structured Outputs strict object 规则；公共
  Schema 1.0 不变。未知 JSONL 事件保留为 neutral unknown event，原始输出进入 Artifact。
- SQLite migration 3 新增 executor_sessions、supervised_processes、review_attempts 和
  verifier_executions；Session 结果/Artifact refs 可在进程重启后恢复并避免重复 attempt。
- fresh-per-node、同节点 bounded resume、continuation/failure rotate、Reviewer always-fresh。
- 限长确定性 Context Builder、不可丢弃 Contract/policy/schema、Repository Map 和 Handoff。
- GitWorkspaceManager 为每 Run 建立独立 branch/worktree；accepted commit restart 不修改来源。
- FrozenInputs 对 Contract/Graph/Verifier/acceptance lock 执行 hash 校验。
- 独立 read-only Reviewer/Observer；Observer 前后 execution fingerprint 不变，失败隔离。
- review changes_requested → Implementer fix → affected Command Verifier → fresh review attempt。
- argv-only Command Verifier：passed/failed/error/timeout/output limit 和原始证据 Artifact。
- ProcessSupervisor 与真实 Codex known-Session resume cancel；未及时退出返回 quiescing。

## 本机 Codex 运行时事实

- `codex-cli 0.147.0`；`codex login status` 为 `Logged in using ChatGPT`。
- help 支持 exec JSONL、output schema、last message、resume、review、sandbox 和 approval never。
- OpenAI Docs 确认 `codex exec` 是非交互入口，`--json` 是每状态变化一行 JSON，resume 是
  官方子命令：<https://learn.chatgpt.com/docs/developer-commands#codex-exec>。
- 真实调用发现 0.147.0 的 `exec review --output-schema` 最后消息仍是纯文本；结构化 Reviewer
  因而使用 fresh `codex exec` + read-only + Review Schema。native review capability 被记录但
  不冒充结构化通过。
- Windows pytest basetemp 会产生 Codex sandbox 无法进入的 ACL；真实验收使用预建、ignored、
  独立 fixture Git 目录，避免把基础设施错误误判为实现错误。

## 代码入口

- `executor/types.py`、`executor/runtime.py`、`executor/process.py`：协议、Session 策略、持久
  去重与进程监督。
- `adapters/codex.py`：preflight、argv、strict Schema、JSONL、Artifact 和 cancel。
- `context/`：Context Package、Handoff、Repository Map。
- `workspace/git.py`：Run branch/worktree 和 accepted commit materialization。
- `review/`：结构化 findings、fresh read-only roles 和 review-fix coordinator。
- `verifier/command.py`：声明式 argv Command Verifier。
- `runtime/sessions.py`、`runtime/frozen.py`、`runtime/store.py`：migration 3、恢复和 frozen hash。

## 数据与协议

- 包版本：`0.3.0`；公共协议和 30 个提交 JSON Schema 仍为 `1.0`，无漂移。
- StateStore 保留 Phase 1 `schema_version == 2` 兼容属性；实际最新存储迁移由
  `latest_migration_version == 3` 报告。
- SQLite 只保存 provider-neutral Session/version/status/counters/result/Artifact refs；Codex
  provider JSONL 只存在 Adapter raw Artifact。

## 验证结果

环境：Windows、CPython 3.12.10、Codex CLI 0.147.0，2026-08-16。

- Phase 0–2 默认 suite：90 passed、1 real-Codex skipped；共收集 91 项。
- 真实 Codex fixture：1 passed in 289.42s，覆盖 implement→failed verifier→fresh reviewer
  changes_requested→resume fix→passed verifier→fresh reviewer approved→fresh observer→持久化
  Session/Artifact/Handoff→Runtime 重启恢复→interrupt。
- mypy strict：0 issues；Ruff lint/format：通过。
- Phase 1 的 62 项测试未修改且保持通过。
- Schema、Graph CLI 与最终准确计数在 handoff 的最终复跑段记录。

## 已知问题与未完成

- native `codex exec review` 的结构化输出在 0.147.0 不可靠，使用已记录的 read-only exec
  fallback；未来版本需 fixture/preflight 再启用 native structured review。
- ProcessSupervisor 是本机进程边界；OS 无法及时终止时只能 quiescing 并披露，不能宣称回滚。
- Phase 2 不含自然语言 Gateway、动态/HTTP Verifier、远程 CI、GitHub、daemon、Plugin/UI、
  并行图或完整 Phase 5 requirement matrix。

## 工作区状态

- 分支：`phase/2-codex-memory`；基线：`a069b36`。
- Phase 2 修改未提交，等待 Human review；不得 push/PR/merge。
- ignored `.local/real-codex-fixture` 保留真实验收的临时 Git repo、raw JSONL/command evidence。

## 下一阶段第一步

Human 审阅 Phase 2 的实现、测试和真实 Codex 证据；只有明确批准后才提交并推送本分支。
Phase 2 集成 main 之前不得开始 Phase 3。
