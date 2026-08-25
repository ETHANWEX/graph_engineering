# ADR-038: Graph-backed autonomous delivery coordinator

- Status: Accepted for Phase 6D implementation
- Date: 2026-08-25

## Decision

Phase 6D composes the existing Graph Runtime rather than adding a second execution state machine.
Implementation, verification, bounded repair, fresh multidimensional Review, review-fix,
delivery, reporting and Human decisions retain durable node/attempt/checkpoint/artifact/effect
identities. Coordinator metadata records only product-stage classification and recovery claims;
the Runtime Run/node tables remain authoritative for scheduling and barriers.

Verifier acceptance failure is repairable; verifier/container/provider infrastructure error is
not. Review changes requested is bounded and requires a fresh review after verifier rerun. Review
blocked/error and uncertain delivery effects stop with distinct classifications.
