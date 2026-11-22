# Follow-up verification — 2026-11-21

This report describes checks **after** the public 4.0.0-rc.1 tag was frozen. Work in the `qa/windows-py310-acceptance` branch is *not part of that published tag*, and must not be represented as a released version until independently accepted.

## Rechecked

- macOS ARM64, CPython **3.10.16**, **3.11.11**, **3.12.8**, and **3.15.2**: the expanded **233-test suite passed on each interpreter** with 0 errors/failures on successful runs.
- The 233 comprise the original 231 plus **two** new dependency-free safety tests for the optional third-party probe: HTTP redirects cannot leave loopback and a vendor subprocess cannot inherit personal API credentials.
- One **first-run failure** of the inherited `test_report_renders_history_and_never_overwrites` occurred during a full 3.10.16 run (233 tests, 1 failure). The exact failed log was preserved outside the public source under `qa-final-310.log`, including the assertion `report exit 1 != expected 0`. The same test then passed in isolation, the full suite passed on rerun, and **65 standalone fixture repetitions** produced 0 further failures. Root cause **not established**; classify as a possible intermittent test/evidence-validation issue, **not repaired**. The successful rerun does not erase the failure. Preserve the original assertion.
- The three disposable runtime laboratories, package, install, verification and conservative uninstall passed on 3.10 and 3.15. All measured runtime archive SHA-256 values match the frozen release bundle.
- The isolated platform smoke includes a negative uninstall control: an unowned file must block removal while preserving that file.
- Known synthetic URL-credential scanner findings are accepted **only** when the underlying original fixture matches a separately reviewed SHA-256. Additional findings or fixture changes fail the smoke pending renewed human review.
- macOS ARM64, official PocketBase **v0.40.6** (vendor asset SHA-256 `7f2f7544e9ee5994ab69f84b22a4ab9a3bcfed58c1dad7206d05ebeb753f968b`): **13/13** black-box checks passed in repeated runs, including under Python 3.10 with independent server and read-only SQLite state. This is a real unmodified third-party backend, not a discovered vendor defect; see [sanitized evidence](qa-artifacts/pocketbase-blackbox-2026-11-21.json) and [reproduction](../examples/README.md).
- Codex app-server `skills/list`: one enabled `deep-product-audit` entry discovered from an isolated, freshly installed runtime using a temporary `CODEX_HOME`. No model request, token billing, existing host registration or production account modification was involved. [Reproducible offline probe](../examples/codex_discovery_probe.py) and [sanitized receipt](qa-artifacts/codex-discovery-2026-11-21.json) are provided. This does **not** show that existing live Codex/Claude sessions have switched to v4.

## Native CI blocker

A least-privilege hosted CI matrix was created for `ubuntu-24.04`, `windows-2025` and `macos-15`, at Python 3.10 and 3.12. However, **all six jobs were refused before runner startup**. GitHub reported an account-level billing lock. No native Windows result can be claimed from this run. The matrix includes no secrets and runs only standard public-repository hosted runners.

- [Blocked run](https://github.com/dev-james0723/deep-product-audit/actions/runs/44971972371)
- Follow-up action: have the account owner resolve hosted-runner eligibility, then rerun the matrix, inspect individual job logs and receipts, and obtain independent Windows readback. Do not merge or tag a version claiming Windows verified before that evidence exists.

## Scope limits

Known-answer teaching fixtures and one third-party clean-control backend do not constitute a matched agent-performance experiment. No Windows runtime, real external payment provider, public customer environment, actual production defect or hidden-grader trial was exercised. No general detection superiority, speed, cost or token-use claims are supported.

The original private skill repository and existing v3 host skill registration remain untouched. This branch is isolated; 4.0.0-rc.1 remains the immutable release baseline.
