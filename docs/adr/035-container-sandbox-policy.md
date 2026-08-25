# ADR-035: Fail-closed container resource, mount, network, and secret policy

- Status: Accepted
- Date: 2026-08-24

## Decision

Every container execution declares finite CPU, memory, PID, wall-clock, output, Artifact, and
concurrency limits. Output is consumed as bounded chunks and redacted before Artifact persistence.
Mount sources are relative to explicitly authorized roots, re-resolved immediately before start,
and rejected on traversal, absolute escape, symlink, junction, or reparse traversal. Frozen control,
Verifier, acceptance-lock, and evidence mounts are read-only; writable mounts are explicit and
minimal. Docker sockets, credential/home mounts, and host system paths are prohibited.

Networking defaults to none. Enabled networking is an exact protocol/host/port policy frozen in the
Manifest and Human permission summary. It may run only through an adapter that proves enforcement
of DNS resolution, redirects, proxies, and custom-host mapping; otherwise it fails closed.

Secrets remain reference names in frozen data. Values are resolved only for an ephemeral adapter
request, never placed in image/entrypoint/command identity, and raw, URL-encoded, base64, overlapping,
or cross-chunk variants are redacted before logs, errors, events, Artifacts, checkpoints, or reports.

## Consequences

Some Docker-compatible runtimes can safely run only `network=none` until a stronger network-policy
adapter is configured. Unsupported isolation is an infrastructure error, never silently weakened.
