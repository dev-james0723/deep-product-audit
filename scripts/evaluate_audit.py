#!/usr/bin/env python3
"""Score recorded, independently judged audit runs; never run product commands.

This is a case-level evaluator, not an automatic semantic/security oracle.
The manifest's oracle is evaluator-only. See references/evaluation.md.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

DEFAULT_MANIFEST = None  # Grading manifests are supplied externally, never bundled.
OUTCOMES = {"bug", "clean", "blocked", "unknown"}
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024


class InputError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


@contextmanager
def open_regular(path, limit):
    """Open bounded regular files without blocking on a substituted FIFO."""
    path = Path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise InputError(f"Expected a regular file no larger than {limit} bytes: {path.name}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise InputError(f"Expected a regular file no larger than {limit} bytes: {path.name}")
        yield handle


def load_json(path):
    with open_regular(path, MAX_JSON_BYTES) as handle:
        raw = handle.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise InputError(f"JSON exceeds {MAX_JSON_BYTES} bytes")
    def invalid_constant(value):
        raise InputError(f"Non-finite JSON number: {value}")
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise InputError(f"Non-finite JSON number: {value}")
        return result
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                            parse_constant=invalid_constant, parse_float=finite_float)
    except RecursionError as exc:
        raise InputError("JSON nesting exceeds the parser limit") from exc
    pending = [(result, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 128:
            raise InputError("JSON nesting exceeds 128 levels")
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    return result


def obj(value, label):
    if not isinstance(value, dict):
        raise InputError(f"{label} must be an object")
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise InputError(f"{label} must be a nonempty string of at most 4000 characters")
    return value


def number(value, label):
    try:
        valid = value is None or (type(value) in (int, float) and math.isfinite(value) and value >= 0)
    except OverflowError:
        valid = False
    if not valid:
        raise InputError(f"{label} must be null or a finite nonnegative number")
    return value


def evidence_valid(evidence, root):
    """Check real hashed local artifacts; do not interpret them or follow escapes."""
    if not isinstance(evidence, list) or not evidence:
        return False
    root = Path(root).resolve()
    for item in evidence:
        if not isinstance(item, dict):
            return False
        name, digest = item.get("path"), item.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str):
            return False
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or "\\" in name or not re.fullmatch(r"[a-f0-9]{64}", digest):
            return False
        try:
            path = (root / rel).resolve()
            if path == root or not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > MAX_EVIDENCE_BYTES:
                return False
            h = hashlib.sha256()
            size = 0
            with open_regular(path, MAX_EVIDENCE_BYTES) as handle:
                for block in iter(lambda: handle.read(65536), b""):
                    size += len(block)
                    if size > MAX_EVIDENCE_BYTES:
                        return False
                    h.update(block)
            if h.hexdigest() != digest:
                return False
        except (OSError, RuntimeError, ValueError):
            return False
    return True


def verify_review(review, author, root):
    if not isinstance(review, dict):
        return False
    reviewer = review.get("reviewer")
    return (isinstance(reviewer, str) and bool(reviewer.strip()) and reviewer.strip() != author.strip()
            and evidence_valid(review.get("evidence"), root))


def manifest_cases(manifest):
    obj(manifest, "manifest")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise InputError("Unsupported manifest schema_version")
    text(manifest.get("benchmark_id"), "benchmark_id")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise InputError("Manifest cases must be a nonempty array")
    result = {}
    for case in cases:
        obj(case, "case")
        case_id = text(case.get("id"), "case.id")
        if case_id in result:
            raise InputError(f"Duplicate manifest case: {case_id}")
        text(case.get("prompt"), "case.prompt")
        oracle = obj(case.get("oracle"), "case.oracle")
        if not isinstance(oracle.get("outcome"), str) or oracle["outcome"] not in OUTCOMES:
            raise InputError(f"Invalid oracle outcome for {case_id}")
        if oracle["outcome"] == "bug":
            text(oracle.get("defect_key"), "oracle.defect_key")
        result[case_id] = case
    return result


def manifest_digest(manifest):
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_template(manifest):
    return {
        "schema_version": 1, "benchmark_id": manifest["benchmark_id"],
        "manifest_sha256": manifest_digest(manifest),
        "run_id": "replace-run-id", "author": "replace-agent-id",
        "skill_revision": "replace-revision", "model": "replace-model-version",
        "environment_id": "replace-frozen-fixture-environment",
        "budget_id": "replace-budget-policy", "repetition": 1,
        "observations": [
            {"case_id": case_id, "attempted": False, "outcome": "unknown", "evidence": [],
             "findings": [], "duration_seconds": None, "cost_usd": None}
            for case_id in manifest_cases(manifest)
        ],
    }


def score_run(manifest, run, root):
    cases = manifest_cases(manifest)
    obj(run, "run")
    if type(run.get("schema_version")) is not int or run["schema_version"] != 1 or run.get("benchmark_id") != manifest["benchmark_id"]:
        raise InputError("Run schema/benchmark does not match manifest")
    if run.get("manifest_sha256") != manifest_digest(manifest):
        raise InputError("Run manifest_sha256 does not match the frozen grading manifest")
    for field in ("run_id", "author", "skill_revision", "model", "environment_id", "budget_id"):
        text(run.get(field), field)
    if type(run.get("repetition")) is not int or run["repetition"] < 1:
        raise InputError("repetition must be a positive integer")
    observations = run.get("observations")
    if not isinstance(observations, list):
        raise InputError("observations must be an array")
    counts = {key: 0 for key in (
        "attempted", "missing", "unattempted", "unknown", "blocked", "unproven_cases",
        "correct_classifications", "detected_bug_cases", "true_findings", "false_findings",
        "unproven_findings", "duplicate_true_findings", "verified_closures", "false_closures",
        "unproven_closures", "duplicate_verified_closures", "unsafe_clear_claims")}
    seen, details = set(), []
    measured = {"duration_seconds": [], "cost_usd": []}
    for observation in observations:
        obj(observation, "observation")
        case_id = text(observation.get("case_id"), "observation.case_id")
        if case_id not in cases or case_id in seen:
            raise InputError(f"Unknown or duplicate observation case_id: {case_id}")
        seen.add(case_id)
        if type(observation.get("attempted")) is not bool:
            raise InputError(f"attempted must be boolean for {case_id}")
        outcome = observation.get("outcome")
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            raise InputError(f"Invalid outcome for {case_id}")
        for field in measured:
            value = number(observation.get(field), f"{case_id}.{field}")
            if value is not None:
                measured[field].append(value)
        findings = observation.get("findings")
        if not isinstance(findings, list):
            raise InputError(f"findings must be an array for {case_id}")
        if not observation["attempted"] and (findings or outcome != "unknown"):
            raise InputError(f"Unattempted case cannot claim an outcome or finding: {case_id}")
        counts["attempted" if observation["attempted"] else "unattempted"] += 1
        if outcome in ("unknown", "blocked"):
            counts[outcome] += 1
        artifact_ok = evidence_valid(observation.get("evidence"), root)
        if observation["attempted"] and not artifact_ok:
            counts["unproven_cases"] += 1
        oracle = cases[case_id]["oracle"]
        finding_ids, matched, unproven, false = set(), False, 0, 0
        closure_matched = False
        for finding in findings:
            obj(finding, "finding")
            finding_id = text(finding.get("id"), "finding.id")
            if finding_id in finding_ids:
                raise InputError(f"Duplicate finding ID in {case_id}: {finding_id}")
            finding_ids.add(finding_id)
            text(finding.get("defect_key"), "finding.defect_key")
            verdict = finding.get("verdict")
            if not isinstance(verdict, str) or verdict not in {"confirmed", "rejected", "inconclusive"}:
                raise InputError("finding.verdict must be an independent grader verdict")
            review_ok = verify_review(finding.get("verification"), run["author"], root)
            is_true = False
            if not review_ok or verdict == "inconclusive":
                counts["unproven_findings"] += 1
                unproven += 1
            elif verdict == "confirmed" and oracle["outcome"] == "bug" and finding["defect_key"] == oracle["defect_key"]:
                is_true = True
                counts["duplicate_true_findings" if matched else "true_findings"] += 1
                matched = True
            else:
                counts["false_findings"] += 1
                false += 1
            closure = finding.get("closure")
            if closure is not None:
                obj(closure, "finding.closure")
                if type(closure.get("claimed")) is not bool:
                    raise InputError("closure.claimed must be boolean")
                if closure["claimed"]:
                    check = closure.get("verdict")
                    if not isinstance(check, str) or check not in {"fixed", "still_failing", "inconclusive"}:
                        raise InputError("Invalid independent closure verdict")
                    closure_ok = verify_review(closure.get("verification"), run["author"], root)
                    if not closure_ok or check == "inconclusive":
                        counts["unproven_closures"] += 1
                    elif check == "still_failing" or not is_true:
                        counts["false_closures"] += 1
                    else:
                        # Multiple records for the same case/defect cannot create
                        # additional repairs or a spurious paired-run improvement.
                        counts["duplicate_verified_closures" if closure_matched else "verified_closures"] += 1
                        closure_matched = True
        if matched:
            counts["detected_bug_cases"] += 1
        supported = observation["attempted"] and artifact_ok
        correct = supported and outcome == oracle["outcome"] and not unproven and not false
        if outcome == "bug":
            correct = correct and matched
            if not findings:
                counts["unproven_findings"] += 1
        if outcome == "clean" and oracle["outcome"] != "clean":
            counts["unsafe_clear_claims"] += 1
        counts["correct_classifications"] += int(correct)
        details.append({"case_id": case_id, "expected": oracle["outcome"], "observed": outcome,
                        "evidence_valid": artifact_ok, "correct": bool(correct)})
    counts["missing"] = len(cases) - len(seen)
    bug_cases = sum(c["oracle"]["outcome"] == "bug" for c in cases.values())
    judged = counts["true_findings"] + counts["false_findings"]
    complete = not any(counts[k] for k in ("missing", "unattempted", "unproven_cases", "unproven_findings", "unproven_closures"))
    return {
        "run_id": run["run_id"], "complete_record": complete, "counts": counts,
        "known_bug_recall": {"numerator": counts["detected_bug_cases"], "denominator": bug_cases,
                             "value": counts["detected_bug_cases"] / bug_cases if bug_cases else None},
        "judged_finding_precision": {"numerator": counts["true_findings"], "denominator": judged,
                                     "value": counts["true_findings"] / judged if judged else None},
        "measurements": {field: {"observed_cases": len(values), "total": sum(values) if values else None,
                                  "complete": len(values) == len(cases)} for field, values in measured.items()},
        "cases": details,
        "limits": ["Scores rely on supplied independent grader judgments and a frozen manifest; hashes prove bytes, not truth.",
                   "This is known-case recall, not unknown-bug coverage or a product release gate.",
                   "One paired repetition cannot establish statistical superiority."],
    }


def compare(manifest, baseline, candidate, baseline_root, candidate_root):
    before = score_run(manifest, baseline, baseline_root)
    after = score_run(manifest, candidate, candidate_root)
    mismatches = [field for field in ("model", "environment_id", "budget_id", "repetition")
                  if baseline[field] != candidate[field]]
    distinct_runs = baseline["run_id"] != candidate["run_id"]
    comparable = distinct_runs and not mismatches and before["complete_record"] and after["complete_record"]
    return {"schema_version": 1, "benchmark_id": manifest["benchmark_id"],
            "comparable": comparable, "mismatched_context": mismatches,
            "distinct_run_ids": distinct_runs,
            "baseline": before, "candidate": after,
            "deltas": {key: after["counts"][key] - before["counts"][key]
                       for key in before["counts"]} if comparable else None,
            "performance_claim": "recorded paired comparison only; no general improvement claim"}


def emit(value, output=None):
    rendered = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if output:
        with Path(output).open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    else:
        print(rendered, end="")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="External grader-owned manifest; never expose it to an evaluated agent")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prompts", "template"):
        child = sub.add_parser(name)
        child.add_argument("--out", type=Path, required=True)
    child = sub.add_parser("score")
    child.add_argument("--baseline", type=Path, required=True)
    child.add_argument("--candidate", type=Path, required=True)
    child.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = load_json(args.manifest)
        cases = manifest_cases(manifest)
        if args.command == "prompts":
            emit({"benchmark_id": manifest["benchmark_id"], "cases": [
                {"id": case_id, "prompt": case["prompt"]} for case_id, case in cases.items()]}, args.out)
        elif args.command == "template":
            emit(make_template(manifest), args.out)
        else:
            result = compare(manifest, load_json(args.baseline), load_json(args.candidate),
                             args.baseline.parent, args.candidate.parent)
            emit(result, args.out)
            return 0 if result["comparable"] else 1
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
