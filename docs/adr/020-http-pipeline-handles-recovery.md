# ADR-020: HTTP pipeline state machine and durable external handles

- Status: Accepted
- Date: 2026-08-17

## Decision

HTTP pipeline trigger, poll, report, and cancel are declarative requests. Runtime creates a stable
`run_id:node_id` idempotency key, commits trigger intent before I/O, and checkpoints the returned
handle before polling. Recovery with a handle polls and never triggers; a committed trigger intent
without a handle is an uncertain external effect and stops. Retries and exponential backoff are
bounded. Redirect targets are independently checked against the exact host allowlist.

Interrupt first commits its barrier, then attempts declared cancellation. Unsupported, failed, or
unknown cancellation is retained as an uncompensated external effect.

## Consequences

Runtime never guesses external state and never retries an ambiguous trigger.
