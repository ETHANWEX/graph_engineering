# Phase 6A New-Conversation Startup Prompt

Copy the text below into a new conversation.

```text
# Repository instructions

工作区：

E:\project\graph_engineering

请开始实现 Graph Engineering Phase 6A：Runtime Service、本地 IPC、MCP Server 与 Codex
Plugin。

## Human 决策与分支方式

Phase 5 已经通过 PR #6 合并到远端 main。Phase 6 使用 Human 明确指定的单一长期分支：

phase/6-enhancements

Phase 6A、6B……在该分支上顺序开发，每个完成的子阶段形成一个独立、可审阅的 delivery
commit。不得为 6A 另建分支，也不得在 main 上开发。

Claude Code Adapter 当前未排期。Phase 6A 不得实现并行图、容器化 Verifier、OpenTelemetry、
UI、Claude Code 或其他后续子阶段能力。

本授权允许持续实现 Phase 6A，但不预先授权提交、推送、创建 PR、修改 main、合并、安装或发布
真实 Plugin、修改个人 marketplace/config，或者开始 Phase 6B。

Phase 6A 完成后必须先报告并等待 Human Review。只有 Human 再次明确批准后，才可创建 Phase 6A
delivery commit 或推送。

## 启动检查

首先执行：

git fetch origin

然后核实并报告：

- 当前分支必须是 `phase/6-enhancements`。
- git status、tracked、untracked 和 ignored 文件。
- 当前 HEAD、origin/main 和远端 Phase 6 分支（如存在）的完整 SHA。
- Phase 5 `db7dd54` 和 `4ebeb2da969e3cce9210fc3ed8dc23dbf3986662` 是否为
  `origin/main` ancestor。
- Phase 6 路线文档提交及分支基线。
- 是否已有 Phase 6A 代码、文档、ADR、migration、测试或部分实现。
- README、CURRENT 和 handoff 是否与远端事实一致。
- Python 3.12、Codex CLI 版本和登录状态。
- Codex Plugin、Skill 和 MCP 相关本机能力。
- Phase 0–5 全量 pytest、mypy strict、Ruff lint/format、Schema drift、SQLite migration head、
  Graph CLI 和 Verifier Manifest CLI。

至少执行：

git merge-base --is-ancestor db7dd54 origin/main
git merge-base --is-ancestor 4ebeb2da969e3cce9210fc3ed8dc23dbf3986662 origin/main

两个命令必须退出 0。

如果当前不在 `phase/6-enhancements`，不要自行创建替代分支、reset、rebase、cherry-pick 或改写
历史；先检查 `docs/phases/phase-6.md` 和远端分支事实。工作树如有无法确认归属的修改，立即停止
并报告。

## 修改前必须完整阅读

1. AGENTS.md
2. DESIGN.md
3. README.md
4. CONTRIBUTING.md
5. docs/status/CURRENT.md
6. docs/phases/phase-6.md
7. docs/prompts/phase-6a-start.md
8. Phase 0–5 全部 scope 和 handoff
9. 仓库内全部 ADR
10. pyproject.toml
11. 全部现有测试、公共 Schema 和 fixtures
12. Core、Runtime、Control、Conversation、Context、Session、Artifact、Report
13. Compiler、Executor、Verifier、Review、Requirement Matrix、Delivery
14. SQLite migrations、Event Store、checkpoint、external handle 和 CLI
15. DESIGN.md 的插件集成、部署形态、环境依赖、版本兼容、Human Control Conversation、
    Runtime、barrier、Phase 6 和跨对话交接章节

`docs/phases/phase-6.md` 是 Phase 6 范围、顺序和不变量的权威文件。聊天摘要不能取代它。

## Skills 和官方事实

Phase 6A 涉及 Codex Plugin、Skill 和 MCP，必须使用：

- `openai-docs` skill：核对当前官方 Codex Plugin、Skill、MCP、CLI、配置和权限文档。
- `plugin-creator` skill：核对并创建仓库内有效 Plugin 结构和 manifest。

默认只创建仓库内可审阅的 Plugin package。未经额外授权，不得安装到个人 Codex 环境、修改个人
marketplace、发布 Plugin 或修改全局配置。

同时以本机实际安装为事实，至少检查：

codex --version
codex login status
codex --help
codex mcp --help

如 DESIGN.md、官方文档和本机 CLI 不一致，以官方文档和实际安装版本为运行时事实，并通过 ADR
记录兼容策略。

## Phase 6A 范围

### 1. Runtime Service

- 独立本地 Runtime Service 生命周期、health、version 和 controlled shutdown。
- Runtime restart 后恢复 Run、checkpoint 和 external handle。
- 单实例或明确的多实例/项目隔离策略。
- Windows 路径、进程、endpoint、shutdown 和 cleanup。
- 不依赖 Codex、MCP Session 或聊天上下文保存状态。
- 不创建系统服务或开机自启动项；测试可以使用受控子进程。

### 2. 本地 IPC

- versioned protocol、request ID、幂等键、project/Run/workspace identity。
- typed request/response/error、timeout、disconnect、reconnect、bounded retry 和大小限制。
- 本地 endpoint 身份与授权，未授权客户端 fail closed。
- mutation replay 不重复 Run 或外部副作用。
- query/status/report 保持只读。
- 不接受任意 Python、Shell 或表达式源码。
- Provider、Codex 或 MCP wire format 不进入 Core。

### 3. MCP Server

实现 `ge mcp-server`，至少暴露：

- `start`
- `message`
- `confirm`
- `status`
- `report`

要求：

- `message` 创建持久化 HumanMessage。
- mutation 必须经过 Intent Compiler、确认策略和强类型 ControlIntent。
- MCP tool 不得直接修改 Runtime、SQLite 或工作区。
- `confirm` 只能确认已持久化且仍有效的 pending action。
- target 缺失、歧义、过期、未授权或版本不兼容时 fail closed。
- MCP 断线不终止 Run。
- 重复请求幂等。
- MCP error 不伪装成业务失败、Verifier failure 或 Review verdict。

### 4. Codex Plugin

- 有效 `.codex-plugin/plugin.json`。
- Graph Engineering Skill 和使用说明。
- MCP 配置模板。
- Runtime、`ge` 和 Codex 版本要求及兼容检查。
- start/message/confirm/status/report 工作流。
- Plugin 不保存权威 Run 状态，不直接写 SQLite/worktree/external handle。
- Codex 退出、Session 替换或 compact 不损坏 Run。
- Runtime 不存在或版本不兼容时明确拒绝。

### 5. 统一 API 和兼容性

CLI、MCP 和 Plugin 必须复用相同 Human Gateway、Intent Compiler、Runtime 和 Report API，不得
形成旁路。

按实际设计增加必要 CLI，例如：

ge service start
ge service status
ge service stop
ge mcp-server

定义 Runtime/API、IPC、MCP tools、Plugin、`requires_ge` 和 Codex host 版本。公共协议变化必须
先有 ADR、兼容分析、fixtures、migration、Schema export 和 drift 测试。Phase 0–5 历史数据和
Run 必须保持可读。

## 必须保持的不变量

- Runtime 持久化是唯一事实来源。
- HumanMessage 是自然语言唯一入口。
- Runtime 只接受强类型 ControlIntent。
- 冻结和历史记录只能追加或版本化。
- query/status/report 无副作用。
- pause/interrupt 先建立持久化 barrier。
- barrier 后不得启动 Agent、Verifier、subprocess、HTTP、GitHub 或其他副作用。
- secret 值不得进入 prompt、协议、日志、事件、异常、Artifact 或报告。
- 默认不 merge。
- 不允许任意 Python、Shell 字符串或表达式求值。
- 不得弱化 Phase 0–5 测试。

## 明确禁止

- Phase 6B 或后续子阶段。
- Claude Code Adapter。
- 并行节点、子图或 join。
- 容器化 Verifier。
- OpenTelemetry。
- Web、IDE 或桌面 UI。
- 分布式 Worker。
- 自动合并或绕过 branch protection。
- 未经授权安装/发布 Plugin或修改个人 Codex 配置。
- 后台系统服务或开机自启动。

## ADR 优先

检查实际 ADR 编号；若最新为 ADR-028，从 ADR-029 开始。至少收敛：

1. Runtime Service 生命周期和权威状态。
2. IPC 版本、身份、授权、幂等和重连。
3. MCP tools 与 HumanMessage/ControlIntent 路由。
4. Codex Plugin 薄入口、manifest、Skill 和 config 边界。
5. Plugin/MCP/IPC/Runtime 版本兼容。
6. barrier 与 IPC/MCP 副作用。
7. secret/redaction 和本地客户端安全。
8. Windows 进程、路径和清理。
9. fixture 与真实 Codex Plugin E2E 的证据分类。

## 工作顺序

1. 完成启动核验并确认 Phase 6 路线提交。
2. 更新 README/CURRENT 的活动阶段。
3. 创建 `docs/phases/phase-6a.md`。
4. 编写 ADR。
5. 编写失败测试。
6. 实现 Runtime Service 和 IPC。
7. 实现 MCP Server。
8. 使用 plugin-creator 创建仓库内 Plugin package。
9. 分层验证和隔离 E2E。
10. 只有额外授权后才可真实安装 Plugin。
11. 创建 `docs/phases/phase-6a-handoff.md` 并更新 README/CURRENT。
12. 报告未提交结果，等待 Human Review。

## 优先验收

- Service start/status/stop、health 和 version。
- Runtime restart、client reconnect 和 Run 恢复。
- IPC identity/version/authorization/limits/timeout/typed errors。
- mutation replay 不重复副作用。
- MCP tools schema validation 和五个工具完整路由。
- HumanMessage 先持久化，Intent Compiler/确认策略不可绕过。
- query/status/report 无副作用。
- barrier 后无新副作用。
- Plugin manifest、Skill 和配置 validation。
- Plugin 不持有权威状态。
- Codex Session 替换后找回同一 Run。
- 版本不兼容 fail closed。
- migration repeatability 和历史数据兼容。
- secret 全链路脱敏。
- Windows 路径、进程、endpoint 和 cleanup。
- Phase 0–5 全部回归、mypy strict、Ruff 和 Schema drift。
- 隔离 Plugin/MCP E2E。
- 真实 Codex Plugin/MCP E2E；阻塞时不得用 fixture 冒充。

## 文档和交接

创建或更新：

- README.md
- docs/status/CURRENT.md
- docs/phases/phase-6a.md
- docs/phases/phase-6a-handoff.md
- ADR、必要 migration、fixtures 和 Schema

Phase 6A handoff 必须记录 baseline/current commit、ADR、migration、协议兼容、Runtime/IPC/MCP/
Plugin、全部测试证据、风险、未验证项、Claude Code 未实现、Phase 6B 未开始，以及 Phase 6B 的
准确启动 Prompt。

## 交付规则

持续实现 Phase 6A，直到验收满足或出现范围内无法解决的阻塞。完成后先报告并等待 Human Review。

未经 Human 再次明确批准：

- 不得创建 Phase 6A delivery commit 或推送。
- 不得创建 Graph Engineering PR。
- 不得修改或推送 main。
- 不得合并、force push、reset、自动 rebase 或改写历史。
- 不得安装或发布真实 Plugin。
- 不得开始 Phase 6B。
- 不得实现 Claude Code Adapter。
```
