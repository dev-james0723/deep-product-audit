> Developer fixture commands below require a full source checkout. The minimal runtime package excludes known demonstration source; this is not a missing product capability.

# Network reliability testing

## Choose the boundary

State the product invariant before injecting a fault. A timeout proves the caller lacks a result; it does not prove the operation failed. Observe committed data, durable operation records, queue state, or the real file independently of the UI/HTTP status. Retain unknown outcomes until reconciled. Never blindly replay an ambiguous GUI click or an operation with side effects.

Use [the network profile catalog](../assets/network-profiles.json) to select relevant cases. Each profile describes a fault, invariant, oracle, recovery check, and possible adapters. Catalog entries are plans, never completed coverage. Only five have bundled synthetic fixture execution; all other entries require a product-specific implementation and real evidence.

## Run the bounded fixture lab

```sh
python3 <skill>/scripts/network_fault_lab.py --mode compare --out <new-result.json>
python3 <skill>/scripts/network_fault_lab.py --list-profiles
python3 <source-checkout>/tools/run_tests.py test_network_fault_lab.py
```

`compare` executes deliberately buggy and corrected versions of five scenarios. It succeeds only when independent SQLite reads find duplicate committed effects in the three seeded buggy cases, the other buggy cases behave as expected, and all corrected cases pass. `buggy` alone should exit 1; `corrected` should exit 0. Neither is product acceptance. The output always says `product_accepted: false` and identifies its synthetic scope.

Executed fixture profiles: NET-001 offline before submission; NET-004 committed effect/lost reply; NET-005 committed effect/response timeout; NET-009 a 429 then one permitted retry; NET-017 lost reply and fresh server instances using the same durable SQLite file.

The lab binds only `127.0.0.1` ephemeral ports, uses stdlib HTTP and SQLite, writes only task-owned temporary fixture data plus an explicitly requested new result file, and removes fixture data on normal completion/cancellation. It has no URL, target, proxy, system-network, or deployment argument. Socket and database operations use 0.5-second timeouts; the delayed response is 0.35 seconds. A cooperative whole-run deadline defaults to 15 seconds and cannot be raised. Cleanup has additional bounded server operations. Run under an external process timeout if the host requires a hard process deadline.

The new server instances simulate loss of server memory; this is not an OS/process kill or power-loss test. The rate-limit fixture uses `Retry-After: 0` with exactly one recovery attempt; it does not validate a real exponential-backoff or jitter policy. TLS, DNS, WebSocket, genuine packet loss, browsers, native UI, and production load are not exercised by this lab. Preserve these limits when attaching its result to a ledger.

## Verify installed k6 and Toxiproxy first

```sh
python3 <skill>/scripts/verify_network_tools.py --tools k6,toxiproxy --out <new-tool-receipt.json>
```

This optional helper uses only selected installed binaries. It does not install anything. Missing tools stay `missing`; a successful version command establishes `runnable`, not `fixture_verified`. k6 runs one VU and three iterations against an owned loopback fixture with response assertions and thresholds. It receives an empty temporary config, disabled usage reporting, and no inherited `K6_*`/proxy configuration. No REST/dashboard server is enabled. Toxiproxy runs as an owned child on an explicit loopback control address, creates one loopback proxy, checks baseline, injects a downstream timeout, removes it, and verifies recovery. Only owned proxy/process state is removed; no service is registered.

The helper accepts tool names and a new output file, never a product URL. It has a 30-second cooperative overall budget, bounded subprocess/API waits, and child termination/cleanup. Output always retains `product_executed: false` and `product_accepted: false`. A receipt verifies these small adapter fixtures only; it does not establish production load, soak, packet-loss or product reliability coverage. Existing/symlinked output paths are rejected before tool execution. Run the helper on the actual host where the tools will be used.

## Convert a profile into a product test

1. Identify the actual target, build, protocol, test account/data, effect boundary, and authority from the current task. Skill installation alone does not authorize traffic to a product.
2. Prove the normal case first. Discover the adapter, run its bounded readiness check, then verify a controlled fixture. Installed is not executed.
3. Assign the fault path separately from the control/evidence path. Use a disposable proxy/runner or namespace. Do not disrupt the owner's Mac network, current control session, credentials, or trust store to simulate an outage.
4. Set finite request/retry/concurrency/duration budgets and a stop condition. Record the exact fault timing and observed injection effect; a configured fault that never touched the product is not coverage.
5. Run the relevant flow with a stable operation identity. For retries, check payload identity, duplicate effects, retry budget, backoff, queue growth, and results after server/client restart where applicable.
6. Check the independent oracle during failure and after recovery. UI, transport, persisted data, and background-work states must agree with the specified product contract.
7. Remove the fault in `finally`/runner cleanup. Verify normal behavior returns and owned processes, queues, connections, and files return to the expected state. Keep the original failure evidence and the repaired rerun separately.

Use new operation IDs across independent test cases; preserve the same ID only when testing a retry/replay of the same operation. Reuse with a different payload must have an explicit conflict policy. Durable deduplication must be atomic with the corresponding effect or backed by a documented reconciliation design; an in-memory map alone does not establish restart safety.

## Select an adapter

| Boundary | Adapter and use | Limit that must remain visible |
| --- | --- | --- |
| Browser HTTP/WS behavior | Existing Playwright installation; intercept/abort/fulfill a scoped request and verify application state | Mocking a response does not exercise the real upstream. Service workers and unhandled paths can bypass the intended interception. Record what actually ran. |
| Load/spike/stress/soak | Existing k6 CLI/isolated runner; use measured workload and explicit thresholds | Check generator headroom and dropped iterations. Choose arrival-rate vs closed-loop traffic deliberately. Do not infer correctness from throughput. |
| TCP latency/jitter/bandwidth/reset/timeout | Toxiproxy scoped to explicit test connections | The app must route through the proxy. Stream faults are not genuine IP packet loss, UDP, or QUIC simulation. Check installed-version capabilities. |
| HTTP(S)/WS inspection/mutation | mitmproxy in a disposable test configuration | TLS interception may require test trust settings; certificate pinning and protocol support constrain coverage. WebSocket replay is limited. |
| Actual IP packet loss/reorder/duplication | Linux `tc/netem` in an isolated namespace/router/runner | This is not a macOS host-network default. Record the interface/direction and remove only the owned rule. Keep the control channel outside the fault path. |
| Native app network changes | Native UI/integration tests on test devices plus a controlled network boundary | Browser emulation does not prove native sleep/wake, VPN/Wi-Fi switching, permission, or lifecycle behavior. |

For k6, use the current installed help and official documentation. The documented MCP `run_script` has a 50-VU/5-minute ceiling; `validate_script` itself runs a small test. Use an appropriate CLI runner for longer/larger work. These limits describe the checked documentation, not an installed runtime guarantee.

## Evidence and completion

For every executed profile record the selected build, case ID, input/operation ID, adapter/version, fault configuration, proof the fault occurred, independent state observations, retry count, recovery result, cleanup result, and evidence timestamps. Redact tokens, cookies and real private bodies. Store actual adapter output separately from the profile definition. Do not label source excerpts or this fixture lab as live-product evidence.

Keep failed, blocked, not-tested, inconclusive and out-of-scope results distinct. A server error caused by the test environment is not automatically a product defect. A passing fixture lab establishes that the bundled lab can distinguish its seeded defect; it does not demonstrate a higher bug-finding rate for the skill.

## Primary references

- Playwright network controls: https://playwright.dev/docs/network
- Grafana integration: https://grafana.com/docs/k6/latest/set-up/configure-ai-assistant/
- Grafana MCP tools and limits: https://grafana.com/docs/k6/latest/set-up/configure-ai-assistant/tools-prompts-resources/
- k6 open/closed workload models: https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/
- Toxiproxy upstream: https://github.com/Shopify/toxiproxy/blob/main/README.md
- mitmproxy protocols: https://docs.mitmproxy.org/stable/concepts/protocols/
- Linux netem manual source: https://kernel.googlesource.com/pub/scm/network/iproute2/iproute2-next/+/refs/heads/main/man/man8/tc-netem.8
- Retry semantics: https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/

Checked during the 2026-11-21 research. Recheck version-specific commands and limits before executing a third-party adapter. No third-party skill text or implementation is bundled here.
