## Unreleased — local CI acceptance follow-up

- Add local, offline-at-test-time macOS and Linux ARM64 test runners and explicit evidence aggregation.
- Keep Windows native and model-effectiveness benchmarks explicitly untested pending direct verification.
- Document isolated Docker image preparation; remove broken hosted Actions workflow from the QA branch.

# Changelog

## 4.0.0-rc.1 — 2026-11-21

### Changed

- Split the reusable public core from owner-specific language, product profiles,
  host workspace conventions and implicit graph-guard paths.
- Require an explicit graph identifier and authorized guard for optional graph
  routing; support arbitrary safe identifiers and preserve revision/cleanliness checks.
- Require `evaluate_audit.py --manifest` explicitly. The private legacy answer
  manifest is not distributed. This is an intentional breaking CLI change.
- Keep developer demonstrations and tests outside the runtime package using a
  versioned allowlist. Public demos are known examples, not held-out evaluations.
- Preserve ledger schema v2 and the distinction between integrity, completed
  investigation and release acceptance.

### Added

- Dated Last30Days research, primary-source pain-point matrix, public requirements
  and prioritized implementation plan.
- Five executable known defect/control pairs for partial batch success,
  security-sensitive parsing, concurrent file persistence, truncated streams and
  skipped required CI jobs. The CI case checks offline records, not a live pipeline.
- Deterministic runtime packaging, explicit installation, conservative verification
  and uninstall, privacy/history screening, fresh-environment checks, license and
  contribution/security documentation.
- A regression for arbitrary graph identifiers and an independent resource
  lifecycle regression for every SQLite connection in the new demonstration.

### Fixed during independent review

- Close SQLite connections explicitly after transactions in the new demonstration;
  connection context management alone did not close them. Preserve the unchanged
  reviewer regression and before/after evidence.

### Limits

- Exact validated environments, test counts and remaining issues are in `docs/qa.md`.
- Windows runtime, real-product audits and matched agent-performance trials are not
  established by this release. No superiority, cost or token-saving claims.

## 3.0.0 — inspected baseline

The original baseline contains 43 files, a v2 evidence ledger, coverage critic,
conditional graph routing, release-record checks, 163 local contract tests and
a six-defect/six-clean-control synthetic fixture. The current work independently
reran the tests and verified source/installed file identity before editing.
