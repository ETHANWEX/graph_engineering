# Current Status

## 当前阶段

Phase 6G Optional Project UI 已完成本地实现与验证，并进入已授权的单一 delivery commit
门禁。长期分支为
`phase/6-enhancements`；baseline、本地 HEAD 与远端 Phase 6 HEAD 均为 Human 已接受并推送的
Phase 6F delivery `ba30339922f9412cc369063efa2c136e0a3aef1f`，其 parent 是 Phase 6E
delivery `e1aa9c61f568b7dda6c77248bc87a000f539a0ca`；`origin/main` 保持
`eedc46d1a607c6169cb43eca79ef56bdd137efac`。Phase 6F handoff 的 delivery 前措辞是冻结历史
快照，不予重写；本文件记录实际 Phase 6F delivery 与 push 事实。

## Phase 6G 当前范围

- ADR-043 起定义无新增依赖、离线、loopback-only 的可选 Project UI 与 UI/API contract 1.0。
- UI 只通过 Runtime Service/Human Gateway 的版本化 API 读取 snapshot、提交 HumanMessage 和
  confirmation；不直接打开 SQLite、worktree、Artifact、provider 或 qualification evidence。
- 服务端渲染安全 HTML，静态资源随 wheel 打包；实时更新使用有界 polling，并从权威 snapshot
  在 refresh/reconnect/Runtime restart 后恢复。
- Origin/Host/CSRF/CSP/frame/MIME/no-store、安全 URL 与文本呈现、请求/响应/并发/slow-client
  bounds、secret rejection 和键盘/语义 accessibility 均为 acceptance gate。
- 不新增 SQLite migration 或公共 Core Schema；产品/package 仍为 0.8.0。

## Phase 6G 验证与结论

- test-first 红灯先证明 `graph_engineering.ui` 尚不存在；交付前审阅又用 3 个失败断言锁定原生
  浏览器控制器、CSP script 边界与 wheel JavaScript asset，随后实现并恢复全绿。
- Phase 6G focused 18 passed；受影响 Conversation/Control/Service/6D/6F/6G regression 60 passed。
- Python 3.13 与 Python 3.12 最终全量均为 `262 passed / 4 skipped`；四个 skip 仍仅是历史 opt-in
  real-Codex cases。mypy 145 source files clean，Ruff lint/format passed。
- 36 Schema zero drift，serial/parallel Graph 与 Verifier list/validate passed；migration head 保持
  10，Phase 6E qualification focused 10 passed。
- 最终 wheel/sdist 在固定 `SOURCE_DATE_EPOCH` 下各两次 byte-identical；干净 Python 3.12/3.13
  venv 从本地 wheel 安装并通过 0.8.0 metadata、CLI/UI entrypoint、958-byte CSS 与 3229-byte
  JavaScript package assets、
  static assets、36 Schema、serial/parallel Graph 和 Verifier smoke。精确哈希与编排失败见
  `docs/phases/phase-6g-handoff.md`。
- 没有真实 browser automation，因此浏览器/accessibility matrix 诚实标记 unverified；deterministic
  HTTP 测试不冒充真实浏览器证据。外部 hosting、Linux/macOS UI、TLS/DNS/CDN 均未执行。

## Phase 6E 已交付基线

- qualification evidence/claim matrix 1.0 独立于 Runtime SQLite，记录 product/protocol/Git/
  host/tool/auth 状态、typed operation、时间/退出码/count、Artifact、cleanup、residual、限制与
  recovery guidance。查询现有 evidence 不初始化或迁移 Runtime，也不改写 evidence 文件。
- evidence classification 严格区分 deterministic fixture、real local、real external、
  supported-platform、blocked 和 unverified；blocked/unverified/unavailable 不可成为 passed。
- Secret guard 拒绝 secret-bearing key 及配置 secret 的 raw、URL、base64、overlap 和跨 chunk
  形式；认证只保存枚举状态，不保存 token、cookie、header 或原始输出。
- `ge qualification collect` 只读采集本地身份并输出诚实的默认 matrix；
  `ge qualification report` 只读加载严格版本化 evidence。
- ADR-041 修复真实 sdist 不可重复 failure：固定 `SOURCE_DATE_EPOCH` 时规范 tar/gzip 时间与
  owner metadata；wheel/sdist 各两次构建达到 byte-identical。SPDX license metadata 同步修正。
- 本地 wheel 已在干净 Python 3.12/3.13 venv 安装，并通过 metadata/entrypoint、36 Schema、
  serial/parallel Graph、Verifier、migration 10、foreground Service/IPC cleanup 和 MCP handshake。
- 精确 Phase 6D delivery wheel 到当前 build 的 upgrade、uninstall/reinstall 保持项目 Runtime DB
  和历史 evidence 字节不变。两个开发 build 都是 0.8.0，以 Git/artifact hash 区分。

## 决策、迁移与兼容性

- ADR-040：versioned、secret-safe、non-authoritative qualification evidence 与 fail-closed
  classification。
- ADR-041：显式 `SOURCE_DATE_EPOCH` 下的 reproducible setuptools sdist 与隔离 package 资格。
- package/产品仍为 0.8.0；Plugin 0.1.0 要求 ge 0.8.x 与 Codex >=0.147.0；Runtime API、IPC、
  MCP 均为 1.0。migration head 保持 10，公共 Schema 保持 36，无公共协议或 SQLite 变化。
- Runtime SQLite 仍是唯一 Run 权威；qualification 文件从不成为 routing/recovery 状态源。

## 当前证据

- Phase 6F focused：13 passed；受影响 Phase 2/5/6A–6D regression：93 passed；Phase 6D
  autonomous delivery + Phase 6E qualification 宿主短路径回归：20 passed。
- Phase 6F 最终全量 248 collected：Python 3.13.14 `244 passed / 4 skipped` in 50.38s；
  Python 3.12.10 `244 passed / 4 skipped` in 50.78s，均 exit 0。
- Phase 6F 最终 mypy 136 source files clean；Ruff lint passed、136 files format clean；36 Schema
  zero drift；serial/parallel Graph 与 Verifier list/validate passed。
- 无依赖、package version、SQLite migration 或公共 Schema 变化。单独获批后，Phase 6E 固定
  build toolchain 从 pip cache 安装到一次性 venv；当前快照 wheel/sdist 构建成功，wheel 在全新
  Python 3.12/3.13 venv 离线安装并通过 metadata/observability import smoke。artifact hash 与
  cleanup 见 `docs/phases/phase-6f-handoff.md`；未改写 Phase 6E 冻结 evidence。
- 真实 OTLP/collector/SaaS E2E 未获精确 endpoint/字段/认证/保留/cleanup 授权，**blocked**；没有
  telemetry 离开本地进程。详见 `docs/phases/phase-6f-handoff.md`。

- 修改前受管 sandbox：225 collected，`70 passed / 3 skipped / 152 tmp_path ACL errors`，exit 1；
  仅为 pytest 临时根 ACL，未记为通过。宿主 Python 3.13.14 与 3.12.10 均为
  `221 passed / 4 skipped`，exit 0。
- 修改前 mypy 128 source files clean；Ruff lint/format、36 Schema drift、serial/parallel Graph、
  Verifier list/validate、migration/history/Plugin static focused 15 tests 全部通过。
- Phase 6E + Phase 6D/Plugin/MCP/IPC/parallel/container focused：73 passed in 25.14s；其中
  qualification tests 为 10 passed。
- 最终全量 235 collected：Python 3.13.14 `231 passed / 4 skipped` in 48.09s；Python 3.12.10
  `231 passed / 4 skipped` in 48.74s，均 exit 0。
- 最终 mypy 132 source files clean；Ruff lint passed、133 files format clean；36 Schema zero drift；
  serial/parallel Graph 与 Verifier list/validate passed。
- final reproducible artifacts：wheel
  `3b1baf9f0dc1d5e8d3e85082c5d4e04265b5ad2c5830203bc9d984a207a1779a`；sdist
  `383673ba52daa88ad39b02f874c206d05f01d2372422135f2a70aaac7df59eec`。
- Phase 6D wheel：`b92ab0f2958eb3e949c56026164a5e000e4f8c1b112190105defc00c5bff6c0f`。
- identity evidence v1 保留 Windows locale decode failure，v2 保留错误 auth-stream limitation，v3
  正确记录 Codex 0.147.0 authenticated、GitHub CLI 2.97.0 unauthenticated、Docker/Podman absent。

四个默认 skip 仍仅为既有 opt-in real-Codex cases，没有新增 skip/xfail 或弱化断言。真实失败与
qualification 编排失败均保留在 release-readiness report，不以重跑覆盖历史分类。

## Provider 与支持平台结论

- Windows 双 Python package 与本地 core boundaries 有 real-local evidence；但真实 Plugin-load/
  Codex 和 container 边界仍阻断，因此 Windows 整体只可标记 partially supported/unverified。
- 真实 Codex Plugin load/autonomous execution：Codex 已认证，但隔离 CODEX_HOME、Plugin 安装和
  disposable repository execution 未获单独授权，**blocked by authorization**。
- 真实 GitHub：CLI 未认证且没有 owner/repository/branch/write/cleanup 授权，**blocked**；没有
  push、PR、Checks、comment、settings、protection 或 merge。
- 真实 container：Docker/Podman 不存在且执行/安装/daemon/image pull 未授权，**blocked**；没有
  container、volume、network 或 image 残留。
- Linux/macOS：没有获批 runner，均为 **unverified**；Windows fixture 不作替代。

## 工作区与下一门禁

Phase 6G 经本次 Human 授权完成单一 delivery commit 后，Phase 6 已排期路线结束。不得 push、PR、修改/合并 main、发布
package/Plugin/UI、外部 hosting、真实 provider/telemetry 写入、auto-merge，或开始 Claude Code
Adapter、分布式 worker与任何未排期阶段。
