# Phase 4: Dynamic Verifiers

## Scope

Phase 4 adds a provider-neutral Verifier Registry and SDK, declarative HTTP pipeline verification,
an argv-only structured subprocess protocol, capability and secret policy, append-only Verifier
revisions, and Runtime recovery/cancellation of external handles. Discovery prefers declarative
configuration and uses Codex only when project code is required. Generated bundles contain a
Manifest, implementation, fixtures, and tests and must pass schema validation, policy validation,
tests, dry-run, Human permission review, and freeze before execution.

SQLite migration 5 stores Verifier revisions, lifecycle evidence, Contract bindings, and external
handle cancellation/report metadata. Raw logs and reports remain content-addressed Artifacts.

## Non-scope

No GitHub-specific integration, PR mutation, auto-merge, Phase 5 review/delivery, Claude adapter,
plugin/UI, daemon, parallel graph, containers, telemetry, arbitrary shell strings, expression
evaluation, production CI calls, or dangerous Codex sandbox bypass is included.

## Acceptance criteria

- Registry registration is deterministic and rejects duplicates and unknown types.
- Unified results preserve pending/passed/failed/error/cancelled semantics.
- HTTP trigger is idempotent, checkpointed before polling, recoverable without retrigger, bounded,
  redirect-safe, cancellable when declared, and able to retain redacted reports/evidence.
- Project subprocess Verifiers use argv plus JSON stdin/stdout, enforce timeout/output/schema
  limits, and separate acceptance failure from infrastructure error.
- Network is denied by default, hosts are exact allowlist entries, filesystem paths are bounded,
  and Runtime injects only declared secret references and capabilities.
- Secret values and supported encodings are redacted before exceptions, events, prompts, Artifacts,
  and reports are persisted.
- validate/test/dry-run/Human permission summary precede append-only freeze. Frozen Manifest,
  source, tests, and fixtures hashes are checked before any side effect.
- A new Verifier revision requires a new Contract revision; query operations remain read-only.
- Pause/interrupt barriers persist before new HTTP/subprocess work; interrupt attempts cancellation
  and explicitly records unsupported or uncertain residual effects.
- Phase 0-3 protocol, tests, schema, CLI, and real-Codex evidence remain valid.
