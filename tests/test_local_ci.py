"""Local CI receipts fail closed on missing, forged or partial evidence."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from local_ci import ROOT as SOURCE, run_lane, TEST_PATTERN, SKIP_PATTERN

import importlib.util
SPEC=importlib.util.spec_from_file_location("dpa_localci_aggregate",SOURCE/"tools/localci/aggregate.py")
aggregate=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aggregate)

SHA="a"*64
HEAD="b"*40
LANE={"id":"linux-python312","platform":"Linux","runner":"linux-docker","python":"3.12.8"}


def sample(tmp:Path):
    directory=tmp/LANE["id"]
    directory.mkdir()
    checks=[]
    for name in ("full_suite","disposable_smoke"):
        out="" if name=="full_suite" else json.dumps({"result":"passed","python":"3.12.8",
                       "runtime_sha256":SHA,"installer_uninstall_verify":"passed",
                       "normal_and_negative_controls":"passed"})
        err="Ran 241 tests in 0.15s\n\nOK\n" if name=="full_suite" else ""
        (directory/(name+".stdout.log")).write_text(out)
        (directory/(name+".stderr.log")).write_text(err)
        record={"name":name,"pass":True,"timed_out":False,"exit_code":0,
            "stdout":name+".stdout.log","stderr":name+".stderr.log",
            "stdout_sha256":hashlib.sha256(out.encode()).hexdigest(),
            "stderr_sha256":hashlib.sha256(err.encode()).hexdigest()}
        if name=="full_suite":record.update(tests_discovered=241,skipped=0)
        else:record["smoke_summary"]=json.loads(out)
        checks.append(record)
    receipt={"schema_version":1,"runner":"linux-docker","platform":"Linux","source_commit":HEAD,
       "source_dirty":False,"source_dirty_after":False,"source_consistent":True,
       "source_revision_after":HEAD,"state":"passed","release_accepted":False,"native_windows_verified":False,
       "image_id":"sha256:"+SHA,"network":"none","workspace_mount":"read_only","checks":checks}
    (directory/"receipt.json").write_text(json.dumps(receipt))
    return directory, receipt


class LocalCIReceipts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="dpa-localci-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.directory,self.data=sample(self.root)

    def test_valid_receipt_passes_but_does_not_approve_release(self):
        result=aggregate.aggregate({"schema_version":1,"min_tests":241,"required":[LANE],
            "known_unverified":[{"id":"windows-native","status":"not_tested"}]},
            self.root,HEAD,SHA)
        self.assertEqual(result["status"],"passed_with_declared_gaps")
        self.assertFalse(result["native_windows_verified"])
        self.assertFalse(result["release_accepted"])

    def test_dirty_source_fails(self):
        self.data["source_dirty"]=True
        x=aggregate.check_receipt(LANE,self.data,self.directory,HEAD,241,SHA)
        self.assertIn("UNCLEAN_WORKTREE_AT_EXECUTION",x["issues"])

    def test_source_changes_during_execution_fail(self):
        self.data["source_consistent"] = False
        x = aggregate.check_receipt(LANE,self.data,self.directory,HEAD,241,SHA)
        self.assertIn("SOURCE_CHANGED_DURING_EXECUTION",x["issues"])

    def test_post_run_dirty_source_fails(self):
        self.data["source_dirty_after"] = True
        x = aggregate.check_receipt(LANE,self.data,self.directory,HEAD,241,SHA)
        self.assertIn("UNCLEAN_WORKTREE_AT_EXECUTION",x["issues"])

    def test_commit_mismatch_fails(self):
        x=aggregate.check_receipt(LANE,self.data,self.directory,"c"*40,241,SHA)
        self.assertIn("SOURCE_COMMIT_MISMATCH",x["issues"])

    def test_wrong_image_provenance_fails(self):
        self.data["network"]="bridge"
        x=aggregate.check_receipt(LANE,self.data,self.directory,HEAD,241,SHA)
        self.assertIn("CONTAINER_PROVENANCE_MISMATCH",x["issues"])

    def test_tampered_log_fails(self):
        (self.directory/"full_suite.stderr.log").write_text("Tampered")
        x=aggregate.check_receipt(LANE,self.data,self.directory,HEAD,241,SHA)
        self.assertIn("MISSING_OR_TAMPERED_LOG",x["issues"])

    def test_missing_lane_is_not_tested(self):
        matrix={"schema_version":1,"min_tests":241,"required":[LANE,{"id":"macos-python310","platform":"Darwin","runner":"native","python":"3.10.16"}]}
        x=aggregate.aggregate(matrix,self.root,HEAD,SHA)
        self.assertEqual(x["status"],"failed_or_incomplete")
        self.assertEqual(x["lanes"][-1]["state"],"not_tested")

    def test_skipped_case_is_not_pass(self):
        self.data["checks"][0]["skipped"]=1
        x=aggregate.check_receipt(LANE,self.data,self.directory,HEAD,241,SHA)
        self.assertIn("TEST_COUNT_OR_SKIPS",x["issues"])

    def test_missing_runtime_proof_fails(self):
        x=aggregate.check_receipt(LANE,self.data,self.directory,HEAD,241,"f"*64)
        self.assertIn("RUNTIME_SHA_MISMATCH",x["issues"])

    def test_untrusted_log_path_is_rejected(self):
        self.assertFalse(aggregate.safe_log(self.directory,"../secret",SHA))
        self.assertFalse(aggregate.safe_log(self.directory,"/etc/passwd",SHA))

    def test_never_overwrite_existing_runner_output(self):
        with self.assertRaises(ValueError):run_lane("native","/invalid",None,None,self.directory,241)

    def test_test_count_parser_does_not_mistake_skips_for_passes(self):
        self.assertEqual(TEST_PATTERN.search("Ran 241 tests in 0.5s").group(1),"241")
        self.assertEqual(SKIP_PATTERN.search("OK (skipped=2)").group(1),"2")

if __name__=="__main__":unittest.main()
