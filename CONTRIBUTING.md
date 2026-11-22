# Contributing

Start with a reproducible user-impacting failure or a documented missing check.
Explain the affected workflow, input, expected and actual results, independent
oracle, clean control and supported environment. Label proposals and anecdotes
as such. Do not infer that code written with AI is defective merely because of
its origin.

Keep the Python core dependency-free and portable. Place host/provider-specific
behavior behind explicit capability checks. Avoid hard-coded personal paths,
account names, private repositories, automatic installs or paid calls. Preserve
the ledger's public schema unless a versioned migration is justified.

For a material repair, add a regression that fails for the intended reason on
the old code. Keep its requirement and assertions unchanged after the fix. Run
`python -B tools/run_tests.py`, the relevant bounded demonstration and packaging
checks. Report exact failures, skipped/blocked cases and platforms not tested.
An independent reviewer should challenge both implementation and coverage.

Do not add benchmark answers or held-out targets to the repository or runtime
package. Public examples must be labeled known demonstrations. A fixture test
is not a comparative agent evaluation or proof of production reliability.

Contribute only work you have the right to redistribute under this project's
MIT license. Identify any incorporated third-party material and preserve its
required notices. Do not assume that an accessible public repository is licensed
for copying. Use citations and short original paraphrases for research; do not
commit raw scraped comments, transcripts or private research receipts.

Pull requests should state why the change is needed, resulting behavior,
reproduction/regression evidence, compatibility changes and remaining limits.
Do not include live credentials, customer content, private host paths or
unsupported marketing claims. Use the security reporting process for sensitive
issues. Maintainers may reject changes that weaken assertions or hide failures.
