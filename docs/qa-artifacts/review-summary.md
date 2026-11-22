# Independent review of Deep Product Audit 4.0.0-rc.1

## Review result

[Certain] **No unresolved confirmed blocker remains in the reviewed source files at the hashes recorded below.** Six core-code findings and five package/scanner findings were reproduced, repaired by the implementation author, and independently reverified. The original assertion expressions were retained, and the independent regression tests used for the repairs were unchanged across their failing and passing runs.

This is a review of known public code, performed with disposable local fixtures. It measures code and fixture behavior. Agent-performance evaluation was not executed, and external products were not tested.

## Confirmed findings and final disposition

| ID | Initial failure | Repair verified |
| --- | --- | --- |
| CORE-01 | The behavioral demo left 27 of 27 SQLite connections open after teardown. Garbage collection could hide the leak on some runs. | Every connection is now explicitly closed. The same cross-platform test holds strong references and verifies that every connection rejects `SELECT 1` after teardown. |
| CORE-02 | Repeating one independently judged finding under a second ID increased verified closures from one to two for the same defect. | Verified closures are counted once per case/defect; repeated verified claims have a separate duplicate counter. The paired comparison no longer reports a fabricated closure gain. |
| CORE-03 | Changing the atomic fixture's expected input left its claimed check digest unchanged. | The digest now covers the database and stream input functions, observation and scheduling helpers, case selection and timeout. An unchanged test verifies that changing the atomic expected input changes the digest. |
| CORE-04 | The corrected stream consumer accepted a numeric `done: 1` as boolean success. | Completion requires the actual boolean `true`. Numeric, string, absent and other non-boolean terminal values are refused. |
| CORE-05 | The batch oracle rejected a correct partial-success response when a requested record was missing. | The expected-outcome denominator retains every requested ID, including missing records, and enforces unique, correctly typed child outcomes. |
| CORE-06 | The graph router buffered arbitrary child output before truncating its returned string. A 16 MiB output caused about 50.4 MB of traced parent allocations. | A shared 64 KiB capture budget applies while reading stdout and stderr. Overflow and timeout fail closed, and owned subprocesses are terminated. |
| PKG-01 | A removed grader directory escaped historical path screening. | Each reachable commit's paths receive the forbidden-directory and filename rules. |
| PKG-02 | A safe filename concealed an identical blob formerly stored under a forbidden name. | Historical tree paths are inspected before content is deduplicated. |
| PKG-03 | Ordinary use of the installed regression helper created bytecode that caused install verification to fail. | The local helper import disables incidental bytecode. Ordinary CLI use leaves the install verifiable without requiring a special interpreter flag. |
| PKG-04 | Uninstall deleted an unowned empty directory because only files were checked against the receipt. | Verification checks the exact owned directory set and refuses unexpected directories. |
| PKG-05 | A historical symlink was missed when its path and target bytes later became a regular file with the same blob. | Historical identity includes object ID, path, mode and kind. The unchanged mode-alias regression passes. |

The three fixture-boundary findings CORE-03 through CORE-05 were gaps beyond the original seeded cases. They do not imply that the initially reported five known bugs failed to reproduce. The initial 59 targeted tests passed before the review exposed these additional failures.

## Verification and preservation of the original tests

[Certain] **102 distinct targeted checks passed after the relevant repairs:** 75 core checks and 27 package/scanner/runner checks. Reruns are not counted as additional checks. The final package gate reran its historical-mode regression and original package/scanner suites, passing 20 of 20 checks.

The core checks comprise 36 behavior checks, 29 evaluator/regression checks, and 10 graph-router checks. They include the original 24 behavioral-demo tests, original 28 evaluator/regression tests, original six graph-router tests, and the arbitrary-graph portability test. The same arbitrary-graph test failed against the historical implementation and passed against the candidate.

An AST comparison of the ten original test files found **all 345 original assertion calls/statements preserved**. The reviewed changes to those original tests adjust relocated script paths, replace private example identifiers with generic names, and supply the now-required external grading manifest. This is an assertion-expression preservation check; it does not turn a fixture suite into a complete product evaluation.

The independent regression files retained these SHA-256 values across failure and success:

| Regression test | SHA-256 |
| --- | --- |
| SQLite lifecycle | `136b8beb015333656c4856581fa6614711d443079650fe563ed0b4200f107e73` |
| Duplicate closures | `3f8a4eed3a957cda43795f778a35a6f06d394b4aa61074e8329876e0ae813e79` |
| Additional behavior boundaries | `e36ace35dbb2201294e01ddc008ebc8b555820e231d79a201d32add0c9cc4746` |
| Package boundaries | `9f5f75d8076c70b5511f59578ac932b6deb1b6ba3d46c9ee8c213a55b0ac4939` |
| Historical Git mode alias | `7f6c1187e53ea107913511218d5df819e75480f8a0225061ab391317a1683abe` |

The added router-output tests were also independently executed after the repair. Initial unbounded capture was separately demonstrated with the retained local-output probe.

## Rejected interpretations and corrected documentation

The scanner's credential-URL finding in `test_credentials_in_target_are_rejected` is a synthetic negative test using an example target. It is not an actual credential. The raw finding remains preserved with a manual false-positive disposition; no scanner suppression was added.

The demonstrations explicitly report that agent evaluation, hidden-benchmark evaluation and external-product testing were not performed. The evaluator requires an external manifest, and the runtime package excludes the public demonstration answers. These safeguards support the stated distinction between training fixtures and independent evaluation; they do not themselves provide operating-system isolation for a future evaluated agent.

Moved test commands in the network, evidence-ledger and behavior references were corrected to use the developer-checkout layout. The custom test runner now rejects an empty selection with exit code 2. Earlier assumptions that the obsolete raw `unittest` commands would silently exit zero were corrected: on the observed Python 3.12.14 and 3.13.5 interpreters they selected zero tests and exited 5. This review does not claim an independently executed pre-fix failure for the custom runner change.

## Scope and remaining validation

The core independent execution used Linux and CPython 3.12.14. Windows and Python 3.10 execution remain outside this review's measured coverage. The router enforces the tested memory budget, and its POSIX process-group cleanup was inspected; Windows descendant-process cleanup was not exercised.

The evaluator and regression helper validate supplied record consistency. Their hashes bind bytes, while the truth and independence of the supplied judgments still require a real reviewer. The public scanner is a heuristic release aid; its passing result does not establish the absence of every secret, personal detail, licensing issue or future grader encoding.

Final release-commit and archive identities, all reachable public history, redistribution rights, manual privacy review and unauthenticated public readback remain separate release checks. This source review supplies no broader detection, compatibility, efficiency or performance claim.

## Reviewed source identities

| File | SHA-256 |
| --- | --- |
| `scripts/behavior_lab.py` | `63f72977fd4d80c1ea5590650336c1e8b56d0549ebf3945a9ba509c5494634fa` |
| `scripts/impact_router.py` | `4a84149c4796a41d0a8425664295d703ebf44632103a295a92a67a75bbcff3c9` |
| `scripts/evaluate_audit.py` | `a4ae26f1ef3e7d1e783df9f3987647a758f5a81268d4f156e1372a86e0bb2c04` |
| `scripts/regression_evidence.py` | `25d2ad5e7cda04fca06945cd3cf28f46dfe76bf609b9397cf51aca29309d862e` |
| `tools/package_skill.py` | `c01c00282711ae05e10708fc00adbc31e77854655f264b8ea945dd99251d5799` |
| `tools/install_skill.py` | `e45005839a314052c0b7ee24fd2dc0fa9eb22c98f8851f129b2037a98395ce96` |
| `tools/public_scan.py` | `fd588a397844478ebfac86ea4b18f89f79e25baff8d4fca1f54265d004765df4` |
| `tools/run_tests.py` | `205bbd7d37b27ca45e367ae78be690f28b872babc11097f03cbfc26b52ec6c6f` |
| `references/network-testing.md` | `bd8ea7489ca21ac0077591c18c643a3ac38714e6bcd6424abe1b83b84d0028dc` |
| `references/research-checks.md` | `e928718273772593bb0d95f6f5b643230638c323ca87ca4f23cfba30a1a945aa` |
| `references/evidence-ledger.md` | `fb28d560e15308da81e3ae7ec7988def58818ff658c9e0f74c0d28a22f2fe620` |
| `package-manifest.json` | `6237bdb339e4e9072c07cc9d55f7dc2f6c64ffc1f6b58fa2dfda7f31630a5975` |
