#!/usr/bin/env python3
"""Score observed skill-loading decisions against a frozen trigger manifest. Does not invoke an agent."""
import argparse
import hashlib
import json
from pathlib import Path

def score(cases,observed):
    if not isinstance(cases,dict) or not isinstance(observed,dict) or cases.get("schema_version") != 1 or observed.get("schema_version") != 1:
        raise ValueError("Invalid trigger manifest")
    raw_cases=cases.get("cases")
    if not isinstance(raw_cases,list) or not raw_cases or any(not isinstance(c,dict) or not isinstance(c.get("id"),str) or not c["id"].strip() for c in raw_cases):
        raise ValueError("Nonempty manifest with valid case IDs required")
    expected={c["id"]:c["should_trigger"] for c in raw_cases}
    if len(expected)!=len(cases["cases"]) or not all(isinstance(v,bool) for v in expected.values()):
        raise ValueError("Invalid expected labels")
    predictions=observed.get("observations")
    if not isinstance(predictions,list):
        raise ValueError("observations must be a list")
    outcomes={"tp":0,"tn":0,"fp":0,"fn":0,"not_measured":0}
    visited=set()
    run_ids=set()
    for item in predictions:
        if item.get("case_id") in visited:
            raise ValueError("Duplicate case observation")
        id=item.get("case_id");visited.add(id)
        if id not in expected or not isinstance(item.get("triggered"),bool):
            raise ValueError("Unknown case or nonboolean observation")
        if not isinstance(item.get("run_id"),str) or not item["run_id"].strip() or not isinstance(item.get("agent_session"),str) or not item["agent_session"].strip():
            raise ValueError("Missing/non-string invocation/session receipt fields")
        run_key=item["run_id"].strip()
        if run_key in run_ids:
            raise ValueError("Duplicate agent run ID")
        run_ids.add(run_key)
        truth=expected[id]
        predicted=item["triggered"]
        outcomes["tp" if truth and predicted else "tn" if not truth and not predicted else "fp" if predicted else "fn"]+=1
    outcomes["not_measured"]=len(expected)-len(predictions)
    pden=outcomes["tp"]+outcomes["fp"]
    rden=outcomes["tp"]+outcomes["fn"]
    digest=hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return {"schema_version":1,"kind":"skill_trigger_score","manifest_canonical_sha256":digest,"confusion":outcomes,
            "precision":outcomes["tp"]/pden if pden else None,
            "recall":outcomes["tp"]/rden if rden else None,
            "comparison_complete":outcomes["not_measured"]==0,
            "evidence_status":"self_reported_receipts_not_identity_verified",
            "limitations":["Run/session fields are assertions; independent host logs must verify actual skill loading.",
                           "Scoring observed decisions is not an automated deployment or an agent run."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--observations",type=Path,required=True)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    try:
        from coverage_critic import read_json
        data=score(read_json(a.manifest),read_json(a.observations))
        s=json.dumps(data,indent=2)+"\n"
        if a.out:
            with a.out.open("x") as f:f.write(s)
        else:print(s,end="")
        return 0 if data["comparison_complete"] else 1
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print("evaluate_triggers: "+str(exc),file=__import__('sys').stderr);return 2
if __name__=="__main__":raise SystemExit(main())
