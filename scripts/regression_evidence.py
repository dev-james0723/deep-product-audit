#!/usr/bin/env python3
"""Validate supplied regression records without executing product code or commands."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
import json

# CLI use must not modify a checksum-verified runtime installation on import.
sys.dont_write_bytecode = True
from evaluate_audit import InputError, evidence_valid, load_json, obj, text, emit


def runs_digest(runs):
    raw = json.dumps(runs, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_regression(document, root):
    obj(document, "comparison")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise InputError("Unsupported comparison schema_version")
    for field in ("case_id", "test_id", "assertion_id", "environment_id", "buggy_revision", "fixed_revision", "author", "verifier"):
        text(document.get(field), field)
    for field in ("test_sha256", "oracle_sha256"):
        if not isinstance(document.get(field), str) or not re.fullmatch(r"[a-f0-9]{64}", document[field]):
            raise InputError(f"{field} must be a SHA-256 digest")
    runs = document.get("runs")
    if not isinstance(runs, list):
        raise InputError("runs must be an array")
    reasons = []
    phases = {"before": [], "after": []}
    seen = set()
    if document["buggy_revision"] == document["fixed_revision"]:
        reasons.append("identical_revisions")
    if document["author"].strip() == document["verifier"].strip():
        reasons.append("no_independent_verifier")
    for run in runs:
        obj(run, "run")
        phase = run.get("phase")
        if not isinstance(phase, str) or phase not in phases:
            raise InputError("phase must be before or after")
        if type(run.get("repetition")) is not int or run["repetition"] < 1:
            raise InputError("run repetition must be a positive integer")
        identity = (phase, run["repetition"])
        if identity in seen:
            raise InputError(f"Duplicate repetition: {identity}")
        seen.add(identity)
        outcome = run.get("outcome")
        if not isinstance(outcome, str) or outcome not in {"passed", "failed", "skipped", "error", "timeout"}:
            raise InputError("Invalid run outcome")
        expected_revision = document["buggy_revision" if phase == "before" else "fixed_revision"]
        if run.get("revision") != expected_revision:
            reasons.append("revision_mismatch")
        for field in ("test_id", "test_sha256", "oracle_sha256", "environment_id"):
            if run.get(field) != document[field]:
                reasons.append(f"{field}_mismatch")
        if not evidence_valid(run.get("evidence"), root):
            reasons.append("missing_or_invalid_evidence")
        kind = run.get("failure_kind")
        if kind not in (None, "assertion", "import", "build", "infra", "other"):
            raise InputError("failure_kind must identify assertion, import, build, infra, other, or null")
        if outcome == "passed" and (kind is not None or run.get("assertion_id") is not None):
            raise InputError("A passing run cannot carry a failure classification")
        if outcome == "failed" and kind is None:
            reasons.append("unclassified_failure")
        if outcome in {"error", "timeout"} or kind in {"import", "build", "infra", "other"}:
            reasons.append("runner_or_environment_failure")
        if outcome == "skipped":
            reasons.append("skipped_test")
        if phase == "before" and outcome == "failed" and kind == "assertion" and run.get("assertion_id") != document["assertion_id"]:
            reasons.append("unrelated_assertion_failure")
        phases[phase].append(run)
    for phase, records in phases.items():
        if not records:
            reasons.append(f"missing_{phase}_runs")
        elif len(records) < 2:
            reasons.append(f"insufficient_{phase}_repetitions")
        if len({(r["outcome"], r.get("failure_kind"), r.get("assertion_id")) for r in records}) > 1:
            reasons.append(f"inconsistent_{phase}_results")
    if any(r["outcome"] == "passed" for r in phases["before"]):
        reasons.append("test_passed_on_buggy_revision")
    if any(r["outcome"] != "passed" for r in phases["after"]):
        reasons.append("fixed_revision_not_passing")
    if any(r["outcome"] != "failed" or r.get("failure_kind") != "assertion" for r in phases["before"]):
        reasons.append("buggy_revision_not_reproduced_by_assertion")
    phase_digests = {
        phase: {item.get("sha256") for run in records
                for item in (run.get("evidence") if isinstance(run.get("evidence"), list) else [])
                if isinstance(item, dict) and isinstance(item.get("sha256"), str)}
        for phase, records in phases.items()
    }
    if phase_digests["before"] & phase_digests["after"]:
        reasons.append("reused_before_after_evidence")
    verification = document.get("verification")
    if not isinstance(verification, dict) or not evidence_valid([verification], root):
        reasons.append("missing_or_invalid_verification_record")
    else:
        if verification["sha256"] in phase_digests["before"] | phase_digests["after"]:
            reasons.append("verification_reuses_execution_evidence")
        try:
            review = load_json(Path(root) / verification["path"])
            obj(review, "verification record")
            if type(review.get("schema_version")) is not int or review["schema_version"] != 1 or review.get("kind") != "independent_regression_review":
                reasons.append("invalid_verification_record_kind")
            if review.get("reviewer") != document["verifier"] or review.get("author") != document["author"]:
                reasons.append("verification_actor_mismatch")
            for field in ("case_id", "test_id", "assertion_id", "test_sha256", "oracle_sha256", "environment_id", "buggy_revision", "fixed_revision"):
                if review.get(field) != document[field]:
                    reasons.append(f"verification_{field}_mismatch")
            if review.get("runs_sha256") != runs_digest(runs):
                reasons.append("verification_does_not_bind_current_runs")
            if review.get("verdict") != "confirmed":
                reasons.append("independent_verification_not_confirmed")
        except (OSError, ValueError, TypeError):
            reasons.append("unreadable_verification_record")
    reasons = sorted(set(reasons))
    accepted = not reasons
    return {
        "schema_version": 1, "case_id": document["case_id"], "accepted": accepted,
        "classification": "verified_regression_record" if accepted else "not_verified",
        "reasons": reasons, "before_runs": len(phases["before"]), "after_runs": len(phases["after"]),
        "test_id": document["test_id"], "buggy_revision": document["buggy_revision"],
        "fixed_revision": document["fixed_revision"],
        "verification_record_sha256": verification.get("sha256") if accepted else None,
        "limits": ["Consumes recorded runner outcomes and an independent review; it does not run or semantically inspect the test.",
                   "Two consistent repetitions screen obvious instability; they do not prove a test is never flaky.",
                   "This evidence is not deployment or full-product acceptance."],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = check_regression(load_json(args.comparison), args.comparison.parent)
        emit(result, args.out)
        return 0 if result["accepted"] else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
