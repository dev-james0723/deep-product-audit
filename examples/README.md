# Optional black-box integration example

`pocketbase_blackbox.py` demonstrates independent runtime evidence against a **real external open-source backend**. It is a manual, disposable example, **not a mandatory skill dependency** or an evaluation of bug-finding effectiveness. No vendor binary is distributed with this project.

## Reproduce (macOS ARM64)

Use the archived official PocketBase v0.40.6 release and verify its exact SHA-256 before execution. Never use a live deployment or existing data directory.

```sh
mkdir -p /tmp/dpa-pocketbase-check
curl -fL --retry 2   https://github.com/pocketbase/pocketbase/releases/download/v0.40.6/pocketbase_0.40.6_darwin_arm64.zip   -o /tmp/dpa-pocketbase-check/pocketbase.zip
shasum -a 256 /tmp/dpa-pocketbase-check/pocketbase.zip
# Must equal 7f2f7544e9ee5994ab69f84b22a4ab9a3bcfed58c1dad7206d05ebeb753f968b
unzip -q /tmp/dpa-pocketbase-check/pocketbase.zip pocketbase -d /tmp/dpa-pocketbase-check
chmod 700 /tmp/dpa-pocketbase-check/pocketbase
python3 -B examples/pocketbase_blackbox.py   --binary /tmp/dpa-pocketbase-check/pocketbase   --archive /tmp/dpa-pocketbase-check/pocketbase.zip   --out /tmp/dpa-pocketbase-check/report.json
```

The script refuses a mismatched binary/archive digest, creates temporary users and SQLite data, serves only on 127.0.0.1, verifies HTTP authorization, persistence, independent SQLite state and restart, then removes temporary data. Disposable credentials are randomly generated and are not sent to external services or stored in the report. All subprocesses get a sanitized environment.

This example verifies a known expected contract. It does **not** reproduce a specific upstream bug, verify the web Dashboard UI, prove security of PocketBase as a whole, measure agent ability or authorize fault injection into production. The original vendor retains its own license; this repository does not redistribute the vendor binary.

## Optional Codex host discovery verification

Developers who have Codex CLI installed can check real skill discovery without
running an LLM request:

```sh
python3 -B examples/codex_discovery_probe.py --out ../codex-discovery-receipt.json
```

This builds a *fresh*, isolated runtime installation under a temporary
`CODEX_HOME` and queries the Codex app-server `skills/list` protocol. It
confirms one enabled skill path, then terminates the local process. Missing
Codex is reported as **blocked**, not passed. This is **not** evidence that any
existing live Codex or Claude session has switched versions, nor that an agent
can successfully use the skill on a real task.
