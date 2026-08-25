# Phase 6G Project UI Compatibility

- UI/API contract: 1.0; optional additive presentation boundary.
- Product/package: 0.8.0; Python `>=3.12,<3.14`; no new dependency.
- Runtime API / IPC / MCP / Plugin: 1.0 / 1.0 / 1.0 / 0.1.0.
- SQLite migration head: 10; no table, column, view or migration change.
- Public JSON Schema: 36; no Core model/export change.

UI absence preserves all existing behavior. Additive read-only snapshot operations do not change
existing request meanings; incompatible/old servers reject them as unsupported. UI mutations reuse
existing Gateway operations and idempotency ledger. Historical Runs and migrations 1–10 remain
readable. The dependency-free CSS/JavaScript assets are included as package data and require no
network/CDN or browser storage. Browser automation,
external hosting and Linux/macOS UI qualification remain explicitly unverified.
