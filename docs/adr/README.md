# Architecture Decision Records

Accepted decisions are append-only. A later ADR may supersede a decision but does not rewrite its
historical file.

- [ADR-001](001-independent-core.md) through [ADR-006](006-runtime-control-and-recovery.md): core,
  protocol, persistence, control and recovery foundations.
- [ADR-007](007-executor-adapter-boundary.md) through
  [ADR-011](011-readonly-agents-command-verifier.md): Executor/Codex, worktree, Session/context and
  read-only role boundaries.
- [ADR-012](012-human-conversation-control-boundary.md) through
  [ADR-018](018-query-and-barrier-isolation.md): Human conversation, Discovery, freeze/revision,
  compilation, lineage, query and barrier boundaries.
- [ADR-019](019-verifier-registry-result-protocol.md) through
  [ADR-023](023-codex-verifier-generation-boundary.md): Verifier Registry, HTTP/subprocess,
  capabilities, secrets, lifecycle and generated-code trust.
- [ADR-024](024-multidimensional-review-attempts.md) through
  [ADR-028](028-human-delivery-decisions-and-secrets.md): Review, requirement evidence, GitHub,
  reports and Human delivery decisions.
- [ADR-029](029-runtime-service-and-windows-lifecycle.md) through
  [ADR-031](031-human-gateway-mcp-plugin-compatibility.md): Runtime Service, IPC, MCP and Plugin.
- [ADR-032](032-explicit-parallel-subgraph-join-protocol.md) and
  [ADR-033](033-durable-bounded-parallel-runtime.md): parallel Graph protocol and Runtime.
- [ADR-034](034-container-verifier-provider-and-image-identity.md) through
  [ADR-036](036-container-recovery-cancellation-and-cleanup.md): container identity, sandbox,
  recovery and cleanup.
- [ADR-037](037-confirmed-prepared-explicit-run-start.md) through
  [ADR-039](039-phase6d-control-and-report-boundary.md): autonomous delivery closure.
- [ADR-040](040-versioned-qualification-evidence.md) and
  [ADR-041](041-reproducible-local-package-qualification.md): qualification and packaging.
- [ADR-042](042-non-authoritative-observability-provider.md): non-authoritative, secret-safe,
  bounded observability provider boundary.
