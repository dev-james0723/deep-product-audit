# Evaluation and regression integrity

## Product fix evidence

Use `python scripts/regression_evidence.py --help` for the input contract. Freeze
the original requirement, executable assertion and independent oracle. Preserve
before/after command, environment, revision, exact failed assertion, exit code,
raw result and file digests. Both executions must run the same test. Import or
infrastructure failure, skipped assertions, changed expected values, retries
that conceal instability and self-signed reviewer labels do not establish a fix.
The helper checks supplied evidence consistency; a reviewer still examines the
content and its relationship to the claimed behavior.

## Public demonstrations

`scripts/benchmark_fixture.py` is the legacy 6-defect/6-clean-control HTTP/SQLite
demonstration. `scripts/behavior_lab.py` adds research-derived public examples.
These developer-only sources include known implementations and oracles. They are
not installed into the agent runtime package and **must not be represented as
blind or held-out evaluations**. Their success verifies fixture mechanics only.

## Genuine independent evaluation

Use fresh tasks that have not been published in this repository. Have a separate
evaluator create and freeze a manifest and grading environment. Keep answers,
reference fixes, logs and held-out cases physically inaccessible to the evaluated
agent, including inherited context, host filesystem, mounts, connectors and
network. Do not launch an evaluated agent with access to this development checkout
or a sibling grader directory under the same unrestricted operating-system user.
If that separation cannot be enforced, report evaluation blocked.

The evaluator runs, in its separate environment:

```sh
python scripts/evaluate_audit.py --manifest EXTERNAL_MANIFEST prompts --out NEW_PROMPTS
python scripts/evaluate_audit.py --manifest EXTERNAL_MANIFEST template --out NEW_RUN_TEMPLATE
python scripts/evaluate_audit.py --manifest EXTERNAL_MANIFEST score --baseline BASELINE_RUN --candidate CANDIDATE_RUN
```

Only sanitized prompts/targets reach the evaluated agent. Templates begin with
unknown results and attempted=false. No grader manifest is bundled. Version 4
requires `--manifest` explicitly; the legacy default answer set is retained only
in the private historical baseline, not this public repository or package.

Match models, tool access, environments, budgets, case sets and repetitions.
Independently judge confirmed findings, false positives, false closures,
regressions, completeness and observed cost/time. Keep failures and absent
measurements. Known-case recall cannot estimate all unknown bugs. A single
repetition or a fixture self-test cannot establish performance superiority.
