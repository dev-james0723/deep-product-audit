# Adaptive Verification Engine v3.0.0

This extends v2's coordinator, evidence ledger, regression and release gates. Never replace the canonical v2 ledger with a weaker, self-reported score.

## Eight-part workflow

1. **Ground:** exact repository HEAD, target, deployed artifact, role/access, existing user instructions and permitted tests. Never infer real features from a profile example.
2. **Inventory and risk:** enumerate actual routes, journeys, roles, states, APIs, native lifecycle and integration boundaries. Prioritize money, identity, private data, irreversible effects, replay, cancellation, network recovery.
3. **Adaptive test selection:** choose a tool only if it supplies otherwise missing evidence. Probe installed capability; an executable version check is not product testing. Query Graphify conditionally only on an exact matching clean HEAD. Never auto-reindex.
4. **Execute:** act on real product within approved test authority. Use independent oracles and same-build evidence. Preserve all failed/unknown/blocked results.
5. **Coverage criticism:** give a fresh reviewer the actual inventory and execution records, not a success summary. Find missing roles, unlinked features, negative controls, state transitions, flakiness, blind spots and invalid equivalence assumptions.
6. **Repair:** reproduce real failure, isolate cause, fix authorized code, rerun unchanged assertion on buggy/fixed builds, independent reviewer and adjacent regression.
7. **Delivery:** corroborate source, artifact, running target and post-release smoke/monitoring evidence; never equate pushed code with deployed runtime or authorize deployment.
8. **Skill evaluation:** compare v2 and v3 via matched real agent invocations against separate frozen benchmark fixtures and held-out cases, not just testing the helper.

## Helper boundaries

- coverage_critic.py: independent scope record validator, not evidence truth.
- benchmark_fixture.py: 6 seeded defects + 6 clean controls, local HTTP/SQLite; no audited production.
- impact_router.py: read-only Graphify freshness routing; no automatic graph query.
- release_observer.py: offline examination of observed windows and evidence; no deployment or live network calls.
- evaluate_triggers.py: score observed skill loading decisions; does not run models.
- Existing audit_ledger.py and regression_evidence.py remain authoritative for source/runtime and before-after evidence.

## Results that MUST remain separate

- Helper unit tests passing.
- Fixture/oracle correctly distinguishes synthetic buggy and corrected services.
- Actual agent discovered and fixed a defect.
- A product's actual build/runtime was tested.
- An independent reviewer verified a claim.
- The user authorized a production deployment.

Never collapse these into one “all good.” The runnable 12-case fixture and the v2 20-case starter specifications are separate; no benchmark run has shown that v3 outperforms v2 yet.
