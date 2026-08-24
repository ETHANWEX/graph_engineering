# ADR-041: Reproducible local package qualification

- Status: Accepted for Phase 6E implementation
- Date: 2026-08-25

## Context

The first Phase 6E build produced byte-identical wheels but non-identical sdists. Extracted file
bytes were identical; generated PKG-INFO, setup.cfg, and egg-info tar entries and the gzip header
carried build-time timestamps. The build also warned that the legacy TOML license table is no
longer accepted metadata practice. Ignoring the sdist hash difference would falsely qualify the
required reproducible build claim.

## Decision

Keep setuptools as the declared build backend and add a narrow `sdist` command hook. When and only
when `SOURCE_DATE_EPOCH` is explicitly set, the hook normalizes release-tree timestamps and emits a
sorted gzip/tar archive with the same epoch, numeric owner identity, and empty owner names. Without
that environment variable, normal setuptools behavior is preserved. Package license metadata uses
the SPDX string `Apache-2.0`.

Package builds run from disposable source copies so historical workspace egg-info is not
overwritten. Qualification builds twice with one fixed epoch and compares SHA-256 for both wheel
and sdist. Clean Python 3.12/3.13 venvs install only the local wheel while resolving declared
runtime dependencies. Upgrade qualification starts from an exact Phase 6D delivery archive, then
force-reinstalls the current same-version development build and proves project Runtime/evidence
bytes survive upgrade, uninstall, and reinstall.

## Consequences

Phase 6E does not change package version, Runtime/IPC/MCP versions, public Schema, or migration head.
The exact Git commit and artifact hash distinguish Phase 6D and Phase 6E development builds that
both report package 0.8.0. A future published release should choose a new package version before
registry upload; Phase 6E performs no publication.
