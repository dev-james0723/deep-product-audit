#!/usr/bin/env python3
"""Bounded local CI lane for native Python or a disconnected Linux Docker runner.

No network is available inside the Linux test container. Only a selected local
repository is mounted, read-only. Logs and receipts go to an external new folder.
The runner never pushes, merges, deploys, changes host skill registrations or
claims Windows verification from Linux containers.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
TEST_PATTERN = re.compile(r"Ran (\d+) tests? in [\d.]+s")
SKIP_PATTERN = re.compile(r"\bskipped=(\d+)")
MAX_RUNTIME_SECONDS = 110


def run(args: list[str], *, timeout: int = MAX_RUNTIME_SECONDS, env=None, cwd=ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env, check=False)


def git(*args: str) -> str:
    outcome = run(["git", "-C", str(ROOT), *args], timeout=10)
    if outcome.returncode:
        raise RuntimeError("Git source identity unavailable")
    return outcome.stdout.strip()


def log_sha(path: Path, data: str) -> str:
    with path.open("x", encoding="utf-8") as file:
        file.write(data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_lane(kind: str, python: str | None, docker_context: str | None,
             image: str | None, out: Path, min_tests: int) -> dict:
    if out.exists() or out.is_symlink():
        raise ValueError("Output directory already exists; use a new location")
    if ROOT in out.parents or ROOT == out:
        raise ValueError("Keep CI evidence outside the source checkout")
    out.mkdir(parents=True)
    commit = git("rev-parse", "HEAD")
    source_dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    identity = {"schema_version": 1, "runner": kind, "source_commit": commit,
                "source_dirty": source_dirty,
                "run_started_at": datetime.now(timezone.utc).isoformat(),
                "min_test_count": min_tests,
                "owner_effects": "none", "github_actions_used": False,
                "native_windows_verified": False,
                "release_accepted": False, "checks": []}
    if kind == "native":
        if not python or not Path(python).is_file():
            raise ValueError("Specify an absolute path to an installed Python interpreter")
        ver = run([python, "--version"], timeout=8)
        if ver.returncode:
            raise ValueError("The provided Python interpreter cannot start")
        identity["platform"] = platform.system()
        identity["python_version"] = (ver.stdout or ver.stderr).strip()
        identity["host_architecture"] = platform.machine()
        prefix = [python, "-B"]
        allowed = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")
        env = {name: os.environ[name] for name in allowed if name in os.environ}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        native_home = tempfile.TemporaryDirectory(prefix="dpa-localci-home-")
        env["HOME"] = native_home.name
        env["XDG_CONFIG_HOME"] = str(Path(native_home.name) / "config")
        env["XDG_CACHE_HOME"] = str(Path(native_home.name) / "cache")
    else:
        if not docker_context or not image:
            raise ValueError("Linux Docker runner requires --docker-context and --image")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", docker_context):
            raise ValueError("Unexpected Docker context name")
        if not re.fullmatch(r"[a-zA-Z0-9._/:@-]+", image):
            raise ValueError("Unexpected Docker image name")
        docker_id = run(["docker", "--context", docker_context, "image", "inspect", image,
                         "--format", "{{.Id}}"], timeout=15)
        if docker_id.returncode or not docker_id.stdout.strip().startswith("sha256:"):
            raise ValueError("Local Docker runner image is missing; build it explicitly, never pull on a test run")
        identity.update({"platform": "Linux", "image_id": docker_id.stdout.strip(),
                         "image": image, "docker_context": docker_context,
                         "network": "none", "workspace_mount": "read_only",
                         "cpu_limit": 2, "memory_limit": "1536m", "pids_limit": 128})
        prefix = ["docker", "--context", docker_context,
                  "run", "--rm", "--pull", "never", "--platform", "linux/arm64",
                  "--network", "none", "--read-only",
                  "--tmpfs", "/tmp:rw,size=512m,mode=1777",
                  "--cpus", "2", "--memory", "1536m", "--pids-limit", "128",
                  "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
                  "--user", "65534:65534", "--volume", f"{ROOT}:/work:ro",
                  "--workdir", "/work", "--env", "HOME=/tmp",
                  "--env", "PYTHONDONTWRITEBYTECODE=1",
                  "--env", "GIT_CONFIG_COUNT=1", "--env", "GIT_CONFIG_KEY_0=safe.directory",
                  "--env", "GIT_CONFIG_VALUE_0=/work", image, "python", "-B"]
        env = None
    commands = [("full_suite", "tools/run_tests.py"),
                ("disposable_smoke", "tools/ci_portability_smoke.py")]
    for label, script in commands:
        t0 = time.monotonic()
        try:
            result = run(prefix + [script], env=env)
            out_text, err_text = result.stdout, result.stderr
            code = result.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            out_text = (exc.stdout or b"")
            err_text = (exc.stderr or b"")
            if isinstance(out_text, bytes):
                out_text = out_text.decode("utf-8", "replace")
            if isinstance(err_text, bytes):
                err_text = err_text.decode("utf-8", "replace")
            code = 124
            timed_out = True
        stdout_file = label + ".stdout.log"
        stderr_file = label + ".stderr.log"
        check = {"name": label, "exit_code": code, "timed_out": timed_out,
                 "elapsed_seconds": round(time.monotonic()-t0, 3),
                 "stdout": stdout_file, "stderr": stderr_file,
                 "stdout_sha256": log_sha(out/stdout_file, out_text),
                 "stderr_sha256": log_sha(out/stderr_file, err_text)}
        if label == "full_suite":
            pattern = TEST_PATTERN.search(err_text)
            check["tests_discovered"] = int(pattern.group(1)) if pattern else 0
            skip = SKIP_PATTERN.search(err_text)
            check["skipped"] = int(skip.group(1)) if skip else 0
            check["pass"] = (code == 0 and not timed_out
                             and check["tests_discovered"] >= min_tests
                             and check["skipped"] == 0 and
                             re.search(r"(?m)^OK\s*$", err_text) is not None)
        else:
            try:
                structured = json.loads(out_text)
            except json.JSONDecodeError:
                structured = {}
            check["pass"] = (code == 0 and structured.get("result") == "passed"
                             and structured.get("installer_uninstall_verify") == "passed"
                             and structured.get("normal_and_negative_controls") == "passed")
            if structured:
                check["smoke_summary"] = structured
        identity["checks"].append(check)
        if not check["pass"]:
            break  # Stop after one failed check, never mark an unrun check passed.
    if kind == "native":
        native_home.cleanup()
    identity["run_completed_at"] = datetime.now(timezone.utc).isoformat()
    identity["source_revision_after"] = git("rev-parse", "HEAD")
    identity["source_dirty_after"] = bool(git("status", "--porcelain", "--untracked-files=normal"))
    identity["source_consistent"] = (identity["source_revision_after"] == commit and identity["source_dirty_after"] == source_dirty)
    identity["state"] = "passed" if len(identity["checks"]) == len(commands) and all(x["pass"] for x in identity["checks"]) and identity["source_consistent"] else "failed"
    report = json.dumps(identity, indent=2, ensure_ascii=False) + "\n"
    (out / "receipt.json").write_text(report, encoding="utf-8")
    return identity


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runner", choices=("native", "linux-docker"), required=True)
    p.add_argument("--python", help="Absolute interpreter path for native runner")
    p.add_argument("--docker-context", help="Explicit preexisting local Docker context")
    p.add_argument("--image", help="Prebuilt local Docker image; pulls disabled")
    p.add_argument("--out", type=Path, required=True, help="Fresh folder OUTSIDE repository")
    p.add_argument("--min-tests", type=int, default=1)
    a = p.parse_args()
    if a.min_tests < 1:
        p.error("--min-tests must be positive")
    try:
        data = run_lane(a.runner, a.python, a.docker_context, a.image,
                        a.out.resolve(), a.min_tests)
    except (ValueError, OSError, RuntimeError) as exc:
        print("Local CI preflight blocked: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"state": data["state"], "runner": data["runner"],
                      "python": data.get("python_version", data.get("image")),
                      "checks": [{k: v for k, v in check.items() if k in
                                  ("name", "pass", "tests_discovered", "skipped", "exit_code")}
                                 for check in data["checks"]],
                      "windows_native": "not_tested", "release_accepted": False}))
    return 0 if data["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
