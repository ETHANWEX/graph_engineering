# ADR-026: GitHub provider identity, Checks, and Pull Request effects

- Status: Accepted
- Date: 2026-08-18

## Decision

GitHub is an adapter boundary with exact owner/name/API-host identity. Checks are read-only and
accepted only for the requested commit; unknown states never become success. Authentication,
rate-limit, network, API, identity, and code conclusions remain distinct. Polling is bounded and
honors provider retry headers.

PR creation uses a stable Run/repository/base/head key. Runtime checkpoints intent before POST and
the returned number/URL/node ID immediately after success. Recovery first uses a saved handle, then
an exact head/base discovery; ambiguous POST outcomes stop without blind retry. Updates revalidate
ownership and a persisted barrier immediately before I/O. Query/report never writes and no merge
operation exists.

## Consequences

Redirect destinations are revalidated and tokens exist only in transient authorization headers.
Real writes require explicit repository authorization; fixtures remain labelled deterministic.
