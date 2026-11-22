# Public demonstrations and coverage review

Run the known developer demonstrations from a full source checkout:

```sh
python scripts/benchmark_fixture.py --self-test --out NEW_LEGACY_DEMO_JSON
python scripts/behavior_lab.py --out NEW_BEHAVIOR_DEMO_JSON
```

They are local, disposable demonstrations of specified failures and clean
controls. Their implementations and expected outcomes are public. They test
fixture/oracle mechanics; they are neither blind benchmarks nor real-product
acceptance. Do not supply these known fixtures as held-out tasks to an agent.
The legacy generator's separate target/grader directories are a layout feature,
not an access-control boundary. See [evaluation](evaluation.md).

## Coverage critic

Declare schema_version=1, scope_id, revision, required_cases and observations.
Each case records id, priority P0..P3, dimensions, invariant and oracle_required.
Observations record case_id, status, matched dimensions/revision, evidence,
actual author/verifier identity and independent_oracle. Unknown and untested
are honest results, not missing rows to remove.

```sh
python scripts/coverage_critic.py SCOPE_CONTRACT --out NEW_REVIEW
```

The helper checks record consistency and hashed files, not factual truth. Keep
the full ledger validation. A separate reviewer should inspect the inventory for
forgotten controls, server-side authorization, unlinked routes, exports, durable
writes, lifecycle/permission transitions, cancellation and cross-session races.
Require a proposed test plus an independent oracle for each new gap.
