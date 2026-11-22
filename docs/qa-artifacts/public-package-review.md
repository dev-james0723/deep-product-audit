# Independent package review: 4.0.0-rc.1

## Outcome

The confirmed package and scanner defects found in this review were repaired and independently rechecked with unchanged regression tests. No unresolved confirmed defect remains within the inspected package, installer, scanner, and documentation scope at the source digests below.

This review inspected known public code and ran disposable local checks. It is not a held-out benchmark, an agent performance evaluation, proof of secret absence, or authorization to publish. It did not use an external network, credentials, a production target, or a paid service.

## Findings and disposition

| Finding | Initial observation | Final disposition |
| --- | --- | --- |
| Removed grader directories escaped history screening | A removed `heldout/cases.json` produced a successful history screen with no finding. | Fixed. Historical tree paths now receive the same forbidden-directory and filename rules as current files. The unchanged regression passes. |
| A safe filename concealed an identical forbidden historical file | A blob shared by `README.md` and a removed `.env` appeared under only its safe representative name in the object inventory. | Fixed. The scanner inspects each reachable commit's paths before deduplicating content. The unchanged regression passes. |
| Normal runtime use made an installation unverifiable | Running the regression helper normally created an unlisted local bytecode cache; subsequent verification rejected the install. | Fixed. The helper disables incidental bytecode before its local import. Ordinary CLI use and subsequent verification pass without a `-B` workaround. |
| Uninstall removed an unowned empty directory | Only files were checked against the receipt, so an unrelated empty directory was accepted and recursively removed. | Fixed. Verification checks the exact directory set implied by owned file paths and preserves unexpected directories. The unchanged regression passes. |
| Historical symlink mode was lost during path deduplication | A symlink replaced by a normal file with the same path and bytes was skipped because the identity omitted Git mode. | Fixed. Historical identity includes object ID, path, mode, and kind. The unchanged regression passes. |
| Examples still used the previous test layout | Developer test commands selected zero tests, and one example imported a test factory from the old directory. | Corrected. Examples now identify the full developer checkout, use the test runner, and add both script and test paths where needed. |
| The custom runner needed to reject empty selection | The repaired runner was available before this package review executed the old version. | Current behavior independently verified: zero selected tests exit 2. This review does not claim an independently executed before-failure for that runner change. |

The scanner's credential-URL match in `test_credentials_in_target_are_rejected` is a synthetic negative test, not an actual credential. The test asserts that example credential-bearing targets are rejected. The raw finding remains preserved, with a manual disposition and no suppression added to scanner code.

## Verification evidence

There were **27 distinct targeted checks** across this review: 13 original package tests, 6 original scanner tests, 6 independent package boundary tests, 1 independent historical-mode test, and 1 empty-selection runner test. All passed after the relevant repairs. The final affected gate reran the historical-mode test plus the original scanner and package suites: **20 tests passed**. Repeated executions are not counted as additional distinct checks.

The six independent package tests retained SHA-256 `9f5f75d8076c70b5511f59578ac932b6deb1b6ba3d46c9ee8c213a55b0ac4939` across the failing and passing executions. The historical-mode test retained SHA-256 `7f6c1187e53ea107913511218d5df819e75480f8a0225061ab391317a1683abe` across its failing and passing executions. The nonempty-runner test has SHA-256 `6c8c151a7ab60c2352c401ed89bb846696b3f7637f7b7facc3c7d9dfed16b371`.

The package and installer source digests did not change between the first repair verification and the final gate. Controls established that unlisted arbitrary files remain outside the runtime snapshot, allowlisted symlinks are rejected, archives are deterministic for identical input bytes, existing destinations are not merged, and modified or unrelated install contents are preserved.

The obsolete raw `unittest` commands selected zero tests and exited 5 on the observed Python 3.12.14 and Python 3.13.5 interpreters. An earlier assumption that those raw commands would exit zero was corrected using actual execution. The custom runner's current explicit rejection returns exit 2.

## Final source identity

| File | SHA-256 |
| --- | --- |
| `tools/package_skill.py` | `c01c00282711ae05e10708fc00adbc31e77854655f264b8ea945dd99251d5799` |
| `tools/install_skill.py` | `e45005839a314052c0b7ee24fd2dc0fa9eb22c98f8851f129b2037a98395ce96` |
| `tools/public_scan.py` | `fd588a397844478ebfac86ea4b18f89f79e25baff8d4fca1f54265d004765df4` |
| `tools/run_tests.py` | `205bbd7d37b27ca45e367ae78be690f28b872babc11097f03cbfc26b52ec6c6f` |
| `scripts/regression_evidence.py` | `25d2ad5e7cda04fca06945cd3cf28f46dfe76bf609b9397cf51aca29309d862e` |
| `references/network-testing.md` | `bd8ea7489ca21ac0077591c18c643a3ac38714e6bcd6424abe1b83b84d0028dc` |
| `references/research-checks.md` | `e928718273772593bb0d95f6f5b643230638c323ca87ca4f23cfba30a1a945aa` |
| `references/evidence-ledger.md` | `fb28d560e15308da81e3ae7ec7988def58818ff658c9e0f74c0d28a22f2fe620` |
| `package-manifest.json` | `6237bdb339e4e9072c07cc9d55f7dc2f6c64ffc1f6b58fa2dfda7f31630a5975` |

## Remaining limits

Windows execution was not available and remains untested. Heuristic screening does not prove that all secrets, personal information, license conflicts, or novel grader encodings are absent. The final public commit, all reachable public history, redistribution rights, and unauthenticated public readback require their own release review. No broader performance or compatibility claim follows from these known-code tests.
