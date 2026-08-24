# Current Status

## 当前阶段

Phase 6C Container Verifiers 实现与验收证据已完成并通过 Human Review；Human 已明确
授权创建单一 Phase 6C delivery commit 并推送到 `phase/6-enhancements`。
分支为 `phase/6-enhancements`，精确 pre-delivery baseline 是 R0 delivery
`b7da3c4c7712db0f8fb01f14cd2d141008c5186a`；Phase 6C delivery 是包含本 CURRENT 和
handoff 的单一 child commit，SHA 在创建后核实并推送到同一远端分支；
`origin/main=eedc46d1a607c6169cb43eca79ef56bdd137efac`。

## Phase 6C 已完成

- `project/container` 复用 exact-name Verifier Registry 和统一 `VerifierResult`；Docker CLI
  和兼容 runtime 细节保持在 adapter 边界。缺失 runtime、版本不兼容、daemon 不可用
  和能力不足为 typed preflight infrastructure error，不安装 runtime 或修改系统服务。
- 冻结容器定义绑定 registry/repository/`sha256` digest/platform/provenance/entrypoint/config
  fingerprint；拒绝 mutable tag、allowlist 越界和冻结漂移。
- CPU、memory、PID、wall-clock、stdout/stderr、Artifact 和 concurrency 限额有限；Docker
  log 两流并发限长读取，超额在读取过程中请求终止。
- mount 仅允许已授权 root 下的相对路径，启动前重新 resolve；拒绝 Windows/POSIX
  绝对路径、`..`、symlink/junction/reparse escape、Docker socket、home 和系统目录。
  frozen/evidence 只读，writable mount 必须显式且最小化。
- 默认 `network=none`；启用网络需 exact protocol/host/port 冻结策略且 adapter 必须
  能可靠执行 DNS/redirect/proxy/custom-host 边界，否则 fail closed。
- Secret 仅以 reference 冻结，执行时通过短命环境文件或 adapter request 注入；raw、
  URL encoded、base64、overlap 和跨 chunk 内容在 Artifact/error/event/checkpoint/report 前脱敏。
- SQLite migration 9 持久化 execution/owner/attempt/idempotency/handle/digest/fingerprint/
  byte accounting/result/cleanup/residual state。恢复查询已有 handle，完成结果复用，无 handle
  的 uncertain start 不重触发；parallel branch qualified identity 保持兼容。
- pause/barrier 后不启动容器；interrupt/cancel 有界 stop/settlement；cleanup 仅按稳定
  owner label 处理本 attempt 资源，失败与 residual 进入 Event、Artifact 和 Final Report。

## 决策、迁移与兼容性

- ADR-034：provider-neutral container 边界与不可变 image identity。
- ADR-035：资源、mount、network 与 secret 的 fail-closed sandbox 策略。
- ADR-036：持久恢复、cancel/settlement、owned cleanup 和 residual effect。
- migration head 从 8 增加到 9；migration 1–9 repeatable。`parallel_migration_version=8`、
  `service_migration_version=7` 等旧 compatibility view 保持。
- `VerifierManifest` 内部 SDK 加法支持 `project/container`。公共 Schema 1.0 仍为 36 个，
  export drift 为零；历史 serial Graph canonical 内容未改。
- Runtime Service、IPC 1.0、MCP、Plugin、串行/并行 Runtime 和 query/report 只读边界保持兼容。

## 最终验证

- 修改前 sandbox baseline：190 collected，`62 passed / 3 skipped / 125 tmp_path ACL errors`，
  12.46s，exit 1；没有产品断言失败。
- 修改前宿主 baseline：Python 3.13.14 `186 passed / 4 skipped` in 34.23s；Python
  3.12.10 `186 passed / 4 skipped` in 33.63s；均为 190 collected、exit 0。
- Phase 6C focused + Registry + migration compatibility：32 passed in 5.13s，exit 0。
- 最终 Python 3.13.14 宿主全量：215 collected / 211 passed / 4 skipped in 39.41s，
  exit 0。
- 最终 Python 3.12.10 宿主全量：215 collected / 211 passed / 4 skipped in 38.36s，
  exit 0。
- mypy strict：126 source files 无问题；Ruff lint 通过；Ruff format：126 files clean。
- Schema export：36 files，drift 为零；migration head 9。历史与 Phase 6B Graph CLI、
  Verifier list/validate 均 exit 0，列表包含 `project/container`。

四个 skipped collected instances 仍仅为现有 opt-in 真实 Codex 验收实例，Phase 6C 没有
添加、弱化或伪装 skip。受管 sandbox 的 pytest 失败仅来自系统临时根 ACL；宿主
证据使用全新固定 basetemp，不删除任何历史 `.pytest-*` 目录。

## 未验证与残留事项

- 宿主无 Docker 与 Podman，因此真实容器隔离、cgroup/resource enforcement、mount/
  network namespace、真实 stop/cleanup E2E 标记为 **unverified**。没有安装 runtime、
  启动系统服务或拉取镜像。
- exact network allowlist 在默认 Docker CLI adapter 中不被声称为可执行；该 adapter
  仅安全支持 `network=none`，需要网络时必须提供可靠强制 exact policy 的兼容 adapter。
- deterministic fake adapter/fake process 证据仅验证 Graph Engineering 协议和状态机，
  不冒充真实容器隔离证据。没有容器、volume、network namespace 或外部 provider 副作用残留。

## 工作区与下一门禁

- Phase 6C 的单一 delivery commit 和 Phase 6 分支 push 已获授权；delivery SHA 在创建后通过
  Git 核实。历史 pytest evidence 目录和 ignored 环境未删除。
- 未授权 PR、main 修改/merge、Plugin 安装/发布、真实外部写入或 Phase 6D 实现。
- 精确交接见 `docs/phases/phase-6c-handoff.md`。下一阶段是 Phase 6D Autonomous
  Delivery Closure，启动 prompt 为 `docs/prompts/phase-6d-start.md`；开始实现仍需独立明确授权。
