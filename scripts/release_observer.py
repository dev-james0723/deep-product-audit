#!/usr/bin/env python3
"""Read-only post-release evidence gate. Never deploys, sends traffic or rolls back."""
import argparse
import datetime as dt
import re
import hashlib
import json
import math
import pathlib
import sys

ALLOWED={"passed","failed","blocked","not_tested","unknown"}

def nonblank(x):return isinstance(x,str) and bool(x.strip())

def valid_digest(x):
    return isinstance(x,str) and len(x)==64 and all(c in "0123456789abcdef" for c in x)

def check_evidence(items,root):
    if not isinstance(items,list) or not items:return False
    for item in items:
        if not isinstance(item,dict) or not nonblank(item.get("path")) or not valid_digest(item.get("sha256")):
            return False
        rel=pathlib.Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts:return False
        path=(root/rel).resolve()
        if path==root or root not in path.parents or not path.is_file() or not (0 < path.stat().st_size <= 8_388_608):
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            return False
    return True

def typed_proof(items,root,kind,expected):
    if not check_evidence(items,root):return False
    from coverage_critic import read_json
    for item in items:
        try:
            path=(root/item["path"]).resolve()
            data=read_json(path)
        except (ValueError,TypeError,OSError,OverflowError):
            continue
        if isinstance(data,dict) and data.get("kind")==kind and all(data.get(k)==v for k,v in expected.items()):
            return True
    return False

def number(x,minimum=None,maximum=None):
    ok=isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
    if ok and minimum is not None:ok=ok and x>=minimum
    if ok and maximum is not None:ok=ok and x<=maximum
    return ok

def analyze(record,root):
    root=pathlib.Path(root).resolve()
    if not isinstance(record,dict) or record.get("schema_version")!=1:
        raise ValueError("expected a schema_version 1 record")
    issues=[]
    identity=record.get("identity")
    if not isinstance(identity,dict):
        raise ValueError("identity object required")
    src=identity.get("source_revision")
    dep=identity.get("deployed_source_revision")
    obs=identity.get("observed_source_revision")
    art=identity.get("artifact_sha256")
    if not isinstance(src,str) or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})",src) is None or dep!=src or obs!=src or not valid_digest(art):
        issues.append({"code":"REVISION_OR_ARTIFACT_UNPROVEN"})
    if not nonblank(identity.get("environment")):
        issues.append({"code":"ENVIRONMENT_UNKNOWN"})
    deployed_at=None
    try:
        deployed_at=dt.datetime.fromisoformat(identity["deployed_at"].replace("Z","+00:00"))
        if deployed_at.utcoffset() is None:deployed_at=None
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError):pass
    if deployed_at is None:
        issues.append({"code":"DEPLOYMENT_TIME_UNVERIFIED"})
    thresholds=record.get("thresholds")
    if not isinstance(thresholds,dict):
        raise ValueError("thresholds object required")
    for k,minv,maxv in (("max_error_ratio",0,1),("max_p95_ms",0,None),("max_dropped_iterations",0,None),("min_requests_per_window",1,None)):
        if not number(thresholds.get(k),minv,maxv):
            raise ValueError("invalid threshold "+k)
    used_evidence=set()
    def distinct_evidence(items,phase):
        for item in items or []:
            if isinstance(item,dict) and isinstance(item.get("sha256"),str):
                digest=item["sha256"]
                if digest in used_evidence:issues.append({"code":"RECYCLED_PHASE_EVIDENCE","id":phase})
                used_evidence.add(digest)
    if not typed_proof(identity.get("evidence"),root,"release_identity",
        {"source_revision":src,"deployed_source_revision":dep,"observed_source_revision":obs,
         "artifact_sha256":art,"environment":identity.get("environment"),
         "deployed_at":identity.get("deployed_at")}):
        issues.append({"code":"IDENTITY_EVIDENCE_UNVERIFIED"})
    else:distinct_evidence(identity.get("evidence"),"identity")
    probes=record.get("probes")
    if not isinstance(probes,list) or not probes:
        issues.append({"code":"NO_SMOKE_PROBES"})
        probes=[]
    probe_ids=set()
    for probe in probes:
        if not isinstance(probe,dict) or not nonblank(probe.get("id")) or probe["id"] in probe_ids:
            raise ValueError("duplicate/invalid probe id")
        probe_ids.add(probe["id"])
        if probe.get("status") not in ALLOWED:raise ValueError("invalid probe status")
        if probe["status"]!="passed":
            issues.append({"code":"PROBE_NOT_PASSED","id":probe["id"],"status":probe["status"]})
        if not typed_proof(probe.get("evidence"),root,"synthetic_journey",
             {"id":probe.get("id"),"status":probe.get("status"),
              "observed_source_revision":src}):
            issues.append({"code":"PROBE_EVIDENCE_INVALID","id":probe["id"]})
        else:distinct_evidence(probe.get("evidence"),probe["id"])
    windows=record.get("windows")
    if not isinstance(windows,list) or len(windows)<2:
        issues.append({"code":"INSUFFICIENT_MONITORING_WINDOWS"})
        windows=windows if isinstance(windows,list) else []
    win_ids=set()
    ranges=[]
    for window in windows:
        if not isinstance(window,dict) or not nonblank(window.get("id")) or window["id"] in win_ids:
            raise ValueError("duplicate/invalid window id")
        win_ids.add(window["id"])
        try:
            start=dt.datetime.fromisoformat(window["start_at"].replace("Z","+00:00"))
            end=dt.datetime.fromisoformat(window["end_at"].replace("Z","+00:00"))
            if start.utcoffset() is None or end.utcoffset() is None or end<=start:
                raise ValueError("Invalid bounds")
            ranges.append((start,end,window["id"]))
            if deployed_at is None or start<deployed_at:
                issues.append({"code":"PRE_DEPLOYMENT_WINDOW","id":window["id"]})
        except (ValueError,KeyError,TypeError,AttributeError):
            issues.append({"code":"INVALID_WINDOW_TIMESTAMP","id":window["id"]})
        if window.get("observed_source_revision")!=src:
            issues.append({"code":"WINDOW_BUILD_MISMATCH","id":window["id"]})
        n,err,dropped,p95=(window.get(x) for x in ("requests","errors","dropped_iterations","p95_ms"))
        if not (isinstance(n,int) and not isinstance(n,bool) and isinstance(err,int) and not isinstance(err,bool)
                and isinstance(dropped,int) and not isinstance(dropped,bool)
                and n>=0 and 0<=err<=n and dropped>=0 and number(p95,0)):
            raise ValueError("invalid measured window fields")
        if n<thresholds["min_requests_per_window"]:
            issues.append({"code":"LOW_SAMPLE","id":window["id"],"count":n})
        if n==0 or err/n>thresholds["max_error_ratio"]:
            issues.append({"code":"ERROR_BUDGET_BREACH","id":window["id"]})
        if p95>thresholds["max_p95_ms"]:
            issues.append({"code":"P95_BREACH","id":window["id"]})
        if dropped>thresholds["max_dropped_iterations"]:
            issues.append({"code":"DROPPED_ITERATIONS","id":window["id"]})
        if not typed_proof(window.get("evidence"),root,"telemetry_window",
             {"id":window.get("id"),"start_at":window.get("start_at"),"end_at":window.get("end_at"),
              "observed_source_revision":window.get("observed_source_revision"),
              "requests":n,"errors":err,"p95_ms":p95,"dropped_iterations":dropped}):
            issues.append({"code":"WINDOW_EVIDENCE_INVALID","id":window["id"]})
        else:distinct_evidence(window.get("evidence"),window["id"])
    ranges.sort(key=lambda x:x[0])
    for previous,current in zip(ranges,ranges[1:]):
        if current[0]<previous[1]:
            issues.append({"code":"OVERLAPPING_MONITORING_WINDOWS","id":current[2]})
    rollback=record.get("rollback")
    if not isinstance(rollback,dict) or rollback.get("verified") is not True or not nonblank(rollback.get("run_id")) or rollback.get("status")!="passed" or not typed_proof(rollback.get("evidence"),root,"rollback_rehearsal",
        {"run_id":rollback.get("run_id"),"status":rollback.get("status"),
         "observed_source_revision":src}):
        issues.append({"code":"ROLLBACK_REHEARSAL_UNVERIFIED"})
    else:distinct_evidence(rollback.get("evidence"),"rollback")
    return {"schema_version":1,"kind":"post_release_observation_evaluation",
            "identity":identity,"probes_considered":len(probes),"windows_considered":len(windows),
            "issues":issues,"observation_gate_eligible":not issues,
            "release_accepted":False,"deployment_authorized":False,
            "limits":["Checks supplied measurements and local evidence hashes, not the running production service.",
                      "Eligible observation evidence is not deployment permission or an independent runtime claim.",
                      "A reviewer must confirm source/artifact/telemetry authenticity and rollback behavior."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("contract",type=pathlib.Path)
    p.add_argument("--out",type=pathlib.Path)
    args=p.parse_args()
    try:
        path=args.contract.resolve()
        if not path.is_file() or path.stat().st_size>2_097_152:raise ValueError("input unavailable/oversize")
        from coverage_critic import read_json
        result=analyze(read_json(path),path.parent)
        data=json.dumps(result,indent=2)+"\n"
        if args.out:
            with args.out.open("x") as f:f.write(data)
        else:print(data,end="")
        return 0 if result["observation_gate_eligible"] else 1
    except (ValueError,OSError,TypeError,KeyError,ZeroDivisionError) as exc:
        print("release_observer: "+str(exc),file=sys.stderr)
        return 2
if __name__=="__main__":raise SystemExit(main())
