# Current Status

## 当前阶段

Phase 6E Integration Qualification 正在实现并执行已授权的本地资格测试。长期分支为
`phase/6-enhancements`；baseline、本地 HEAD 与远端 Phase 6 HEAD 均为 Phase 6D delivery
`651352c056c5402c6a4a4057946822948a23ea66`，其唯一 parent 是 Phase 6C delivery
`50f1d0a47d6c210c407af79b5c00e73b43ea984e`；`origin/main` 保持
`eedc46d1a607c6169cb43eca79ef56bdd137efac`。Phase 6D handoff/README 的 pre-delivery 措辞是
冻结历史快照；Phase 6E 不重写它们。

## Phase 6E 已实现

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

全部 Phase 6E 结果保持未提交。完成最终双 Python/full/focused/static/Schema/CLI 验证并创建
`docs/phases/phase-6e-handoff.md` 后等待 Human Review。13 个本次 system-temp qualification 根已
清理且残留为零；pip shared cache 未删除。未经再次明确授权，不得 commit、push、
PR、修改/合并 main、发布 package/Plugin、修改 marketplace、执行真实 Codex/GitHub/container、
创建 runner/VM、auto-merge 或开始 Phase 6F。
