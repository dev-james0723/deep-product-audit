import unittest
import tempfile
import pathlib
import hashlib
import json
from release_observer import analyze

SOURCE = "b"*40
DEPLOYED = "2026-11-21T17:55:00-05:00"

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.dir=pathlib.Path(self.t.name)
    def evidence(self,name,record):
        path=self.dir/(name+".json")
        path.write_text(json.dumps(record,sort_keys=True))
        return [{"path":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}]
    def contract(self):
        identity={"source_revision":SOURCE,"deployed_source_revision":SOURCE,
                  "observed_source_revision":SOURCE,"artifact_sha256":"a"*64,
                  "environment":"staging","deployed_at":DEPLOYED}
        identity["evidence"]=self.evidence("identity",dict(identity,kind="release_identity"))
        probe={"id":"p1","status":"passed"}
        probe["evidence"]=self.evidence("journey",dict(probe,kind="synthetic_journey",
                                                      observed_source_revision=SOURCE))
        window1={"id":"w1","start_at":"2026-11-21T18:00:00-05:00",
                 "end_at":"2026-11-21T18:05:00-05:00","observed_source_revision":SOURCE,
                 "requests":100,"errors":0,"p95_ms":40,"dropped_iterations":0}
        window2={"id":"w2","start_at":"2026-11-21T18:05:00-05:00",
                 "end_at":"2026-11-21T18:10:00-05:00","observed_source_revision":SOURCE,
                 "requests":100,"errors":0,"p95_ms":50,"dropped_iterations":0}
        for idx,win in enumerate((window1,window2),1):
            win["evidence"]=self.evidence("window"+str(idx),dict(win,kind="telemetry_window"))
        rollback={"verified":True,"run_id":"rehearsal-1","status":"passed"}
        rollback["evidence"]=self.evidence("rollback",dict(rollback,kind="rollback_rehearsal",
                                                           observed_source_revision=SOURCE))
        return {"schema_version":1,"identity":identity,
                "thresholds":{"max_error_ratio":0.01,"max_p95_ms":200,
                              "max_dropped_iterations":0,"min_requests_per_window":50},
                "probes":[probe],"windows":[window1,window2],"rollback":rollback}
    def codes(self,record):
        return [x["code"] for x in analyze(record,self.dir)["issues"]]
    def test_eligible_does_not_authorize_release(self):
        x=analyze(self.contract(),self.dir)
        self.assertTrue(x["observation_gate_eligible"])
        self.assertFalse(x["release_accepted"])
    def test_stale_runtime_rejected(self):
        x=self.contract();x["identity"]["observed_source_revision"]="c"*40
        self.assertIn("REVISION_OR_ARTIFACT_UNPROVEN",self.codes(x))
    def test_low_samples_rejected(self):
        x=self.contract();x["windows"][0]["requests"]=1
        self.assertIn("LOW_SAMPLE",self.codes(x))
    def test_missing_rollback_rejected(self):
        x=self.contract();x["rollback"]["verified"]=False
        self.assertIn("ROLLBACK_REHEARSAL_UNVERIFIED",self.codes(x))
    def test_tampered_proof_rejected(self):
        x=self.contract();(self.dir/"window1.json").write_text("changed")
        self.assertIn("WINDOW_EVIDENCE_INVALID",self.codes(x))
    def test_error_breach_and_dropped_iterations(self):
        x=self.contract();x["windows"][0].update(errors=20,dropped_iterations=10)
        codes=self.codes(x)
        self.assertIn("ERROR_BUDGET_BREACH",codes)
        self.assertIn("DROPPED_ITERATIONS",codes)
    def test_one_window_is_not_enough(self):
        x=self.contract();x["windows"].pop()
        self.assertIn("INSUFFICIENT_MONITORING_WINDOWS",self.codes(x))
    def test_recycled_proof_rejected(self):
        x=self.contract();x["windows"][1]["evidence"]=x["windows"][0]["evidence"]
        self.assertIn("WINDOW_EVIDENCE_INVALID",self.codes(x))
    def test_overlapping_windows_rejected(self):
        x=self.contract();x["windows"][1]["start_at"]="2026-11-21T18:04:00-05:00"
        self.assertIn("OVERLAPPING_MONITORING_WINDOWS",self.codes(x))
    def test_identity_requires_proof(self):
        x=self.contract();x["identity"]["evidence"]=[]
        self.assertIn("IDENTITY_EVIDENCE_UNVERIFIED",self.codes(x))
    def test_unrelated_receipt_cannot_prove_telemetry(self):
        x=self.contract()
        e=self.evidence("unrelated",{"kind":"telemetry_window","id":"unrelated"})
        x["windows"][0]["evidence"]=e
        self.assertIn("WINDOW_EVIDENCE_INVALID",self.codes(x))
    def test_predeployment_windows_rejected(self):
        x=self.contract();x["identity"]["deployed_at"]="2026-11-21T18:01:00-05:00"
        self.assertIn("PRE_DEPLOYMENT_WINDOW",self.codes(x))
    def test_blank_file_is_not_valid_evidence(self):
        x=self.contract()
        p=self.dir/"empty.json";p.write_bytes(b"")
        x["rollback"]["evidence"]=[{"path":"empty.json","sha256":hashlib.sha256(b"").hexdigest()}]
        self.assertIn("ROLLBACK_REHEARSAL_UNVERIFIED",self.codes(x))
if __name__=="__main__":unittest.main()
