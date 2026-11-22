#!/usr/bin/env python3
"""Aggregate verified local CI receipts; missing/dirty/altered lanes never pass.

This is a local artifact evaluator, not an assertion of product release safety.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MAX_RECEIPT = 100_000


def load_json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_RECEIPT:
        raise ValueError("Missing/oversized matrix or lane receipt")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def safe_log(directory: Path, name: str, digest: str) -> bool:
    if (not isinstance(name, str) or not name or
        not re.fullmatch(r"[A-Za-z0-9._-]+", name) or
        name.startswith(".") or name in ("..", ".") or
        not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        return False
    f = directory / name
    return f.is_file() and not f.is_symlink() and f.stat().st_size < 5_000_000 and hashlib.sha256(f.read_bytes()).hexdigest() == digest


def check_receipt(lane: dict, data: dict, directory: Path, expected_head: str,
                  min_tests: int, expected_runtime_digest: str | None) -> dict:
    issues = []
    if data.get("schema_version") != 1 or data.get("runner") != lane["runner"] or data.get("platform") != lane["platform"]:
        issues.append("INVALID_IDENTITY")
    if data.get("source_commit") != expected_head:
        issues.append("SOURCE_COMMIT_MISMATCH")
    if data.get("source_dirty") is not False or data.get("source_dirty_after") is not False:
        issues.append("UNCLEAN_WORKTREE_AT_EXECUTION")
    if data.get("source_consistent") is not True or data.get("source_revision_after") != expected_head:
        issues.append("SOURCE_CHANGED_DURING_EXECUTION")
    if not isinstance(data.get("checks"), list) or len(data["checks"]) != 2:
        issues.append("MISSING_CHECKS")
        checks = []
    else:
        checks = data["checks"]
    if [x.get("name") for x in checks] != ["full_suite", "disposable_smoke"]:
        issues.append("CHECK_ORDER_MISMATCH")
    for x in checks:
        if x.get("pass") is not True or x.get("exit_code") != 0 or x.get("timed_out") is not False:
            issues.append("CHECK_FAILED")
        for stream in ("stdout", "stderr"):
            if not safe_log(directory, x.get(stream), x.get(stream+"_sha256")):
                issues.append("MISSING_OR_TAMPERED_LOG")
    if len(checks) == 2:
        test=checks[0]
        if type(test.get("tests_discovered")) is not int or test["tests_discovered"] < min_tests or test.get("skipped") != 0:
            issues.append("TEST_COUNT_OR_SKIPS")
        summary=checks[1].get("smoke_summary", {})
        if summary.get("result") != "passed" or summary.get("python") != lane["python"]:
            issues.append("SMOKE_OR_PYTHON_MISMATCH")
        if expected_runtime_digest and summary.get("runtime_sha256") != expected_runtime_digest:
            issues.append("RUNTIME_SHA_MISMATCH")
        if lane["runner"]=="native" and data.get("python_version") != "Python " + lane["python"]:
            issues.append("NATIVE_PYTHON_VERSION_MISMATCH")
        if lane["runner"]=="linux-docker" and (not str(data.get("image_id", "")).startswith("sha256:") or data.get("network")!="none" or data.get("workspace_mount")!="read_only"):
            issues.append("CONTAINER_PROVENANCE_MISMATCH")
    if data.get("state") != "passed" or data.get("release_accepted") is not False or data.get("native_windows_verified") is not False:
        issues.append("UNSUPPORTED_ACCEPTANCE_CLAIM")
    return {"id": lane["id"], "platform": lane["platform"], "python": lane["python"],
            "state": "passed" if not issues else "failed", "issues": sorted(set(issues)),
            "suite_count": checks[0].get("tests_discovered") if checks else None,
            "suite_skipped": checks[0].get("skipped") if checks else None,
            "receipt_sha256": hashlib.sha256((directory/"receipt.json").read_bytes()).hexdigest()}


def aggregate(matrix: dict, root: Path, head: str, expected_runtime_digest: str | None) -> dict:
    if matrix.get("schema_version") != 1 or not isinstance(matrix.get("required"), list):
        raise ValueError("Invalid CI matrix")
    lanes = []
    ids=set()
    for lane in matrix["required"]:
        if not isinstance(lane, dict) or not re.fullmatch(r"[A-Za-z0-9._-]+", lane.get("id", "")) or lane["id"] in ids:
            raise ValueError("Invalid/duplicate lane id")
        ids.add(lane["id"])
        d = root / lane["id"]
        if not d.is_dir() or d.is_symlink():
            lanes.append({"id": lane["id"], "state": "not_tested", "issues": ["NO_RECEIPT"]})
            continue
        try:
            data = load_json(d / "receipt.json")
            lanes.append(check_receipt(lane,data,d,head,matrix["min_tests"],expected_runtime_digest))
        except (OSError, ValueError, KeyError, TypeError):
            lanes.append({"id": lane["id"], "state": "failed", "issues": ["RECEIPT_INVALID"]})
    passed = sum(row["state"]=="passed" for row in lanes)
    return {"schema_version":1,"kind":"local_ci_matrix_report",
            "observed_at":datetime.now(timezone.utc).isoformat(),
            "source_commit":head,"required_lanes":len(lanes),"passed_lanes":passed,
            "lanes":lanes,"known_unverified":matrix.get("known_unverified", []),
            "status":"passed_with_declared_gaps" if passed==len(lanes) and lanes else "failed_or_incomplete",
            "native_windows_verified":False,"release_accepted":False,
            "limits":["All tested Linux lanes are Linux ARM64 guests, not native Windows.",
                      "The suite validates this skill, not detection performance on unseen products.",
                      "Receipt correctness depends on trusted local runner and independent review of logs."]}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs",type=Path,required=True)
    p.add_argument("--matrix",type=Path,default=Path(__file__).with_name("matrix.json"))
    p.add_argument("--expected-runtime-sha256",default=None)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    try:
        if a.out.exists():
            raise ValueError("Output exists; refusing overwrite")
        head=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True,timeout=8).strip()
        report=aggregate(load_json(a.matrix),a.runs.resolve(),head,a.expected_runtime_sha256)
        with a.out.open("x",encoding="utf-8") as f:
            json.dump(report,f,indent=2)
            f.write("\n")
        print(json.dumps({"status":report["status"],"passed":report["passed_lanes"],
                          "required":report["required_lanes"],"windows":"not_tested", "release_accepted":False}))
        return 0 if report["status"]=="passed_with_declared_gaps" else 1
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        print("Invalid local CI receipt: " + str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
