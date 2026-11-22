import unittest
import tempfile
import pathlib
import hashlib
from coverage_critic import critique

def contract(root):
    (root/"records").mkdir(exist_ok=True)
    (root/"records/1.json").write_text('{"observed":true}')
    digest=hashlib.sha256((root/"records/1.json").read_bytes()).hexdigest()
    d={"role":"parent","state":"success","platform":"web"}
    return {"schema_version":1,"scope_id":"demo","revision":"r1",
            "required_cases":[{"id":"C1","priority":"P0","dimensions":d,
                               "invariant":"cannot access another parent","oracle_required":True}],
            "observations":[{"case_id":"C1","revision":"r1","dimensions":d,"status":"passed",
                             "evidence":[{"path":"records/1.json","sha256":digest}],
                             "independent_oracle":"database row-level check",
                             "author":"author-1","reviewer":"reviewer-2"}]}
class CriticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
    def critique(self,x):
        return critique(x,self.root)
    def test_good_record(self):
        self.assertTrue(self.critique(contract(self.root))["scope_review_passed"])
        self.assertFalse(self.critique(contract(self.root))["release_accepted"])
    def test_missing_case_blocks(self):
        x=contract(self.root);x["observations"]=[]
        self.assertFalse(self.critique(x)["scope_review_passed"])
        self.assertIn("CRITICAL_GAP",[i["code"] for i in self.critique(x)["issues"]])
    def test_same_reviewer_blocks(self):
        x=contract(self.root);x["observations"][0]["reviewer"]=" author-1 "
        self.assertIn("NO_DISTINCT_REVIEWER",[i["code"] for i in self.critique(x)["issues"]])
    def test_stale_revision_blocks(self):
        x=contract(self.root);x["observations"][0]["revision"]="r0"
        self.assertIn("STALE_REVISION",[i["code"] for i in self.critique(x)["issues"]])
    def test_dim_mismatch_blocks(self):
        x=contract(self.root);x["observations"][0]["dimensions"]=dict(x["observations"][0]["dimensions"],role="admin")
        self.assertIn("DIMENSION_MISMATCH",[i["code"] for i in self.critique(x)["issues"]])
    def test_oracle_missing_blocks(self):
        x=contract(self.root);x["observations"][0]["independent_oracle"]=""
        self.assertIn("MISSING_ORACLE",[i["code"] for i in self.critique(x)["issues"]])
    def test_claimed_pass_does_not_cover_failure(self):
        x=contract(self.root);x["observations"][0]["status"]="failed"
        self.assertFalse(self.critique(x)["scope_review_passed"])
    def test_duplicate_case_rejected(self):
        x=contract(self.root);x["required_cases"].append(x["required_cases"][0])
        with self.assertRaises(ValueError):self.critique(x)
    def test_unscoped_claim(self):
        x=contract(self.root);o=x["observations"][0].copy();o["case_id"]="C2"
        x["observations"].append(o)
        self.assertIn("UNSCOPED_CLAIM",[i["code"] for i in self.critique(x)["issues"]])
    def test_tampered_evidence_rejected(self):
        x=contract(self.root)
        (self.root/"records/1.json").write_text('modified')
        self.assertIn("EVIDENCE_DIGEST_MISMATCH",[i["code"] for i in self.critique(x)["issues"]])
    def test_no_evidence_root_cannot_pass(self):
        self.assertIn("EVIDENCE_BYTES_UNCHECKED",[i["code"] for i in critique(contract(self.root))["issues"]])
    def test_missing_scope_id_rejected(self):
        x=contract(self.root);x.pop("scope_id")
        with self.assertRaises(ValueError):self.critique(x)
    def test_blank_oracle_rejected(self):
        x=contract(self.root);x["observations"][0]["independent_oracle"]="   "
        self.assertIn("MISSING_ORACLE",[i["code"] for i in self.critique(x)["issues"]])
    def test_invalid_digest_marks_unverified(self):
        x=contract(self.root);x["observations"][0]["evidence"][0]["sha256"]="0"*64
        self.assertFalse(self.critique(x)["evidence_bytes_verified"])
if __name__=="__main__":unittest.main()
