# Deep Product Audit

**4.0.0-rc.1 — public release candidate.** A portable, evidence-led workflow for
developers auditing web apps, APIs, command-line tools, desktop and mobile
software, including apps built with AI assistance.

Start with a user journey, prove what actually happened, repair authorized
defects, and verify the same requirement on the fixed build. A successful click,
green CI summary or passing mock is not enough to establish a working product.

The workflow is **Inventory → Plan → Execute → Reproduce → Root Cause →
Authorized Fix → Regression → Independent Verification → Release**.

## What is included

- A small [portable skill](SKILL.md) and deeper, selectively loaded checklists.
- A hash-bound evidence ledger with separate integrity, audit-complete and
  release-accepted gates; explicit passed, failed, blocked, untested and unknown.
- Before/after regression evidence, independent scope review and release-record
  consistency helpers. These assess records; they do not manufacture runtime proof.
- Checks for UI/backend/persistence, identity and tenant boundaries, APIs, money,
  concurrency/retries, network recovery, data integrity, accessibility, supported
  device behavior, performance and source-to-runtime provenance.
- Public local demonstrations with known defects and clean controls. They verify
  fixture mechanisms, not general bug-finding performance.
- Optional capability-checked graph, browser, API and network adapters.

Read the [dated research and pain-point matrix](docs/research.md),
[requirements](docs/product-requirements.md), [implementation plan](docs/implementation-plan.md)
and [QA evidence](docs/qa.md). The research includes a real Last30Days engine run
for **October 23–November 21, 2026**, with supplemental primary-source research
clearly separated. Reports are not equivalent to independently reproduced defects.

## Prerequisites and platform scope

Use **Python 3.10 or newer**, including the standard `sqlite3` module. There are
no mandatory third-party Python dependencies. On some systems use `python3`
instead of `python`; on Windows the equivalent may be `py -3`.

Git is needed only for revision/graph/history checks and tests that exercise
those integrations. Node plus an existing project-installed Playwright is needed
only for the optional responsive probe. No agent, Codex, Claude, graph provider,
desktop-control service or paid API is required for the core.

Linux and macOS execution is documented in [QA](docs/qa.md), with exact runtime
versions. Windows is **provisional and not runtime-tested in this release**.
OS-specific browser/native capabilities require their own platform and product
tests. Do not infer compatibility with every Python version or application.

## Install

Obtain the standalone source checkout at a reviewed release commit. From its
root, choose a **new** destination accepted by your agent host:

```sh
python tools/install_skill.py install --destination ../my-skills/deep-product-audit
python tools/install_skill.py verify --destination ../my-skills/deep-product-audit
```

The installer copies an explicit runtime allowlist and records SHA-256 hashes.
It does not install packages, change settings, discover credentials or overwrite
an existing directory. Inspect the files before invoking any skill. For agent
hosts, place/register this destination using that host's documented skill
configuration; a copied directory alone does not prove host discovery or invocation.

The runtime package deliberately excludes developer tests, demonstration source,
trigger labels and grading answers. **Do not install a full development checkout
as the evaluated agent's context.** Installation has no effect on OS permissions.

Build a deterministic runtime archive when needed:

```sh
python tools/package_skill.py --out ../deep-product-audit-runtime.zip
```

Keep output outside the source checkout or under an ignored `dist` directory for
release work. The archive has one `deep-product-audit` directory and a file-hash
receipt. Extract into a fresh location; compare the published archive digest.

## Uninstall and rollback

```sh
python tools/install_skill.py uninstall --destination ../my-skills/deep-product-audit
```

Uninstall first verifies the install receipt and refuses modified, missing,
foreign or symlinked files. Review/preserve local edits when verification fails;
do not delete them to force an uninstall. Remove the host's skill registration
using its own documented settings. For rollback retain the previous versioned
directory and restore that registration. Never merge a new release into a live
installation or modify the audited product as part of skill rollback.

## Use with an agent

Provide the installed `SKILL.md` and a bounded task, for example:

> Use deep-product-audit on this disposable staging app at the current commit.
> Audit saving a draft, reloading it, and tenant isolation with the two supplied
> test accounts. Inventory controls first. Make local authorized fixes, retain
> the same assertions before/after, and request an independent verification pass.
> Record blocked or untested work. Do not charge, publish or modify production.

Native Codex/Claude subagents and other hosts can split independent lanes when
available. One coordinator owns scope and integration. Do not run multiple
writers against the same browser/session. Different agent identity strings alone
do not establish independent evidence.

## Use without an agent

Read `SKILL.md` and the relevant checklists. Use the existing product test runner
for actual behavior, then collect evidence in a new bundle:

```sh
python scripts/audit_ledger.py init --out ../audit-output --target example-cli --target-kind cli --profile standard --environment local
python scripts/audit_ledger.py validate ../audit-output/audit.json
python scripts/audit_ledger.py validate ../audit-output/audit.json --gate audit
python scripts/audit_ledger.py validate ../audit-output/audit.json --gate release
```

The draft begins without passing observations. Populate it with real results
using the [ledger contract](references/evidence-ledger.md). An incomplete draft
must fail the audit/release gates. A completed investigation may contain defects;
it does not follow that a release is accepted.

## Develop and verify

From the complete source checkout:

```sh
python -B tools/run_tests.py
python scripts/benchmark_fixture.py --self-test --out ../legacy-demo.json
python scripts/behavior_lab.py --out ../behavior-demo.json
python scripts/network_fault_lab.py --mode compare --out ../network-demo.json
python tools/public_scan.py --history --out ../public-scan.json
```

The demos bind only owned loopback services and use disposable state. They accept
no live target. The history scanner requires a real Git repository and reports
findings without matched secret values. It is a bounded heuristic, not a complete
security or ownership proof. A synthetic credential-rejection test can produce a
reviewable match; preserve and explain that finding instead of weakening the test.

Grading a separate real trial requires an **external** evaluator-owned manifest
and enforced access isolation. See [evaluation](references/evaluation.md).
No matched model-performance, token-efficiency or cost-saving claims are made.

## License and security

Original code and documentation are licensed under [MIT](LICENSE), subject to
the provenance scope recorded in [NOTICE](NOTICE.md) and [licensing review](docs/licensing.md).
External sources/tools retain their own terms. See [SECURITY.md](SECURITY.md) for
safe reporting and [CONTRIBUTING.md](CONTRIBUTING.md) for contribution requirements.
