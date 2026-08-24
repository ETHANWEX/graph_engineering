# Graph Engineering Observability Contract 1.0

## Authority boundary

Telemetry is advisory and lossy. Runtime SQLite, frozen inputs, checkpoints, provider handles and
content-addressed evidence remain authoritative. A span, metric, exporter acknowledgement or
collector query may never select a route, recover work, decide a terminal state or prove cleanup.

## Stable spans

`ge.runtime.run`, `ge.runtime.node`, `ge.runtime.parallel_branch`, `ge.executor.invocation`,
`ge.verifier.execution`, `ge.review.attempt`, `ge.review.fix`, `ge.service.operation`,
`ge.ipc.request`, `ge.mcp.request`, `ge.github.operation`, `ge.report.generate`,
`ge.human.decision`, `ge.runtime.recovery`, and `ge.runtime.cleanup`.

Parent/child follows synchronous causality. Concurrent branches are children of the parallel node
and link to their deterministic branch identity. Recovered operations reuse the deterministic Run
trace identity and link to the recovered persisted identity; they do not claim an in-process parent
that no longer exists.

## Stable metrics

`ge.operation.duration`, `ge.operation.result`, `ge.operation.retry`, `ge.budget.usage`,
`ge.queue.size`, `ge.operations.active`, `ge.telemetry.dropped`, `ge.exporter.failure`, and
`ge.exporter.duration`. Units are seconds for duration and integer counts otherwise.

Metric labels are limited to `component`, `operation`, `result`, `reason`, `retryable`, `provider`,
and `protocol_version`, each selected from a bounded configured set. Persisted IDs are span
attributes only and never metric labels.

## Identity and attributes

Allowed identity keys are repository/project, Run, node, attempt, branch, Session, verifier/review,
external-effect idempotency, provider handle, report/artifact and request identities. Values are
bounded opaque identifiers. Allowed non-identity attributes are bounded operation/result/action,
terminal/recovered/late/retryable booleans, finite counts, budget values, cleanup state and declared
protocol/provider versions.

Paths, repository URLs, endpoints, usernames, branch names, commands, prompts, messages, log or
exception bodies, file contents and provider responses are rejected. Secret-bearing keys and raw,
URL-encoded, base64, overlap or cross-chunk secret values are rejected before buffering/export.

## Sampling, buffering and lifecycle

Sampling is deterministic from trace identity and a finite numerator/denominator. Buffers, batches,
export calls, flush and shutdown have finite bounds. Overflow drops newest records and increments a
local bounded health counter. Export failure never blocks the product indefinitely and never enters
business Result/Error protocols. Duplicate and out-of-order telemetry are permitted; sequence and
timestamps are observational only. Telemetry after a terminal Run is marked late and ignored by
authoritative state.
