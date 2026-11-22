# Select tools by the missing evidence

Start with the product's existing tests, runtime and observed failure. A tool is useful only when it supplies an observation or experiment the current stack cannot. Do not install an entire collection to claim coverage.

## Readiness contract

| Stage | Evidence | What it does not establish |
| --- | --- | --- |
| discovered | Resolved executable/package/skill path and version/hash | It runs or is configured |
| runnable | Successful bounded help/version or documented startup | Browser permissions, credentials or product connectivity |
| fixture_verified | Relevant operation succeeds on an owned fixture with recorded evidence | Real product behavior |
| product_executed | Named case ran against exact product/environment/build | Untested variants or release acceptance |

`probe_capabilities.py` establishes discovery and, with `--check-runnable`, bounded allowlisted version results. It never promotes a capability to fixture/product verified. Failures remain explicit. Do not use a global `npx` auto-download as a readiness check. Prefer the locked project binary. Record runtime and product revisions separately when they differ.

## Capability routing

| Need | Preferred lane | Independent check / limitation |
| --- | --- | --- |
| Web journeys | Existing Playwright Test and trace viewer | Assert backend postconditions as well as UI; engine emulation is not a real-device claim |
| Web accessibility | axe-core plus keyboard/focus/screen-reader checks | Automatic checks cover only a subset; inspect hidden/expanded/error states |
| Native macOS/iOS | Swift Testing, XCTest/XCUIAutomation, Instruments; authorized native control | Verify signing/permission rules first; record actual platform, build, files and lifecycle |
| API schema/state | Existing API tests, Schemathesis where applicable | Schema conformance does not establish every business rule or role boundary |
| Independent service evolution | Pact consumer/provider verification | A generated contract without provider verification is incomplete |
| Generated state sequences | fast-check model/command testing | Use a small independent model, preserve seed/shrunk failure and state preconditions |
| Assertions against wrong code | Stryker mutation testing on high-risk logic | Equivalent/uncovered mutants need interpretation; do not demand arbitrary 100% |
| Database/tenancy | pgTAP and API tests with real roles/JWT fixtures | Verify effective identity, returned/affected rows and each access surface |
| Static code risks | Semgrep / supported CodeQL workflow | Triage reachability and conditions; a scanner alert is a candidate |
| Known dependencies | OSV-Scanner and the existing package scanner | Advisory coverage is bounded; record lockfile, database/version and exclusions |
| Load and endurance | k6 CLI/isolated runner | Measure latency, errors, throughput, generator headroom, dropped work and product invariants |
| TCP dependency faults | Toxiproxy | Route only the intended dependency through it; not equivalent to UDP/QUIC/IP packet loss |
| HTTP(S)/WebSocket observation | mitmproxy or existing test proxy | Honor test trust/pinning configuration; protocol/replay support varies |
| IP loss/reorder/duplicate | Linux tc/netem in isolated network namespace/router | Do not impair the control path or the user's everyday Mac network |
| Correlated runtime evidence | Existing logs/metrics/traces/OpenTelemetry | Preserve request/operation IDs without secrets; telemetry is an observation, not an oracle by itself |

Verify current official docs and installed help when selecting command flags. Optional tools are not bundled installations. A missing optional lane blocks only the cases that require it; never relabel missing execution as a pass.

## Skill patterns worth adapting

- Cloudflare security-audit-skill: enumerate scope, allocate investigators, refute candidates independently, retain confirmed/rejected/needs-validation records.
- QA Skills: reproducible bug reports, before/after regression evidence, lost-reply and account-switch cases. An author's benchmark is not a demonstrated gain on this product.
- Eremitia ui-audit-skill: bounded coverage units, validation reserve and isolated execution. README capabilities and Chromium-only coverage are not proof of native/Safari coverage.
- Trail of Bits fp-check: challenge a security candidate's reachability, prerequisites and impact. Preserve inconclusive results in this coordinator.
- Playwright Test Agents: planner/generator/healer roles can assist the existing runner. Require unchanged requirements and assertions when healing mechanics.

These are references and independently implemented patterns, not vendored upstream skills. Keep third-party versions/licenses explicit if installing or copying later. Do not claim these skills are installed from this document alone.

## Workload and cost controls

Run focused checks on changes, wider role/state checks for full audits, and isolated endurance/fault tests for release risk. Reuse safe fixtures and immutable evidence; do not reuse a passing result across changed code, state, accounts or environments without an explicit validity argument. Deduplicate findings by invariant/boundary rather than wording. Stop optional testing once the remaining concrete risk is resolved; retain mandatory project gates.

For k6, choose open-arrival vs closed-concurrency workload from the real traffic model. Closed workloads can reduce arrivals as responses slow. Record thresholds and dropped iterations, and ensure the generator is not the bottleneck. The researched MCP tools were preview/bounded (run_script 50 VUs/5 minutes; validate_script executes a small real run); recheck current limits and use CLI for larger/longer work. Set cancellation, data cleanup, maximum runtime and recovery criteria before a product run.

## Primary guidance

- https://playwright.dev/docs/api-testing
- https://playwright.dev/docs/accessibility-testing
- https://playwright.dev/docs/test-agents
- https://grafana.com/docs/k6/latest/set-up/configure-ai-assistant/
- https://grafana.com/docs/k6/latest/set-up/configure-ai-assistant/tools-prompts-resources/
- https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/
- https://fast-check.dev/docs/advanced/model-based-testing/
- https://schemathesis.readthedocs.io/en/stable/explanations/stateful/
- https://docs.pact.io/getting_started/how_pact_works
- https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/
- https://asvs.owasp.org/
