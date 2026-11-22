# Source record

Reviewed 2026-11-21 for version 2.0.0. Original orchestration/helpers, with no vendored upstream packages or copied third-party skill bodies. Recheck installed versions and official guidance at execution. Research evidence and helper/fixture validation are distinct from real product audits or measured agent-performance improvements.

| Component | Primary source | Provenance and limit |
| --- | --- | --- |
| Agent Browser/Dogfood | https://agent-browser.dev/skills ; https://github.com/vercel-labs/agent-browser/blob/main/skill-data/dogfood/SKILL.md | Apache-2.0 project; CLI supplies version-matched guidance; separate runtime required |
| Web Design Guidelines | https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md ; https://github.com/vercel-labs/web-interface-guidelines | Collection README declares MIT; separate rules expose MIT; source review |
| Playwright | https://playwright.dev/docs/trace-viewer ; https://playwright.dev/docs/api/class-tracing ; https://playwright.dev/docs/test-agents | Apache-2.0; raw tracing does not record assertions |
| UI/UX Pro Max | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | MIT; advisory search, not verification |
| Systematic debugging | https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md | MIT; workflow, not runtime service |
| Responsive alpha | Primary source not verified | No copied code, license assertion, or installation; original Playwright fallback |

Reuse existing tools and dependencies. Copying moving upstream prompts creates stale competing guidance; installing packages alone does not prove readiness. Preserve notices and record exact revision/hash if upstream content is later vendored.

## Reliability patterns reviewed

| Reference | Primary source | Use and limit |
| --- | --- | --- |
| Cloudflare audit | https://github.com/cloudflare/security-audit-skill | MIT; reviewed README/SKILL; independent candidate verification pattern; security scope |
| QA Skills | https://github.com/petrkindlmann/qa-skills ; https://github.com/petrkindlmann/qa-skills/blob/main/VERSIONS.md | MIT; author dates v3.6.1 2026-11-16; selected skills and reported experiments reviewed; author findings are not independently reproduced performance gains |
| Eremitia UI audit | https://github.com/Eremitia/ui-audit-skill | MIT; README/license reviewed; budget/coverage/refutation ideas; README-only implementation confidence, Chromium limits |
| Trail of Bits fp-check | https://github.com/trailofbits/skills/blob/main/plugins/fp-check/skills/fp-check/SKILL.md | CC-BY-SA-4.0 collection; source workflow reviewed, no copied wording/code; findings verification only |
| Grafana k6 assistant | https://grafana.com/docs/k6/latest/set-up/configure-ai-assistant/ ; https://github.com/grafana/xk6-subcommand-agent | Official skills/MCP integration; bootstrap repository Apache-2.0; optional runtime not bundled; limits/version must be rechecked |
| Toxiproxy | https://github.com/Shopify/toxiproxy/blob/main/README.md | TCP stream fault semantics; real IP/UDP/QUIC faults need another layer |
| mitmproxy | https://docs.mitmproxy.org/stable/concepts/protocols/ | Protocol capabilities/replay limits; no automatic certificate/trust changes |
| netem | https://kernel.googlesource.com/pub/scm/network/iproute2/iproute2-next/+/refs/heads/main/man/man8/tc-netem.8 | Isolated Linux network fault semantics; no host network mutation by helpers |
| Retry semantics | https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/ | Unknown outcome, idempotency, bounded retry/backoff |
| Skill evaluation | https://developers.openai.com/blog/eval-skills ; https://www.anthropic.com/research/demystifying-evals-for-ai-agents | Task-local evaluation and independent grading; starter scenarios are not measured skill superiority |

Additional platform/API/testing primary links are located beside their uses in tool-selection.md, native-and-data.md, network-testing.md and evaluation.md. The bundled loopback HTTP/SQLite fixtures are new original code. They simulate particular failure mechanisms; they do not replace live network, OS-process crash, hardware or product acceptance tests.

## v3 review addendum (2026-11-21)

- Playwright Test Agents planner/generator/healer (and caveat that healer may skip broken behavior): https://playwright.dev/docs/test-agents
- Schemathesis stateful workflow/real mutating request caution: https://schemathesis.readthedocs.io/en/stable/explanations/stateful/
- k6 dropped iterations and open vs closed workload: https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/
- Conditional local Graphify guard: installed graphify-code-intelligence/SKILL.md, source identity and freshness must be verified against each target Git checkout.

Original v3 additions are local Python/JSON and do not vendor third-party prompt bodies or packages. Synthetic fixture capability and agent performance remain distinct.
