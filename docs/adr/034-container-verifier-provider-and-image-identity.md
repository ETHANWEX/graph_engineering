# ADR-034: Provider-neutral container Verifier and immutable image identity

- Status: Accepted
- Date: 2026-08-24

## Context

Container isolation must not make a Docker-specific wire format authoritative, and a mutable tag or
drifted launch configuration cannot identify frozen acceptance code.

## Decision

Register `project/container` through the existing exact-name Verifier Registry and unified
`VerifierResult`. Core sees only the existing Verifier protocol. A boundary adapter owns runtime
preflight, container argv/API details, handles, inspection, stop, and cleanup. Missing binaries,
incompatible versions, unavailable daemons, or unenforceable policies are typed infrastructure
errors; Graph Engineering never installs a runtime or changes a service.

Frozen container manifests bind registry, repository, `sha256` digest, platform, provenance,
entrypoint, declarative config, and a canonical fingerprint. Mutable tag-only references are
invalid. Exact registry/repository/digest allowlists are evaluated before any side effect, and the
frozen manifest is reverified at execution.

## Consequences

Docker-compatible implementations remain replaceable and provider payloads stay outside Core.
Changing image, platform, entrypoint, config, or provenance requires a new Verifier and Contract
revision. Deterministic fake adapters are protocol evidence, not container-isolation evidence.
