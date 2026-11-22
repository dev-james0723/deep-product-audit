"""A duplicate claim about one fixed defect must not manufacture another fix."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import evaluate_audit as evaluation


class DuplicateClosureTests(unittest.TestCase):
    def test_duplicate_true_finding_does_not_inflate_verified_closures(self):
        with tempfile.TemporaryDirectory(prefix="duplicate-closure-test-") as temporary:
            root = Path(temporary)
            raw = json.dumps({"kind": "synthetic_grader_receipt", "case_id": "a", "defect_key": "duplicate",
                              "verdict": "confirmed", "closure_verdict": "fixed"}).encode()
            (root / "review.json").write_bytes(raw)
            proof = {"path": "review.json", "sha256": hashlib.sha256(raw).hexdigest()}
            manifest = {"schema_version": 1, "benchmark_id": "synthetic-closure-contract", "cases": [
                {"id": "a", "prompt": "Synthetic contract test only",
                 "oracle": {"outcome": "bug", "defect_key": "duplicate"}}]}
            baseline = evaluation.make_template(manifest)
            baseline.update(run_id="baseline", author="fixture-author", skill_revision="r1", model="same",
                            environment_id="same", budget_id="same")
            verification = {"reviewer": "fixture-grader", "evidence": [proof]}
            finding = {"id": "finding-1", "defect_key": "duplicate", "verdict": "confirmed",
                       "verification": verification,
                       "closure": {"claimed": True, "verdict": "fixed", "verification": verification}}
            baseline["observations"][0].update(attempted=True, outcome="bug", evidence=[proof], findings=[finding])
            candidate = copy.deepcopy(baseline)
            candidate["run_id"] = "candidate"
            duplicate = copy.deepcopy(finding)
            duplicate["id"] = "finding-2"
            candidate["observations"][0]["findings"].append(duplicate)
            result = evaluation.compare(manifest, baseline, candidate, root, root)
            self.assertTrue(result["comparable"])
            self.assertEqual(result["candidate"]["counts"]["true_findings"], 1)
            self.assertEqual(result["candidate"]["counts"]["duplicate_true_findings"], 1)
            self.assertEqual(result["candidate"]["counts"]["verified_closures"], 1,
                             "Two claims about the same fixed case/defect are one verified closure")
            self.assertEqual(result["deltas"]["verified_closures"], 0)


if __name__ == "__main__":
    unittest.main()
