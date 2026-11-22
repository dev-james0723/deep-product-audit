# Evidence ledger and acceptance gates

## Contents

- [Commands](#commands)
- [Gate meanings](#gate-meanings)
- [Targets and scope](#targets-and-scope)
- [Coverage and evidence](#coverage-and-evidence)
- [Finding dispositions](#finding-dispositions)
- [Source-to-runtime provenance](#source-to-runtime-provenance)
- [Complete synthetic fixture](#complete-synthetic-fixture)
- [Compatibility and limits](#compatibility-and-limits)

## Commands

Use Python 3.10+ and the standard library. Initialize one new bundle per audit/run:

```sh
python3 <skill>/scripts/audit_ledger.py init --out <new-bundle> \
  --target-kind native --target com.example.MyApp --platform macos \
  --profile advanced --environment local --audit-actor coordinator-session

python3 <skill>/scripts/audit_ledger.py validate <bundle>/audit.json
python3 <skill>/scripts/audit_ledger.py validate <bundle>/audit.json --gate audit
python3 <skill>/scripts/audit_ledger.py validate <bundle>/audit.json --strict
python3 <skill>/scripts/audit_ledger.py validate <bundle>/audit.json --gate release
python3 <skill>/scripts/audit_ledger.py report <bundle>/audit.json --out <new-report.md>
```

`init` creates schema version 2, empty coverage/findings, unknown provenance, and no
release review. It never runs the target or invents passes. Existing output paths
are never overwritten. Exit codes: `0` selected gate passed; `1` validation/gate
failed; `2` command, input, or file error. `report` returns `1` for invalid records,
but can render a valid incomplete audit. Its successful creation is not acceptance.

## Gate meanings

| Result | Meaning |
| --- | --- |
| `gates.ledger_valid` / `--gate ledger` | Schema, references, file existence, required digests, and cross-record consistency are valid. An empty draft can pass. |
| `gates.audit_complete` / `--gate audit` | Every recorded in-scope case reached an observed passed/failed outcome, failed cases have linked defect/risk records, and no required/critical case was excluded. An investigation can finish with real failures. |
| `gates.recorded_checks_passed` / `--strict` | The recorded audit is complete, all in-scope cases pass, and defects/risks have supported dispositions. Build provenance can still be unknown. |
| `gates.release_accepted` / `--gate release` | Recorded checks pass, current source/artifact/runtime provenance agrees, deployment is observed when applicable, fix retests match this build, and an independent review is recorded. This means **recorded-evidence eligibility**, not factual certification or authority to deploy. |

`acceptance.product_accepted` deliberately stays `false`: a file checker cannot
certify a product. `acceptance.release_eligible` mirrors the v2 release gate.
Treat missing access, unknown outcomes, and absent evidence as gaps. Never turn
blocked/not-tested/unknown cases into passes, delete findings, or lower their risk
to make the gate green. Establish scope and risk before executing the audit.

## Targets and scope

`scope.target` is an object with `kind` and `locator`; native/mobile also require
`platform`. A target is an identifier only, never a shell command.

| Kind | Locator | Platform |
| --- | --- | --- |
| `web` | Absolute clean HTTP(S) URL | Optional |
| `api` | Absolute clean HTTP(S) service/base URL | Optional |
| `native` | Absolute app path or bundle/package identifier | `macos`, `windows`, or `linux` |
| `cli` | Absolute executable path or executable basename, without arguments | Optional |
| `mobile` | Bundle/package identifier | `ios` or `android` |

Preserve scope fields `id`, `environment` (`local`, `staging`, `production`),
`profile` (`standard`, `advanced`), `started_at`, `roles`, and `viewports`.
Add `audit_actor` identifying the actual coordinating executor/session.
`build` is an optional human label; release proof comes from `provenance`.
Use `viewports: ["native"]` or `["not-applicable"]` when appropriate, rather than
pretending native/CLI tests used browser dimensions.

List exclusions as `scope.exclusions: [{"case_id": "C-020", "reason": "..."}]`.
An excluded coverage row must retain its ID, risk, expected behavior, and reason.
Any `required: true` or `P0`/`P1` exclusion blocks completeness and release even
when documented. Low-risk optional exclusions do not excuse undeclared scope.

## Coverage and evidence

Keep stable case IDs and define expected outcomes independently of the code under
test. Each v2 coverage row contains:

```json
{
  "id": "C-001",
  "route": "native/save",
  "role": "owner",
  "viewport": "native",
  "state": "lost-reply-retry",
  "invariant": "One operation ID causes at most one durable write",
  "expected": "The original operation result is recovered without a duplicate",
  "actual": "",
  "risk": "P1",
  "required": true,
  "observed_build": null,
  "status": "not_tested",
  "reason": "",
  "evidence": []
}
```

Statuses are `passed`, `failed`, `blocked`, `not_tested`, `unknown`, and
`out_of_scope`. Passed/failed require a nonempty `actual` and valid `runtime`,
`test`, or `log` evidence. A screenshot alone is not behavioral proof. For release,
every passed case's `observed_build` must equal `provenance.artifact.sha256`.

Every v2 evidence object requires `path`, `type`, `sha256`, `observed_at`, and
`summary`. Case, finding, root-cause, regression, and finding-review evidence also
require `case_id` within the associated record's cases. Provenance evidence uses
`subject` instead (`source`, `artifact`, `deployment`, `runtime`, or `release`).

Hash an existing file without changing the ledger or asserting execution:

```sh
python3 <skill>/scripts/audit_ledger.py evidence --bundle <bundle> \
  --path evidence/case-001.json --type test --case-id C-001 \
  --observed-at 2026-11-21T15:00:00Z --summary "Actual assertion results for C-001"
```

Supply the actual observation time. Do not manufacture it from file modification
time or the hashing command. For provenance, replace `--case-id` with `--subject`.
Allowed types: `screenshot`, `trace`, `video`, `test`, `log`, `source`, `runtime`,
`build`, `deployment`, `verification`. Paths must be relative POSIX paths inside
the bundle; traversal, escapes through symlinks, empty files, and nonregular files
are rejected. URL credentials/token-like query parameters are rejected, but this
is not a general secret scanner: sanitize evidence before copying it into a bundle.

## Finding dispositions

Retain the original finding and original evidence when fixing it. Each finding
keeps `id`, `title`, `impact`, `expected`, `actual`, `severity` (`P0`–`P3`), `kind`
(`defect`, `risk`, `suggestion`), `confidence` (`certain`, `likely`, `guessing`),
`reported_by`, `steps`, `coverage_ids`, `evidence`, and `root_cause`.
Root cause is `{status: unknown|suspected|confirmed, hypothesis, evidence}`;
confirmed causes require evidence. Start with `resolution: {"state": "open"}`.

For `resolution.state: fixed`, record:

- `fixer` and distinct `verifier`: actual sessions/people, not invented labels.
- `fixed_revision`: full 40/64-hex source revision; `verified_at`; `summary`.
- `regression.case_ids`: the one primary case identified by the comparison;
  additional adjacent regression checks remain separate coverage rows.
- `regression.record`: a full v2 `test` evidence object pointing to the actual
  comparison JSON file. Keep this file at the bundle root for standalone CLI use.
- `regression.test_definition`, `regression.oracle_definition`, and
  `regression.environment_definition`: full v2 `source` evidence objects for the
  actual immutable test, expected behavior/oracle, and controlled test environment.
- `verification_evidence`: separate `verification` record(s) covering the finding's
  cases, including the review artifact bound by the comparison. Reusing execution
  output or original finding evidence as independent review is rejected.

Use the **same comparison schema and checker** as `scripts/regression_evidence.py`
and [evaluation](evaluation.md); do not create a second before/after format. The
shared checker requires repeated executions (at least two per phase), preserved
test/oracle/environment identity, the expected assertion failing on the buggy
revision, all after runs passing, non-recycled phase evidence, and an independent
JSON review bound to the exact run records by their canonical digest.

The ledger adds these bindings to that shared comparison:

| Field | Ledger requirement |
| --- | --- |
| `case_id` | Match `regression.case_ids` and the coverage/evidence relationship. |
| `test_sha256` | Match the actual `test_definition` file digest. |
| `oracle_sha256` | Match the actual `oracle_definition` file digest. |
| `environment_id` | Exactly `sha256:<environment_definition digest>`. Record fixed runner/interpreter, configuration, fixture seed, and relevant controls in that file; record the intentionally changed product revision separately. |
| `fixed_revision` | Match the current source revision for release eligibility. The finding's historical `fixed_revision` can remain the original fix revision. |
| `fixed_artifact_sha256` | Match the current artifact for release eligibility. |
| Every run's `exit_code` | Positive integer for a before assertion failure; integer zero after. Booleans do not count as integers. |
| Every after run's `artifact_sha256` | Match `fixed_artifact_sha256`. |
| Every run's evidence | Full v2 evidence metadata with case ID, actual observation time, summary, type, real file and digest. |
| `verifier` | Match the finding's actual independent verifier. |
| Independent review JSON's `reviewed_at` | Actual review time, equal to the finding's `verified_at` and following the executions. |

The comparison's `verification` points to a separate hashed JSON record with
`kind: independent_regression_review`, the same identities and definitions,
`runs_sha256` from `regression_evidence.runs_digest(runs)`, and `verdict: confirmed`.
The shared helper validates its exact binding; the v2 ledger additionally checks
the time and includes that artifact in `verification_evidence`. The reviewer must
inspect the test, oracle, environment, and actual run outputs before writing it.
Hashing a document is not a substitute for that independent inspection.

Inspect the failure itself. Import failures, missing helpers, skipped checks,
flakiness, and unrelated setup errors do not demonstrate that a regression test
catches the product defect. Keep the test's intended assertion stable across the
before/after run. A later artifact needs a current retest even if the fix's original
revision is older. Keep previous evidence/history rather than deleting it.

Other dispositions:

| State | Required record |
| --- | --- |
| `rejected` | Distinct reviewer from `reported_by`, `reviewed_at`, `reason`, and independent `verification` evidence with content distinct from the original finding evidence. |
| `accepted_risk` | Only P2/P3; actual `owner`, `reviewer`, `reviewed_at`, `reason`, future `expires_at`, and verification evidence recording the real acceptance. It cannot turn a failed case into a pass. |
| `acknowledged` | Suggestions only; `reviewer`, `reviewed_at`, `reason`, and verification evidence. |
| `open` | Unresolved defects/risks block strict/release. Open suggestions can remain in the report without blocking functional acceptance. |

Never infer a user's acceptance of residual risk merely from an owner field. Use
the existing task authority and actual decision evidence. `fix_status` text has no
acceptance effect. Preserve historical findings instead of removing them to pass.

## Source-to-runtime provenance

Unknown stages are `null`. When populated, every stage requires `recorded_by` and
nonempty evidence with the matching `subject` and the evidence type below:

| Stage | Required identity fields | Evidence type |
| --- | --- | --- |
| `source` | `revision`: full 40/64-hex immutable revision/tree digest | `source` |
| `artifact` | `sha256`, `source_revision` matching source | `build` |
| `deployment` | `identity`, `artifact_sha256` matching artifact | `deployment` |
| `runtime` | `identity`, `artifact_sha256`, `source_revision`; `deployment_identity` for deployed targets | `runtime` |

Local/nondeployed native, CLI, or web targets need source, artifact and actual
runtime observations, but **do not invent a deployment record**. Staging/production
requires deployment plus an independent observation that the running target is
that deployment. Version labels, a successful build command, or HTTP 200 alone do
not prove this relationship. Record a binary digest or a canonical build-manifest
digest appropriate to the product; explain the manifest method in the evidence.

`release_review` starts `null`. Populate it after an independent evidence inspection:

```json
{
  "reviewer": "independent-verifier-session",
  "executor": "coordinator-session",
  "reviewed_at": "ACTUAL_TIME",
  "summary": "Explain the independent inspection and its limitations",
  "source_revision": "EXACT_CURRENT_REVISION",
  "artifact_sha256": "EXACT_ARTIFACT_DIGEST",
  "runtime_identity": "EXACT_RUNNING_INSTANCE",
  "evidence": []
}
```

This is a structural example, not a passing record. Fill real values and include
hashed `verification` evidence with `subject: release`. Reviewer must differ from
executor; executor must match `scope.audit_actor`. Review must follow all runtime,
case, provenance and finding-resolution/review observations. Merely relabeling
runtime output is not independent review. Actor identities must be canonical (no
surrounding whitespace); case variation cannot create independence, and case
variation in a hex digest cannot create new evidence.

## Complete synthetic fixture

For an isolated helper integration in a full source checkout, import the test
factory (not included in the runtime installation). It supplies a
complete native v2 JSON record and real local synthetic evidence files, including
a retained fixed finding and independent-review records:

```python
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "<source-checkout>/scripts")
sys.path.insert(0, "<source-checkout>/tests")
from test_audit_ledger import make_v2_fixture
from audit_ledger import Validator

with tempfile.TemporaryDirectory(prefix="audit-contract-") as directory:
    bundle = Path(directory)
    data = make_v2_fixture(bundle, kind="native", environment="local", with_fixed=True)
    (bundle / "audit.json").write_text(json.dumps(data, indent=2))
    result = Validator(bundle).validate(data)
    assert result["gates"]["release_accepted"] is True
    assert result["acceptance"]["product_accepted"] is False
```

The factory is **test data**, never evidence about an installed app. Do not copy
synthetic passing records into a real audit. `init` remains the production entry.

## Compatibility and limits

Version 1 ledgers retain the old integrity and `--strict` behavior, including the
conservative refusal to accept free-text fixed findings. Their release gate is
always false. For a new audit use v2 and collect current evidence; do not silently
upgrade old assertions, invent observation times, or re-label a v1 report accepted.
Use `init --schema-version 1` only for a consumer that still requires legacy data.

This validator checks structure, paths, digests, recorded identities, and declared
relationships. It cannot authenticate who produced a file, prove that log text is
true, determine undiscovered scope, inspect a running app, or make deployment
decisions. The independent verifier must inspect actual evidence contents and the
running target. Keep these limits in acceptance reports even when every gate passes.
