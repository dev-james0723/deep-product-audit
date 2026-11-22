# Optional adapters

The core works without an agent, graph, browser package or hosted service.
Probe installed capability first. Distinguish discovered, runnable,
fixture-verified and executed on the product. Missing capability leaves the
affected check blocked or untested; it never becomes a pass.

## Code graphs

Use any authorized Python guard implementing the following JSON contract:
`should_query_graph=true`, `status=ready|ready_remapped`, canonical `repository`,
explicit `graph`, `head` and `indexed_commit`. Both revisions must equal the
clean repository HEAD. The router rechecks HEAD and cleanliness after the guard.

```sh
python scripts/impact_router.py --repo PATH_TO_PROJECT --graph sample-module --guard PATH_TO_AUTHORIZED_GUARD
```

Omit graph/guard to use targeted source inspection. No guard is auto-discovered,
installed, queried or granted extra authority. The guard is executable code:
inspect it and authorize its use before invocation. The router only validates
its output; a compromised guard is not made safe by JSON validation. Never
auto-index or upload source. Verify graph claims against current source/tests.
Graphify is one possible adapter, not a required runtime.

## Browser and accessibility

Use the existing project runner and installed Playwright/browser tools. The
responsive probe performs initial observations, not authentication journeys or
complete accessibility verification. Enable traces only after considering their
private contents. Add actual keyboard/focus, zoom, reduced-motion and supported
assistive-technology checks. Planner/generator/healer tooling must preserve
original requirements and assertions; skipped broken behavior is not repaired.

## API, network and load

Use an existing OpenAPI runner or installed Schemathesis on authorized disposable
APIs. Record operation links and independent authorization/data oracles; no
covered links means no stateful link coverage. Use installed k6/Toxiproxy only
once bounded fixture checks pass. Distinguish open arrival-rate and closed
concurrency workloads; report p95, errors, dropped iterations, generator limits
and durable outcomes. Keep the test-control transport separate from injected faults.

Official documentation: https://playwright.dev/docs/test-agents ;
https://schemathesis.readthedocs.io/en/stable/explanations/stateful/ ;
https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/
