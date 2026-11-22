# Coverage and evidence

## Inventory

Map requirements, route definitions, menus, real UI, and integrations, including unlinked and role-restricted screens. Record inventory source/revision. Distinguish enumerated controls from exercised behavior.

For important items record route/screen, control/journey, role/tenant, state, platform/viewport, invariant, risk, expected/observed outcome, independent oracle, status and stable ID. Record required scope and inventory source before execution. Group equivalent combinations only with a rationale. Never silently pass or remove untested/failed combinations.

| Dimension | Examples |
| --- | --- |
| Navigation | Deep link, back/forward, refresh, redirect, not-found, context |
| Actions | Valid/invalid input, duplicate submit, cancel/undo, disabled/loading |
| Data | Persistence, stale cache, concurrent edit, retry, pagination, search/filter/export |
| States | Empty, loading, populated, offline, timeout, partial failure, recovery |
| Settings | Defaults, save/reload, dependent settings, fixture-scoped reset |
| Access | Anonymous/user/admin, tenant boundaries, direct route, server enforcement |
| Integrations | Missing setup, revoked/expired access, rate limit, upstream error, real result |
| Layout | Breakpoints, overflow, clipping, dialog, touch, keyboard, focus, zoom |
| Content | Long text, locale, units/dates, validation wording, accessible names |
| Delivery | Source, artifact, deployed revision, environment, observed behavior |

Choose combinations based on product/risk and state exclusions. A checklist alone never proves every feature works.

## Status and severity

Coverage: passed, failed, blocked, not_tested, unknown, out_of_scope. Failed behavior needs reproduction. Blocked/unknown/out-of-scope needs a reason. Unknown outcome after a timeout is not equivalent to failed operation. Finding kinds: defect, risk, suggestion. Excluding an important required case cannot satisfy release acceptance.

- P0: demonstrated critical data exposure/loss or total critical-service failure.
- P1: important journey unusable/substantially wrong without practical workaround.
- P2: meaningful issue with workaround or limited reach.
- P3: small usability/visual defect.

Use observed reach, frequency, impact, and recovery. Hypothetical risks are not demonstrated incidents; aesthetic preferences are not automatically defects.

## Evidence

Bind claims to environment, role, build, viewport, and time. Keep original evidence in the task's private bundle; use relative paths. Preserve originals if making redacted shareable copies. Never log passwords, tokens, cookies, full authorization headers, or private network bodies. Screenshots/traces may contain private data: capture relevant test accounts/windows, review before sharing, and keep traces local unless sharing is authorized.

Behavior claims require runtime/test/log evidence. For visual defects include a screenshot plus a runtime observation of the rendered condition/viewport. File existence/hashes establish integrity, not truth; inspect the content and its relationship to the claim.

Use ledger CLI help and [evidence-ledger.md](evidence-ledger.md) for the current schema. New v2 evidence requires a SHA-256, timestamp, meaningful summary and case binding where applicable. Legacy v1 records remain readable with their original limitations. Do not relabel source excerpts as runtime evidence to satisfy validation.

## Completion

An investigation may be reported with findings or incomplete coverage. `audit_complete` requires conclusive outcomes for the required recorded scope; a completed investigation can still contain real defects. `release_accepted` additionally requires passing applicable outcomes, supported dispositions and exact provenance. Preserve original findings and owner decisions; a risk waiver is never an invented pass and the helper's conservative release rules may still reject it. File validity, audit completeness and release eligibility are distinct.
