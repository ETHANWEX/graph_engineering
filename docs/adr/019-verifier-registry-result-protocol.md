# ADR-019: Verifier Registry, SDK, and unified result protocol

- Status: Accepted
- Date: 2026-08-17

## Decision

Core exposes a provider-neutral Verifier protocol and immutable request/outcome types. Registry
keys are exact type names and duplicate registration or unknown lookup fails closed.
`builtin/command` remains compatible; `builtin/http-pipeline` and `project/subprocess` use the same
public Schema 1.0 `VerifierResult`. Only `failed` represents an acceptance failure eligible for
repair. `error` represents verifier/infrastructure failure and `cancelled` represents cancellation.

## Consequences

Provider JSONL, HTTP wire payloads, and subprocess wire payloads stay inside adapters/verifiers.
