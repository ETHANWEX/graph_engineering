# Phase 6F Observability Compatibility

- Observability contract: 1.0, additive and internal provider boundary.
- Product/package: 0.8.0; Python `>=3.12,<3.14`.
- Runtime API / IPC / MCP: 1.0 / 1.0 / 1.0; Plugin: 0.1.0.
- SQLite migration head: 10; no new tables, columns, views or migration.
- Public JSON Schema: 36; no model or export change.

Existing constructors retain compatible defaults through a disabled no-op provider. Instrumented
read-only operations do not initialize/migrate Runtime state or write events, Artifacts, reports or
qualification evidence. Existing serial/parallel/container/autonomous paths keep their routing,
budgets, barriers, idempotency and terminal semantics.

The internal provider contract can be adapted to an OpenTelemetry SDK, but SDK/exporter packages
are optional. Absent imports, incompatible provider versions and exporter failures fail safely at
the telemetry boundary. No collector/backend is required for default tests or product operation.
