# 当前缺口与路线建议

> 审计日期：2026-08-26
>
> 代码基准：`origin/main` @ `3cc79eb`（Phase 6G 已通过 PR #7 合入）
>
> 目的：区分“已经实现的边界”“尚未接通的用户路径”和“缺少真实环境证据”，避免把 fixture、设计目标或独立组件误称为完整产品能力。

## 结论

项目已经具备 MVP 级控制层骨架与大部分确定性运行能力，但还不是“克隆后即可让真实 Codex 自治完成任意需求”的成品。最大缺口是三处产品接线，其次是外部环境资格证据和发布体验。

## P0：阻塞真实用户闭环

### 1. 真实 Codex 未接入自治执行入口

- 已有：`CodexAdapter`、`DurableExecutorRuntime`、Session/Context/Handoff、受限 real-Codex 测试。
- 现状：`HumanGateway.run()` 只接受 `provider="deterministic_git_fixture"`；`ge run` 只有 `--deterministic-fixture`，内部使用 `FakeExecutor` / `FakeVerifier`。
- 影响：可以验证控制层与交付闭环，但用户不能从正式 CLI/MCP/UI 路径启动真实编码执行。
- 下一步：定义 provider 配置与权限模型，将真实 Executor/Verifier/Reviewer factory 注入 `AutonomousDeliveryCoordinator`，补充中断、恢复、错误分类和端到端测试。

### 2. Discovery 仍是固定七问，Codex 的缺失信息没有接入

- 已有：`CodexDiscoveryAdapter` 能输出结构化 `missing_information`。
- 现状：`DiscoveryService._QUESTIONS` 固定七类问题，`answer()` 只消费现有 unknown；回答完就生成草稿，没有追加 unknown 或 `max_rounds`。
- 影响：复杂项目可能在 Contract 冻结前漏掉仓库特定约束。
- 下一步：把只读分析结果规范化为 `UnknownItem`，去重、记录来源和轮次，循环至无新缺失项，并以 `max_rounds` / 总问题数预算 fail closed。

### 3. 默认图编译器不按需求复杂度选择拓扑

- 已有：固定串行 `ExecutionGraphCompiler`，以及 Phase 6B 的显式 parallel/subgraph/join 模型和 Runtime。
- 现状：所有 frozen Contract 默认编译成同一套 inspect → implement → verifier/repair → review/review_fix → deliver 串行模板；并行图需要外部显式提供。
- 影响：底层支持并行不等于产品会根据任务选择合适拓扑。
- 下一步：优先采用可解释的确定性多模板方案，以验收条件、Verifier、受影响模块和依赖关系作为信号；若改成模型直接生成图，需要先用 ADR 重新界定安全与可复现边界。

## P1：实现存在，但真实资格证据不足

| 能力 | 当前证据 | 尚缺 |
|---|---|---|
| Codex / Plugin | Adapter fixtures 与 opt-in 小范围 real-Codex 测试；本机 Codex 曾确认登录 | 隔离 `CODEX_HOME`、Plugin 安装、disposable repo、正式自治入口的完整 E2E |
| GitHub PR / Checks | 隔离本地 HTTP provider fixture、幂等/恢复测试 | 已授权仓库中的 push、checks、PR、comment、cleanup 全流程 |
| Container Verifier | Docker-compatible adapter、隔离/资源/secret/恢复测试 | 可用 Docker/Podman daemon、固定 digest 镜像、真实 cleanup/residual 证据 |
| Observability | dependency-free OTLP-compatible 边界、in-memory/no-op 测试 | 真实 collector/exporter、认证、字段、保留、失败和 cleanup E2E |
| Project UI | renderer/API/loopback HTTP/安全与可访问性语义测试 | 真实浏览器与键盘/读屏矩阵、Windows/Linux/macOS UI 验证 |
| 跨平台 package | Windows Python 3.12/3.13 clean install 和可重复构建 | Linux/macOS runner 以及完整 provider 组合 |

这些项不是“代码不存在”，但在证据分级中仍应标为 `blocked`、`unverified` 或 `partially supported`，不能写成 `passed`。

## P2：产品化与可维护性

1. **正式发布缺失**：未发布 PyPI、独立安装器或稳定升级通道；当前以源码 editable install / 本地 wheel 为主。
2. **首次使用体验仍偏工程化**：没有 `ge init`；Discovery 的七轮问答较机械，Run ID、Service 和 UI 需要用户理解内部概念。
3. **后台服务与托管缺失**：Runtime Service 是前台进程，没有系统服务注册、远程部署、TLS/DNS、多人权限或 hosted control plane。
4. **横向扩展未实现**：仅单机有界并行；没有分布式 worker、远程队列或 HA。该项目前仍是明确非目标，不应为了“架构完整”盲目加入。
5. **Provider 覆盖有限**：Claude Code Adapter 未排期；当前抽象是 provider-neutral，但可用实现不等于多 provider 产品。
6. **意图理解能力有限**：Intent Compiler 以确定性规则为主，复杂自然语言和组合意图需要澄清。未来可增加结构化模型分类，但必须保留 schema、置信度、确认策略和 fail-closed。
7. **运维可观测性仍是边界而非方案**：没有默认 SDK/exporter 依赖、仪表盘、告警和容量基线；这是有意保持核心无依赖，但产品化需要提供可选集成包。

## 已从旧清单关闭的项

- Phase 6G 本地 Project UI 已实现并随 0.8.0 package 打包。
- Phase 6 已通过 PR #7 合入 `main`。
- README 已从阶段流水账改为安装、体验、架构、限制和开发入口。
- 面试 HTML 已迁移到 Phase 6G 基线，并明确区分真实实现、fixture 和未来设计。

## 推荐路线

```text
P0.1 真实 Codex 自治接线
  → P0.2 动态 Discovery
  → P0.3 确定性多模板图编译
  → P1 真实 provider / browser / cross-platform qualification
  → P2 安装发布与首次使用体验
```

前三项应分别走独立、可评审的实现分支；不要把外部资格测试混进核心接线提交，也不要在没有 ADR 的情况下把图生成权直接交给模型。
