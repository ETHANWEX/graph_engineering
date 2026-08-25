# 缺失项清单

> 生成日期：2026-08-25。
> 基准：`origin/phase/6-enhancements`（Phase 6F 已交付，`ba30339`），相对 `origin/main`（Phase 5，`eedc46d`）。
> 说明：本清单为「产品完成态 vs 当前代码实际」的差距记录，供规划与面试诚实应答用。

## 缺失项（共 12 项）

1. **真实 Codex Executor 未接进自治执行路径** —— `gateway.run` / `cli run` 只认 `provider="deterministic_git_fixture"`，内部构造 `FakeExecutor`；`CodexAdapter`（已完整实现 `ExecutorProtocol`）没有任何地方被调用。

2. **真实 Codex E2E 证据缺失** —— 隔离 CODEX_HOME + Plugin 安装 + disposable repo 执行未获授权，`blocked by authorization`。

3. **真实 GitHub PR/Checks E2E 缺失** —— `gh` 未登录，无 owner/repo/write/cleanup 授权，`blocked`。

4. **真实容器 Verifier E2E 缺失** —— Docker/Podman 不存在，执行/安装/daemon/image pull 未授权，`blocked`。

5. **真实 OTLP/collector E2E 缺失** —— Phase 6F observability 全部 no-op，无 telemetry 离开本地进程，`blocked`。

6. **Linux / macOS runner 证据缺失** —— 均 `unverified`，Windows fixture 不作替代。

7. **Windows 平台证据不完整** —— 仅双 Python package + core 边界有 real-local 证据，Plugin-load/Codex/container 边界 blocked，整体只能标 `partially supported`。

8. **Discovery 动态追问未实现** —— 当前 `_QUESTIONS` 固定 7 问，`answer()` 只减不增，问完即结束；`CodexDiscoveryAdapter` 已产出 `missing_information` 但未接主流程，也无「追问到空」的循环。缺：接入 + `missing_information → UnknownItem` 追加 + 带 `max_rounds` 上限的循环。

9. **执行图可设计（按需求伸缩）未实现** —— 当前 `ExecutionGraphCompiler.compile()` 是固定模板，简单复杂一个样；期望「简单需求 → 单链 loop、复杂需求 → graph」。缺：复杂度信号 + 确定性多模板编译（方案 A），或模型生成图（方案 B，需 ADR）。

10. **Phase 6G Web UI 未开始** —— 无任何 6G 文档/代码，属可选 P3 项。

11. **整个 Phase 6 未合入 `main`** —— `origin/main` 仍停在 Phase 5（`eedc46d`），未创建 Graph Engineering PR。

12. **文档与实现脱节** —— `product-vision.md` 对照表、`project-walkthrough.md` 仍写「`ge run` 未实现、自治执行断了」，基于 `main`（Phase 0–5）写成，与分支实际进度不符。

## 性质归类

| 性质 | 项 | 说明 |
|---|---|---|
| 补胶水（组件已写好，只差接线） | 1、8 | `CodexAdapter`、`CodexDiscoveryAdapter` 都写好了，只差接线 |
| 补证据（代码已全，只差授权跑真环境） | 2–7 | 需要真实环境授权，不是写代码能解决的 |
| 架构决策（需先 ADR） | 9 | 图可设计动的是「方案从确定性编译改成模型生成」的安全边界 |
| 增量开发 | 10 | Phase 6G 可选 UI |
| 收尾 | 11、12 | 合并 + 文档对齐 |
