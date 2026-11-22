#!/usr/bin/env python3
"""Bounded local discovery; optional version probes never prove product readiness."""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import time

COMMANDS = {
    "python3": ["--version"], "node": ["--version"], "git": ["--version"],
    "agent-browser": ["--version"], "uipro": None, "claude": ["--version"],
    "codex": ["--version"], "k6": ["version"], "toxiproxy-server": ["-version"],
    "mitmdump": ["--version"], "schemathesis": ["--version"],
    "semgrep": ["--version"], "osv-scanner": ["--version"], "swift": ["--version"],
    "xcodebuild": ["-version"], "xcrun": ["--version"], "tc": ["-V"],
    "docker": ["--version"], "psql": ["--version"], "pg_prove": ["--version"],
}
PACKAGES = ["@playwright/test", "playwright", "@axe-core/playwright", "fast-check",
            "@pact-foundation/pact", "@stryker-mutator/core", "@opentelemetry/api"]
SKILLS = ["deep-product-audit", "agent-browser", "dogfood", "web-design-guidelines",
          "ui-ux-pro-max", "systematic-debugging", "ecc-debug", "ego-browser",
          "security-audit", "ui-audit", "fp-check", "bug-reproduction",
          "api-testing", "test-reliability", "chaos-engineering", "k6"]

# Resolve package metadata only. Never require/import a project's executable code.
PACKAGE_PROBE = r"""
const {createRequire}=require('module'), fs=require('fs'), path=require('path');
const r=createRequire(path.join(process.argv[1],'package.json'));
const names=JSON.parse(process.argv[2]), results={};
for (const name of names) {
  try {
    let metadata;
    try { metadata=r.resolve(name+'/package.json'); }
    catch (_) {
      let dir=path.dirname(r.resolve(name));
      for(let i=0;i<8;i++){
        const candidate=path.join(dir,'package.json');
        if(fs.existsSync(candidate)){
          const stat=fs.statSync(candidate);
          if(stat.size<=262144){
            const pkg=JSON.parse(fs.readFileSync(candidate,'utf8'));
            if(pkg.name===name){metadata=candidate;break;}
          }
        }
        const parent=path.dirname(dir); if(parent===dir)break; dir=parent;
      }
    }
    if(!metadata || fs.statSync(metadata).size>262144)throw Error('metadata_missing');
    const pkg=JSON.parse(fs.readFileSync(metadata,'utf8'));
    if(pkg.name!==name || typeof pkg.version!=='string')throw Error('metadata_invalid');
    results[name]={status:'available',readiness:'discovered',path:metadata,
      version:pkg.version,fixture_verified:false,product_executed:false};
  } catch (e) {
    results[name]={status:'not_found_or_unreadable',readiness:'unknown',
      fixture_verified:false,product_executed:false};
  }
}
console.log(JSON.stringify(results));
"""


def run(argv, cwd=None, timeout=3, output_limit=1200):
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        return {"exit_code": p.returncode, "output": p.stdout.strip()[:output_limit],
                "error": p.stderr.strip()[:400]}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "error": "timeout"}
    except OSError as exc:
        return {"exit_code": None, "error": type(exc).__name__}


def readiness(entry):
    """Return only the readiness actually established by this inventory."""
    if not entry.get("path"):
        return "missing"
    probe = entry.get("version_probe")
    if probe is None:
        return "discovered"
    return "runnable" if probe.get("exit_code") == 0 else "not_verified_runnable"


def inventory(project, extra_roots=(), check_runnable=False, timeout_seconds=20):
    started = time.monotonic()
    deadline = started + timeout_seconds
    home = pathlib.Path.home()
    roots = [home / ".agents/skills", home / ".claude/skills", home / ".codex/skills",
             home / ".cursor/skills", project / ".agents/skills",
             project / ".claude/skills", *extra_roots]
    skills = {}
    for name in SKILLS:
        matches, seen = [], set()
        candidates = [root.expanduser() / name / "SKILL.md" for root in roots]
        if name == "deep-product-audit":
            candidates.insert(0, pathlib.Path(__file__).resolve().parent.parent / "SKILL.md")
        for path in candidates:
            try:
                if not path.is_file() or path.stat().st_size > 524288:
                    continue
                resolved = path.resolve()
                if str(resolved) in seen:
                    continue
                seen.add(str(resolved))
                matches.append({"path": str(path), "resolved": str(resolved),
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            except OSError:
                continue
        skills[name] = {"status": "discovered" if matches else "not_found_in_scanned_roots",
                        "matches": matches, "invoked": False}
    commands = {}
    for name in COMMANDS:
        executable = shutil.which(name)
        commands[name] = {"path": executable, "status": "available" if executable else "missing",
                          "fixture_verified": False, "product_executed": False}
    to_probe = [name for name, flags in COMMANDS.items()
                if commands[name]["path"] and flags
                and (check_runnable or name in {"node", "python3", "git"})]

    def version(name):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return name, {"exit_code": None, "error": "inventory_budget_exhausted"}
        return name, run([commands[name]["path"], *COMMANDS[name]],
                         timeout=min(3, remaining))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for name, probe in pool.map(version, to_probe):
            commands[name]["version_probe"] = probe
    for entry in commands.values():
        entry["readiness"] = readiness(entry)

    packages = {name: {"status": "not_probed", "readiness": "unknown",
                       "fixture_verified": False, "product_executed": False}
                for name in PACKAGES}
    remaining = deadline - time.monotonic()
    if commands["node"]["path"] and remaining > 0:
        found = run([commands["node"]["path"], "-e", PACKAGE_PROBE, str(project),
                     json.dumps(PACKAGES)], cwd=project, timeout=min(5, remaining),
                    output_limit=32768)
        if found.get("exit_code") == 0:
            # This fixed metadata probe runs once with a bounded complete JSON budget.
            try:
                parsed = json.loads(found["output"])
                if set(parsed) == set(PACKAGES):
                    packages = parsed
            except (ValueError, TypeError):
                packages = {name: dict(info, status="metadata_output_unavailable")
                            for name, info in packages.items()}
    playwright = {"status": "missing_or_unverified", "browser_readiness": "not_tested",
                  "fixture_verified": False, "product_executed": False}
    for name in ["@playwright/test", "playwright"]:
        if packages[name]["status"] == "available":
            playwright.update(packages[name], package=name)
            break
    remaining = deadline - time.monotonic()
    revision = (run([commands["git"]["path"], "rev-parse", "HEAD"], cwd=project,
                    timeout=min(3, remaining))
                if commands["git"]["path"] and remaining > 0 else None)
    return {
        "schema_version": 2, "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project": str(project), "scope": "bounded local paths, metadata and optional versions",
        "skills": skills, "commands": commands, "packages": packages,
        "playwright": playwright, "revision": revision,
        "authenticated_access": "not_tested", "product_behavior": "not_tested",
        "responsive_alpha": "unverified_upstream",
        "duration_seconds": round(time.monotonic() - started, 3),
        "readiness_ladder": ["discovered", "runnable", "fixture_verified", "product_executed"],
        "notes": [
            "Availability and version success do not establish fixture or product behavior.",
            "Package discovery resolves metadata without importing project code.",
            "No installs, credential reads, browser launches or network fault changes performed.",
            "When project points at a shared runtime, revision belongs to that runtime, not the product.",
            "No product acceptance decision is made by this inventory.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--skill-root", type=pathlib.Path, action="append", default=[])
    parser.add_argument("--check-runnable", action="store_true",
                        help="Run bounded allowlisted version commands, never product actions")
    parser.add_argument("--timeout-seconds", type=int, default=20, choices=range(1, 61),
                        metavar="1..60")
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        parser.error("project must be an existing directory")
    if len(args.skill_root) > 8:
        parser.error("at most eight additional skill roots are supported")
    print(json.dumps(inventory(project, args.skill_root, args.check_runnable,
                               args.timeout_seconds), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
