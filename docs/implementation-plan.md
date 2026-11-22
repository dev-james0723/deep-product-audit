# Prioritized Implementation and Verification Plan

**Target: 4.0.0-rc.1**  
**Plan date: November 21, 2026**

This plan turns the [dated research](research.md) into a portable public candidate while preserving the verified v3 baseline. One coordinator owns shared source integration, release decisions and the final evidence ledger. Independent researchers/reviewers may work in parallel; they must not become competing writers to a shared source file or GUI session.

The statuses below describe work packages and acceptance gates. Final completed counts and release state come from commit-bound QA evidence, not from this plan.

## 1. Preserve a recoverable baseline

**Priority: P0. Dependency: none.**

1. Inspect the actual installed skill and source repository, record version/commit and a file-hash manifest, and confirm source visibility.
2. Make an isolated development copy/worktree. Preserve unrelated work and all original test assertions.
3. Run the original suite with existing tooling on available platforms. Retain raw output, exact command and environment.
4. Keep the baseline unchanged for side-by-side regression and rollback.

The baseline currently has 43 manifested files and recorded 163/163 test results on both Linux and macOS. Those results do not establish Windows support or general bug-detection quality.

**Exit evidence:** source/install hash correspondence, test receipts, private visibility readback and a recoverable baseline identity.

## 2. Run and screen real recent research

**Priority: P0. Dependency: baseline identity.**

Follow the installed Last30Days instructions, prerequisites, source plan and post-engine follow-up. Pin the inclusive calendar range, retain the exact date semantics, and separate raw candidates from accepted primary reports. Do not disguise supplemental search as engine execution.

The actual run is complete: 48 candidates across Reddit, Hacker News, GitHub and YouTube; X unavailable without credentials. Its exact window, engine identity, transcript gaps and source screening appear in research.md. Three engine-derived GitHub records and 15 supplemental issue reports enter the primary matrix; historical research and anecdotes remain separately qualified.

For each accepted failure, record impact, context, source date/URL, reproduction method, oracle, clean control and evidence strength. Upstream reproduction is not part of the local synthetic run and remains not run unless separately executed.

**Exit evidence:** dated matrix, raw run receipts, explicit exclusions and a gap map against actual v3 code/guidance.

## 3. Remove owner coupling and define the portable boundary

**Priority: P0. Dependency: baseline/gap map.**

- Replace named-owner report instructions and personal-product profiles with generic report language, product archetypes and user-selected locale.
- Make agent, browser, desktop, design and graph tooling optional. Preserve fallback source/test inspection and missing-capability reporting.
- Replace the graph allowlist/home-derived guard location with explicit caller-supplied identity and independently corroborated revision checks.
- Keep Python 3.10+ standard library as the helper baseline. Git and Node are optional capability-specific requirements.
- Retain ledger schema semantics and distinct audit/release gates.

**Exit evidence:** public-file review, missing-tool smoke tests, graph freshness/identity negative tests, and no owner-specific prerequisite in the installation payload.

**Compatibility decision:** version 4 is justified by public packaging and explicit external-grader/graph interfaces. The release candidate suffix signals unresolved acceptance or rights gates; it must not imply a production release.

## 4. Implement five research-backed executable examples

**Priority: P0. Dependency: invariant definitions.**

| Module | Primary source | Before-fix requirement | Clean control | Independent check |
|---|---|---|---|---|
| Partial batch truth | S03 | Show refused item plus misleading total-success output | Fully accepted batch remains successful | Durable row changes versus per-item/aggregate outcomes |
| Fail-closed privacy parsing | S01 | Show invalid/case-variant input widening access | Legitimate explicitly public/private paths keep intended behavior | Separate observed delivery/effect records |
| Concurrent durable persistence | S04 | Force a reader into the unsafe write interval | Normal save and reads remain complete | Independent decode/content after coordinated reads and restart |
| Truncated stream | S07 | Drop response before protocol completion after partial content | Permitted completed stream remains successful | Protocol terminal/length/status evidence |
| Required job completeness | S08 | Skipped/missing required jobs yield a false all-pass result | All required jobs pass; optional exclusions remain explicit | Frozen required IDs and raw job conclusions |

Use `scripts/behavior_lab.py` and its tests. Keep the generated environment disposable, bounded and separate from production. Record the same assertion/oracle hashes on both implementations. The target is five expected seeded failures, five clean controls and all corrected checks passing; report observed counts only after execution.

**Exit evidence:** real before/after receipts, correct intended assertion failures, unchanged controls, independent review, no mock/provider claim confusion.

This additive lab does not automate every matrix row. Other domains remain actionable project checks using existing runners and guidance.

## 5. Preserve the existing audit machinery

**Priority: P0. Dependency: portable boundary and module integration.**

Run original tests against the candidate with only necessary path/interface adaptations. Review their diffs so a green result cannot be achieved by removing assertions, turning required cases optional, mocking the target or changing the expected invariant.

Retain the known 6/6 public demo, network lab, ledger, scope critic, regression evaluator, release observer and trigger scorer. Keep local helper tests, fixture detection, agent discovery, product execution and release acceptance as separate outcomes.

**Exit evidence:** exact original/new test counts, failures/skips with reasons, baseline-to-candidate diff review and bounded lab receipts.

## 6. Separate educational fixtures from private evaluation

**Priority: P0. Dependency: packaging design.**

Remove the inherited answer manifest from the public core. Require `--manifest` to be supplied explicitly to grading operations. Keep held-out material outside both the public repository and the evaluated agent's accessible runtime.

Build the runtime install from an allowlist that excludes tests, public toy demonstrations and evaluator-only material where they are not needed. Keep the known public demonstrations available in the developer repository, clearly labeled as educational checks.

Test missing-manifest failure and install-payload exclusion. Document that a sibling directory is not sufficient isolation when the agent has filesystem access to it.

**Exit evidence:** package manifest, negative install/grader tests, no answer-key leakage, and no blind benchmark claim using known public cases.

## 7. Add installation, uninstall and rollback

**Priority: P1. Dependency: final public payload layout.**

- Support explicit user-chosen installation destinations without a particular agent's home directory.
- Refuse unsafe destinations and unexpected overwrite.
- Write a manifest with version, relative path and digest for owned files.
- On uninstall, remove only recognized unchanged owned files; preserve modifications and unrelated contents.
- Test fresh install, repeated/error scenarios, paths with spaces/non-ASCII text and rollback to the preceding accepted package.
- Add English human/agent examples, prerequisites, README, SECURITY.md, CONTRIBUTING.md, changelog and attribution information.

**Exit evidence:** fresh-environment install/readback/uninstall receipts and safe modified-file/rollback controls.

## 8. Independent QA and platform verification

**Priority: P0 for release. Dependency: frozen candidate.**

Freeze a candidate commit/artifact. Give a fresh reviewer raw changes, requirements and evidence, not an intended verdict. Ask them to refute both correctness and coverage: unreachable defects, setup mismatch, accidental behavior changes, missing controls, self-certifying results, weak timeouts, filesystem escape, misleading platform claims and release leakage.

Resolve findings with a concrete reproduction and unchanged regression. Repeat only the affected verification and required gates after a change. Record reviewer identity/scope and whether isolation is actually established.

| Platform/lane | Required evidence | Allowed claim before execution |
|---|---|---|
| Linux | Native core suite, labs, fresh install and bounded subprocess behavior | Baseline verified; candidate result pending |
| macOS | Same candidate identity, native core suite/labs/install and path behavior | Baseline verified; candidate result pending |
| Windows | Native process/filesystem/symlink and installation behavior | **Not tested; provisional target only** |
| Browser/native UI | Actual chosen runtime/device, real input and independent result | Not established by Python unit tests |
| Agent invocation | Actual host loading/running records | Not established by skill metadata |
| Performance/model comparison | Frozen matched trials and independent grading | Unmeasured |

**Exit evidence:** exact platform versions, test counts, failures/blocks/untested scope, resolved review findings and final candidate hashes.

## 9. Privacy, security and redistribution gate

**Priority: P0 blocking publication. Dependency: frozen candidate and source provenance.**

Build a separate clean Git repository containing only this skill's reviewed public files. Never make the original private skills repository public or copy its history.

Scan the proposed tree, archives and every reachable public-history object for secrets, personal metadata, internal paths, private code and grading material. Include synthetic markers and history-only leaks as scanner negative tests. Use the scanner as assistance; independently review all findings and files.

Inspect licensing/authorship provenance and third-party inclusion rights. No inherited LICENSE file means permission must be established from provenance or rightsholder authorization, not guessed. Adding a permissive license text cannot supply missing rights.

Keep evidence with machine/account metadata private. Public documents may link to third-party public issues and summarize observations without copying private logs, credentials or whole source files.

**Exit evidence:** reviewer dispositions, exact scan scope, no unresolved blocking findings, confirmed redistribution rights, attribution and source-private readback.

**If unresolved:** retain the verified candidate as implemented but unreleased, identify the exact rights/privacy blocker, and stop before irreversible publication.

## 10. Publish if safe, then independently read back

**Priority: P0 final acceptance. Dependency: every blocking gate resolved.**

1. Create/use a separate clean public repository under existing publication authority.
2. Publish only the reviewed commit/artifact.
3. Record the exact URL, commit, package digest and version.
4. Independently fetch through a public unauthenticated path and compare the actual file manifest.
5. Install/smoke-test from the read-back bytes, not merely the developer checkout.
6. Recheck original source repository visibility.

If public readback is unavailable or mismatched, report Published without verified readback, or Blocked, as appropriate. Do not claim Published and Read Back from a successful push response.

## Final evidence register

The final report must separately list:

- **Verified:** observed baseline/candidate behavior with evidence.
- **Implemented but Unreleased:** changes exist and are verified within stated limits, but release has not occurred.
- **Published and Read Back:** exact public commit independently fetched and checked.
- **Blocked:** named missing capability, permission, right or failing gate.
- **Not Tested:** unsupported platform/runtime/agent/provider cases and empirical comparisons.

Include exact test and lab counts, before-fix intended failures, unchanged assertion/oracle hashes, clean controls, independent review results, platform gaps, install/rollback receipts, privacy/license decisions and source visibility. Archive all candidate hashes and the rollback identity. Passing a test summary is one part of this evidence, not its conclusion.

