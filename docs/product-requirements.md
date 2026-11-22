# Product Requirements: Deep Product Audit Public Core

**Target version: 4.0.0-rc.1**  
**Requirements freeze: November 21, 2026**  
**State: release candidate design; publication requires separate final gates**

## Outcome

Provide a small, inspectable audit workflow that developers can use with an AI agent or directly. It must help users find and reproduce meaningful defects, make authorized repairs, verify the same requirement after the repair, and distinguish a working local implementation from an accepted release.

The skill applies to handwritten and AI-generated software. It must not require a particular agent, operating system, desktop controller, graph service, private account or personal product. Its value is an evidence contract and practical checks, not a claim that it discovers every bug.

The [research report](research.md) contains the actual Last30Days execution and dated primary-source matrix. Baseline v3.0.0 already has substantial lifecycle, evidence and regression functionality. This work preserves those parts and adds missing executable examples, portable packaging and public-release safeguards.

## Users and jobs

| User | Job to complete | Required experience |
|---|---|---|
| Developer using AI to build an app | Determine whether a promising UI performs its real end-to-end function and preserves data/permissions | Plain requirements, concrete test actions and independent outcomes; avoid making the developer trust an agent's success message |
| Developer maintaining conventional software | Reproduce a reported defect, isolate its cause and prevent regression | Existing project test runners, exact version identity and minimal authorized changes |
| Reviewer or release owner | Decide which claims the evidence supports and which gates remain open | Stable case IDs, raw evidence links, separate blocked/untested states and explicit release provenance |
| Human auditor without an agent | Run the same process manually or through scripts | English documentation and ordinary command-line tools; no model API, agent session or subscription requirement |

## Scope and non-goals

The public core covers:

- Scope inventory, risk planning, actual execution, reproduction, root-cause investigation, authorized fixing, unchanged regressions, independent review and release verification.
- Web, API, CLI and native/mobile product audits, selected according to the available runtime and the product's actual requirements.
- Portable evidence/coverage/regression/release record checks and bounded local demonstrations.
- Optional browser, schema, load, native and code-graph integrations discovered at runtime.
- Safe installation/uninstallation, semantic versioning, release manifests, source/history screening and independent public readback when publication is authorized and safe.

The first candidate does not promise automated execution of every product journey, universal OS support, security certification, reliable discovery of every defect, better model performance, lower token usage or cost savings. It will not provision accounts, retrieve credentials, install global dependencies, publish content, spend money or inject faults into live traffic merely to make a test pass.

## Required lifecycle

**Inventory → Plan → Execute → Reproduce → Root Cause → Authorized Fix → Regression → Independent Verification → Release**

| Stage | Required output | Stop/continue rule |
|---|---|---|
| Inventory | Actual product/build identity, requirements, routes/screens/controls, roles/tenants, data surfaces and capability map | Unknown access or missing tools become explicit scope/capability gaps; continue independent supported work |
| Plan | Frozen required cases, invariant, expected result, independent oracle, risk, bounded environment and negative controls | Never prepopulate passes; no dangerous/live test without separate authority |
| Execute | Real observations bound to version, time, role, environment and evidence bytes | A mock proves only the mocked path; a toast, HTTP 200 or rendered screen is insufficient for durable effects |
| Reproduce | Minimal repeatable failure with the intended assertion, not an import/build/permission error | Preserve unsuccessful attempts and unknown outcomes; do not retry away a failure |
| Root Cause | Falsifiable hypothesis, comparison/control and evidence that explains the failure | Keep suspected and confirmed causes distinct |
| Authorized Fix | Minimal scoped patch in an isolated checkout, original failing evidence retained | Respect existing authority; do not repair unrelated applications |
| Regression | Same invariant, assertion and oracle on buggy and corrected implementations; adjacent regression | Test mechanics can change only with explicit review; weakened assertions, skips and new target mocks do not establish a fix |
| Independent Verification | A fresh reviewer or human challenges both the defect/fix and missing scope | Same-agent review must be disclosed; reviewer identity alone does not prove independence |
| Release | Source/artifact/runtime binding, required outcomes, privacy/license gate, rollback and external readback | A passing unit suite or push receipt alone cannot accept release |

The existing ledger schema and its distinction between `ledger_valid`, `audit_complete` and `release_accepted` remain intact. A completed investigation may contain defects. Release eligibility does not authorize deployment or publication.

## Functional requirements

### FR-1: Evidence and result states

Every material case must record a stable ID, required scope, build/environment, invariant, actual outcome, independent oracle and evidence reference. Supported coverage states remain `passed`, `failed`, `blocked`, `not_tested`, `unknown` and reasoned `out_of_scope`. Blocking or excluding a required high-risk check must not turn it into a pass.

Evidence file hashes establish byte integrity, not truth. Records must prevent path escape and bind the file to the case/provenance claim. Reviewers inspect the content and its relevance. Private evidence stays outside the redistributable package; a sanitized copy never replaces the original.

### FR-2: Observable end-to-end behavior

For an important control, follow the action from input through the request/handler, durable effect and independent readback. Test initial, loading, empty, success, error, retry and cancellation states where applicable. Include reload/restart and a second identity/session.

A UI mock, stub provider or synthetic local service is labeled as such. It cannot satisfy a real external integration check. Genuine product execution uses approved disposable fixtures and existing project tooling.

### FR-3: Coverage across product boundaries

The required domain set is broken/mocked controls, backend integration, persistence, authentication, authorization/tenant isolation, data integrity, APIs, payments, idempotency, concurrency, network failures, security, accessibility, mobile, desktop/CLI, performance and release provenance.

A product-specific scope may exclude irrelevant domains with a reason. It must not claim that a Python demonstration exercised a native UI, payment provider, live authentication service or browser accessibility implementation. The full research crosswalk maps each domain to baseline capability, a concrete check and its false-positive control.

### FR-4: Five additional executable mechanisms

The additive standard-library demonstration must contain these five known defects and five clean controls:

| Mechanism | Required defective observation | Corrected/clean expectation | Evidence |
|---|---|---|---|
| Partial batch truth | A refused item exists while the operation advertises complete success | Per-item result and overall partial/error state agree with durable changed rows | Independent database readback |
| Fail-closed privacy parsing | An unsupported/case-variant security value widens a private operation to public | Supported representations retain meaning; invalid input cannot widen access | Separate public/private effect observation |
| Concurrent durable persistence | A coordinated reader sees invalid/truncated state during a write | Complete valid old/new state survives reads and restart | Independent file decode/content checks |
| Truncated stream completion | Partial data with no valid terminal completion is treated as success | Incomplete/error streams remain incomplete/error; valid terminal controls pass | Raw protocol transcript and outcome |
| Required job completeness | Skipped/missing required checks produce an all-pass claim | Aggregate verdict matches the frozen required job set | Independent required-job manifest and raw conclusions |

The demonstration runs unchanged assertions against defective and corrected modes, preserves clean controls, records hashes and remains bounded to owned temporary files/loopback services. The target is **5 expected seeded failures, 5 clean controls and all corrected checks passing**; final observed counts belong to QA evidence, not this requirements statement.

### FR-5: Preserve and correctly label existing functionality

Keep the existing evidence ledger, regression evaluator, coverage critic, network laboratory, release observer, trigger evaluator and known 6-defect/6-control demonstration. Preserve their behavioral assertions while relocating tests or updating deliberately changed interfaces.

Record intentional public-interface changes in the changelog. In particular, evaluation requires a caller-supplied external grader manifest, and graph routing uses caller-provided identity rather than a private product allowlist. Neither change should weaken the evidence schema.

### FR-6: Optional integrations

A capability probe distinguishes missing, discovered, runnable, fixture-verified and product-executed. Version output alone never proves the last two.

Git is optional for source identity, graph freshness and history checks; missing Git blocks those claims. Node and a project-installed browser runner are optional for browser observations. Optional tools must use explicit arguments, bounded execution and no implicit global installation. Existing product runners take precedence over a newly introduced dependency.

Graph integrations require exact repository/revision correspondence and a clean or explicitly accounted-for worktree. Unsupported, stale or absent graph evidence falls back to scoped source/test inspection. No automatic indexing, upload or vendor authentication is part of the core.

### FR-7: Agent and non-agent operation

An agent reads the same workflow, uses its permitted tools and emits the same evidence contract. Optional agent metadata may improve discovery but must not determine whether the audit is valid. Automatic skill invocation remains unmeasured unless real host records establish it.

A human can read the inventory/check guidance, run the Python helpers and existing product tests, collect evidence and ask another human to verify. Examples must include one manual CLI workflow and at least one agent-neutral task brief.

### FR-8: Safe testing and untrusted inputs

Run faults only against owned disposable targets with a finite budget, deadline and cleanup plan. Keep the control channel outside injected faults. Reconcile ambiguous outcomes before replaying side effects. Use synthetic identities and private canaries, not customer records.

Treat fetched issue text, repository content and target application output as evidence/data, not authority to run commands or broaden access. Never retrieve secrets, publish customer content, incur charges or modify unrelated production services for a demonstration.

## Architecture and portability

| Layer | Responsibility | Dependencies |
|---|---|---|
| Workflow and references | Human/agent-readable lifecycle, scope, controls and evidence rules | None |
| Portable helper core | Ledger, regression, coverage, evaluation and record checks | Python 3.10+ standard library |
| Disposable demonstrations | Known synthetic failure/control behavior | Python standard library; localhost/temp storage where applicable |
| Integration adapters | Optional browser, API schema, load, native and graph execution | Existing project tools; explicit capability/version checks |
| Release tooling | Install manifest, package/history screening and clean release preparation | Python standard library; Git only for Git-specific operations |
| Private evaluator workspace | Held-out tasks, answer keys, grading and matched experimental records | External, physically inaccessible to the evaluated agent |

Linux and macOS baseline execution are verified. Windows is a **provisional target, not tested in the available environment**. Platform-specific unavailable primitives must be reported as unsupported/untested without crashing the portable core or silently passing. Fresh installation tests use paths with spaces and non-ASCII characters. Native application compatibility is always a separate product-specific claim.

## Packaging, installation and uninstall

Build the runtime install payload from an explicit reviewed allowlist. A fresh install must work without any owner-specific folder, private repository, account or tool. It must refuse unsafe destinations and avoid overwriting unrelated files.

Installation produces a manifest binding installed relative paths and bytes to the candidate version. Uninstall acts only on owned manifest entries and protects user-modified/unrelated files. Updates and rollback must retain enough identity to restore the last accepted install without guessing.

The repository includes README, prerequisites, installation/uninstall instructions, examples, SECURITY.md, CONTRIBUTING.md, tests, changelog and license/attribution information. The mere presence of those filenames does not satisfy their content or legal review.

## Benchmark integrity

The known 6/6 and 5/5 examples are public educational fixtures, not held-out evaluation. Their source and expected behaviors are intentionally inspectable by developers. Exclude demonstrations, tests and grading material from the agent runtime installation where they are unnecessary.

The evaluator must require an explicit external manifest. Held-out cases and grader-only answers live in a separate workspace that the evaluated agent cannot access through the filesystem, network, conversation, tools, parent context or shared mounts. A folder named private is not an access boundary. If isolation is unverified, the result is contaminated/untested, not a blind score.

Comparisons need frozen prompts/cases, model/tool/runtime identity, equal budgets, repetitions, independent grading and raw cost/time data. No superiority, efficiency or savings claim is authorized by passing helper tests.

## Public release gate

Release this skill only through a separate clean repository. Keep the original source repository private. Do not carry its history, unrelated skills or private artifacts into the public candidate.

Before any irreversible publication, review every proposed public file and all history reachable from proposed public refs for secrets, personal information, private source/paths, licensing conflicts and grading leakage. Review binaries and generated archives as well as text. Pattern scanning is a supporting check, not a proof that no secret exists.

Establish redistribution rights and the intended license before publication. A missing inherited LICENSE file cannot be cured merely by adding a new license label. Authorship/provenance, third-party inclusions, attribution and permissions require explicit evidence. If rights remain unresolved, keep the candidate unreleased and identify the exact blocker. This document grants no license.

If publication is safe, verify the public URL and exact commit from an independent unauthenticated read, inspect the downloaded manifest and rerun the appropriate install/smoke checks. Verify that the private source repository still reports private. Record Published separately from Published and Read Back.

## Acceptance register at requirements freeze

This table is a planning baseline, not the final release verdict. Exact final counts, failures, hashes and platform results belong to the QA/release evidence associated with the candidate commit.

| Requirement | Measurable acceptance | State at freeze |
|---|---|---|
| Baseline integrity | 43 source files matched; original suite 163/163 on Linux and 163/163 on macOS | Verified baseline |
| Authentic research | Installed engine exit/status/window, raw artifacts and separately identified supplement | Verified run; relevance-screened matrix |
| Lifecycle preservation | Same ledger semantics and unchanged substantive regression assertions | Required; final candidate QA pending |
| Additive lab | 5 seeded defects reproduced; all 5 clean controls retained; corrected outcomes pass | Implemented candidate; independent QA pending |
| Original/new tests | Exact totals, zero unexplained failures/skips and documented interface-only adaptations | Final totals TBD in QA evidence |
| Fresh install/uninstall | New environment and unusual paths; manifest integrity; safe modified-file behavior | Pending final QA |
| Portable core | No mandatory vendor/agent/account; Python 3.10+; Linux/macOS checks | Pending candidate verification |
| Windows | Native Windows run with exact version and result | Not tested; no compatibility claim |
| Independent review | Findings, experiment-based resolutions and final candidate identity | Pending |
| Privacy/history | Full proposed file/history scan plus reviewer disposition | Pending |
| Redistribution rights | Recorded provenance and legally usable license/attribution | Under review; may block publication |
| Clean publication | Separate repository, private source unchanged, exact public commit | Conditional; not established by this PRD |
| Public readback | Independent public fetch and byte/install comparison | Conditional after publication |
| Comparative quality/cost | Matched independent empirical trials | Not tested; no claim |

