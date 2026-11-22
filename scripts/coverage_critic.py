#!/usr/bin/env python3
"""Independent, deterministic audit-scope critic. No product actions or package installs."""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import sys
from collections import Counter

STATES = {"passed", "failed", "blocked", "not_tested", "unknown"}
LEVELS = {"P0", "P1", "P2", "P3"}
MAX_SIZE = 2 * 1024 * 1024

def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: " + key)
        out[key] = value
    return out

def read_json(path):
    p = pathlib.Path(path).resolve()
    if not p.is_file() or p.stat().st_size > MAX_SIZE:
        raise ValueError("Missing or oversize input")
    return json.loads(p.read_text(), object_pairs_hook=unique_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite")))

def nonblank(value):
    return isinstance(value, str) and bool(value.strip())

def critique(contract, evidence_root=None):
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValueError("expected schema_version=1 object")
    if not nonblank(contract.get("scope_id")):
        raise ValueError("scope_id is required")
    rev = contract.get("revision")
    if not nonblank(rev):
        raise ValueError("revision missing")
    cases = contract.get("required_cases")
    results = contract.get("observations")
    if not isinstance(cases, list) or not isinstance(results, list):
        raise ValueError("required_cases and observations must be arrays")
    if len(cases) > 20000 or len(results) > 20000:
        raise ValueError("scope exceeds 20000 cases")
    issues, ids, seen = [], {}, set()
    root=pathlib.Path(evidence_root).resolve() if evidence_root is not None else None
    evidence_validated = root is not None and bool(results)
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case must be object")
        cid = case.get("id")
        if not nonblank(cid) or cid in ids:
            raise ValueError("missing/duplicate required case id")
        if case.get("priority") not in LEVELS:
            raise ValueError("priority must be P0..P3")
        dims = case.get("dimensions")
        if not isinstance(dims, dict) or not all(nonblank(dims.get(x)) for x in ("role", "state", "platform")):
            raise ValueError("dimensions require role, state, platform")
        if not nonblank(case.get("invariant")):
            raise ValueError("invariant missing")
        if type(case.get("oracle_required")) is not bool:
            raise ValueError("oracle_required must be Boolean")
        ids[cid] = case
    for obs in results:
        if not isinstance(obs, dict):
            raise ValueError("observation must be object")
        cid = obs.get("case_id")
        if not nonblank(cid) or cid in seen:
            raise ValueError("missing/duplicate observation case_id")
        seen.add(cid)
        if cid not in ids:
            issues.append({"code":"UNSCOPED_CLAIM", "case_id":cid})
            continue
        if obs.get("status") not in STATES:
            raise ValueError("invalid observation status")
        case = ids[cid]
        if obs.get("revision") != rev:
            issues.append({"code":"STALE_REVISION", "case_id":cid})
        if obs.get("dimensions") != case["dimensions"]:
            issues.append({"code":"DIMENSION_MISMATCH", "case_id":cid})
        if obs["status"] in ("passed", "failed"):
            evidence = obs.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                issues.append({"code":"UNPROVEN_OUTCOME", "case_id":cid})
            else:
                for e in evidence:
                    if not isinstance(e, dict) or not nonblank(e.get("path")) or not isinstance(e.get("sha256"), str) or len(e["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in e["sha256"]):
                        issues.append({"code":"UNBOUND_EVIDENCE", "case_id":cid})
                        break
                    path=pathlib.Path(e["path"])
                    if path.is_absolute() or ".." in path.parts or "\\" in e["path"]:
                        issues.append({"code":"EVIDENCE_PATH_ESCAPE", "case_id":cid})
                        break
                    if root is None:
                        issues.append({"code":"EVIDENCE_BYTES_UNCHECKED", "case_id":cid})
                        break
                    real=(root/path).resolve()
                    if real==root or root not in real.parents or not real.is_file() or not (0 < real.stat().st_size <= 8_388_608):
                        issues.append({"code":"EVIDENCE_BYTES_INVALID", "case_id":cid})
                        break
                    if hashlib.sha256(real.read_bytes()).hexdigest()!=e["sha256"]:
                        issues.append({"code":"EVIDENCE_DIGEST_MISMATCH", "case_id":cid})
                        break
        if case["priority"] in ("P0", "P1") and obs["status"] in ("passed","failed"):
            author, reviewer = obs.get("author"), obs.get("reviewer")
            if not nonblank(author) or not nonblank(reviewer) or author.strip() == reviewer.strip():
                issues.append({"code":"NO_DISTINCT_REVIEWER", "case_id":cid})
        if obs["status"] == "passed" and case.get("oracle_required") and not nonblank(obs.get("independent_oracle")):
            issues.append({"code":"MISSING_ORACLE", "case_id":cid})
    observed = {x["case_id"]: x for x in results if x.get("case_id") in ids}
    status_counts = Counter()
    for cid, case in ids.items():
        obs = observed.get(cid)
        status = obs["status"] if obs else "not_tested"
        status_counts[status] += 1
        if not obs:
            issues.append({"code":"MISSING_OBSERVATION", "case_id":cid, "priority":case["priority"]})
        if case["priority"] in ("P0", "P1") and status in ("blocked", "not_tested", "unknown"):
            issues.append({"code":"CRITICAL_GAP", "case_id":cid, "priority":case["priority"]})
    all_passed = len(cases)>0 and status_counts["passed"]==len(cases)
    no_invalid = len(issues)==0
    evidence_codes = {"UNPROVEN_OUTCOME", "UNBOUND_EVIDENCE", "EVIDENCE_PATH_ESCAPE", "EVIDENCE_BYTES_UNCHECKED", "EVIDENCE_BYTES_INVALID", "EVIDENCE_DIGEST_MISMATCH"}
    evidence_validated = evidence_validated and bool(status_counts["passed"]+status_counts["failed"]) and all(i["code"] not in evidence_codes for i in issues)
    return {"schema_version":1,"kind":"independent_scope_critique",
            "scope_id":contract.get("scope_id"),"revision":rev,
            "required_total":len(cases),"observed_total":len(observed),
            "status_counts":dict(sorted(status_counts.items())),
            "critical_gap_count":sum(i["code"]=="CRITICAL_GAP" for i in issues),
            "issues":issues, "scope_review_passed":bool(all_passed and no_invalid and evidence_validated),"evidence_bytes_verified":evidence_validated,
            "release_accepted":False,
            "limits":["This analyzes supplied records, not real product behavior.",
                      "Reviewer strings and evidence hashes do not authenticate a person or prove evidence truth.",
                      "The inventory may omit unknown features; separately challenge its completeness."]}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path)
    args=ap.parse_args()
    try:
        data=critique(read_json(args.input), args.input.resolve().parent)
        payload=json.dumps(data,indent=2,ensure_ascii=False)+"\n"
        if args.out:
            with args.out.open("x") as f:f.write(payload)
        else:sys.stdout.write(payload)
        return 0 if data["scope_review_passed"] else 1
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print("Invalid coverage contract: "+str(exc), file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
