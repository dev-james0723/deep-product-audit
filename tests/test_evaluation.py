#!/usr/bin/env python3
"""Isolated evaluator contract tests; these are not agent/product benchmark results."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import evaluate_audit as evaluation
import regression_evidence as regression


def artifact(root, name, data):
    raw = data.encode() if isinstance(data, str) else data
    (root / name).write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="audit-eval-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proof = artifact(self.root, "evidence.txt", "Synthetic independently checked observation.\n")
        self.manifest = {"schema_version": 1, "benchmark_id": "synthetic-test-only", "cases": [
            {"id": "a", "prompt": "Audit fixture A", "oracle": {"outcome": "bug", "defect_key": "duplicate"}},
            {"id": "b", "prompt": "Audit fixture B", "oracle": {"outcome": "clean"}},
            {"id": "c", "prompt": "Audit fixture C", "oracle": {"outcome": "blocked"}},
            {"id": "d", "prompt": "Audit fixture D", "oracle": {"outcome": "unknown"}},
        ]}
        self.run = evaluation.make_template(self.manifest)
        self.run.update(run_id="synthetic-run", author="audit-agent", model="frozen-model", environment_id="fixture-1", budget_id="fixed-budget")
        for row, outcome in zip(self.run["observations"], ("bug", "clean", "blocked", "unknown")):
            row.update(attempted=True, outcome=outcome, evidence=[self.proof], duration_seconds=1.0)
        self.run["observations"][0]["findings"] = [self.finding()]

    def finding(self, key="duplicate", verdict="confirmed"):
        return {"id": "finding-1", "defect_key": key, "verdict": verdict,
                "verification": {"reviewer": "separate-reviewer", "evidence": [self.proof]}}

    def score(self):
        return evaluation.score_run(self.manifest, self.run, self.root)

    def test_correct_record_keeps_known_denominator_and_unknown_measurements(self):
        result = self.score()
        self.assertTrue(result["complete_record"])
        self.assertEqual(result["known_bug_recall"], {"numerator": 1, "denominator": 1, "value": 1.0})
        self.assertEqual(result["counts"]["correct_classifications"], 4)
        self.assertIsNone(result["measurements"]["cost_usd"]["total"])
        self.assertFalse(result["measurements"]["cost_usd"]["complete"])

    def test_missing_case_cannot_improve_recall_or_complete(self):
        self.run["observations"].pop(0)
        result = self.score()
        self.assertEqual(result["known_bug_recall"]["denominator"], 1)
        self.assertEqual(result["known_bug_recall"]["numerator"], 0)
        self.assertFalse(result["complete_record"])
        self.assertEqual(result["counts"]["missing"], 1)

    def test_clean_case_false_positive(self):
        row = self.run["observations"][1]
        row.update(outcome="bug", findings=[self.finding("invented")])
        result = self.score()
        self.assertEqual(result["counts"]["false_findings"], 1)
        self.assertEqual(result["judged_finding_precision"]["value"], 0.5)

    def test_unverified_finding_is_not_a_confirmed_bug(self):
        finding = self.run["observations"][0]["findings"][0]
        finding["verification"]["reviewer"] = " audit-agent "
        result = self.score()
        self.assertEqual(result["counts"]["unproven_findings"], 1)
        self.assertEqual(result["known_bug_recall"]["value"], 0)
        self.assertFalse(result["complete_record"])

    def test_false_closure_and_unproven_closure_remain_distinct(self):
        finding = self.run["observations"][0]["findings"][0]
        finding["closure"] = {"claimed": True, "verdict": "still_failing",
                              "verification": {"reviewer": "checker-2", "evidence": [self.proof]}}
        self.assertEqual(self.score()["counts"]["false_closures"], 1)
        finding["closure"]["verification"]["evidence"] = []
        result = self.score()
        self.assertEqual(result["counts"]["unproven_closures"], 1)
        self.assertEqual(result["counts"]["false_closures"], 0)

    def test_unsafe_clean_claim_on_blocker(self):
        self.run["observations"][2]["outcome"] = "clean"
        self.assertEqual(self.score()["counts"]["unsafe_clear_claims"], 1)

    def test_duplicate_and_unknown_case_ids_rejected(self):
        for identity in ("a", "not-a-case"):
            with self.subTest(identity=identity):
                self.run["observations"][1]["case_id"] = identity
                with self.assertRaises(evaluation.InputError):
                    self.score()

    def test_duplicate_true_claims_do_not_inflate_precision(self):
        findings = self.run["observations"][0]["findings"]
        findings.append(copy.deepcopy(findings[0]))
        findings[1]["id"] = "second-claim"
        result = self.score()
        self.assertEqual(result["counts"]["true_findings"], 1)
        self.assertEqual(result["counts"]["duplicate_true_findings"], 1)

    def test_malformed_types_and_nonfinite_metrics_rejected(self):
        for field, value in (("cost_usd", float("nan")), ("duration_seconds", float("inf")),
                             ("cost_usd", True), ("cost_usd", 10 ** 1000), ("outcome", []), ("attempted", "yes"), ("findings", {})):
            with self.subTest(field=field, value=value):
                saved = copy.deepcopy(self.run)
                self.run["observations"][0][field] = value
                with self.assertRaises(evaluation.InputError):
                    self.score()
                self.run = saved

    def test_artifact_tamper_and_path_escape_rejected(self):
        for item in ({"path": "../outside", "sha256": "a" * 64},
                     {"path": "/etc/passwd", "sha256": "a" * 64},
                     {"path": "null\u0000byte", "sha256": "a" * 64},
                     {"path": "evidence.txt", "sha256": "0" * 64}):
            self.assertFalse(evaluation.evidence_valid([item], self.root))
        (self.root / "escape").symlink_to("/etc/passwd")
        self.assertFalse(evaluation.evidence_valid([{"path": "escape", "sha256": "0" * 64}], self.root))
        (self.root / "loop").symlink_to("loop")
        self.assertFalse(evaluation.evidence_valid([{"path": "loop", "sha256": "0" * 64}], self.root))

    def test_compare_refuses_different_context_or_incomplete_runs(self):
        candidate = copy.deepcopy(self.run)
        candidate["model"] = "different-model"
        result = evaluation.compare(self.manifest, self.run, candidate, self.root, self.root)
        self.assertFalse(result["comparable"])
        self.assertIsNone(result["deltas"])
        self.assertEqual(result["mismatched_context"], ["model"])

    def test_distinct_runs_and_frozen_manifest_are_required(self):
        same = evaluation.compare(self.manifest, self.run, self.run, self.root, self.root)
        self.assertFalse(same["comparable"])
        self.assertFalse(same["distinct_run_ids"])
        self.manifest["cases"][0]["oracle"]["defect_key"] = "changed-answer"
        with self.assertRaises(evaluation.InputError):
            self.score()

    def test_loader_rejects_duplicate_keys_and_nan(self):
        for value in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '{"x":' * 1100 + '1' + '}' * 1100):
            (self.root / "bad.json").write_text(value)
            with self.assertRaises(evaluation.InputError):
                evaluation.load_json(self.root / "bad.json")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO is available on Unix")
    def test_loader_rejects_fifo_without_blocking(self):
        fifo = self.root / "never-written.fifo"
        os.mkfifo(fifo)
        with self.assertRaises(evaluation.InputError):
            evaluation.load_json(fifo)

    def test_loader_rejects_directory_and_special_file(self):
        with self.assertRaises(evaluation.InputError):
            evaluation.load_json(self.root)
        if Path("/dev/null").exists():
            with self.assertRaises(evaluation.InputError):
                evaluation.load_json("/dev/null")

    def test_public_prompts_omit_oracle_and_templates_never_prepopulate_passes(self):
        manifest = {"schema_version": 1, "benchmark_id": "public-contract-example", "cases": [
            {"id": str(i), "prompt": "Example contract case " + str(i),
             "oracle": {"outcome": "bug" if i < 10 else "clean" if i < 15 else "blocked",
                        "defect_key": "example-" + str(i)}} for i in range(20)]}
        manifest_path = self.root / "external-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        kinds = [case["oracle"]["outcome"] for case in manifest["cases"]]
        self.assertEqual(len(kinds), 20)
        self.assertEqual(kinds.count("bug"), 10)
        self.assertEqual(kinds.count("clean"), 5)
        template = evaluation.make_template(manifest)
        self.assertTrue(all(not row["attempted"] and row["outcome"] == "unknown" for row in template["observations"]))
        output = self.root / "prompts.json"
        command = [sys.executable, str(Path(evaluation.__file__)), "--manifest", str(manifest_path), "prompts", "--out", str(output)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        public = evaluation.load_json(output)
        self.assertTrue(all(set(row) == {"id", "prompt"} for row in public["cases"]))
        second = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(second.returncode, 2, "Existing output must never be overwritten")

    def test_cli_malformed_input_returns_json_error_without_traceback(self):
        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps(self.manifest))
        run_path = self.root / "bad-run.json"
        run_path.write_text("[]")
        completed = subprocess.run([sys.executable, evaluation.__file__, "--manifest", str(manifest_path),
                                    "score", "--baseline", str(run_path), "--candidate", str(run_path)],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("error", json.loads(completed.stderr))
        self.assertNotIn("Traceback", completed.stderr)


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="audit-regression-test-")
        cls.root = Path(cls.temp.name)
        cls.addClassCleanup(cls.temp.cleanup)
        # The same assertion is run against an intentionally buggy and corrected fixture.
        source = "import sys\nrequests=['operation-1','operation-1']\ncount=len(requests) if sys.argv[1]=='buggy' else len(set(requests))\nassert count == 1, 'operation-count'\nprint('operation-count passed')\n"
        digest = hashlib.sha256(source.encode()).hexdigest()
        cls.good = {"schema_version": 1, "case_id": "synthetic-duplicate-test", "test_id": "one-effect",
                    "assertion_id": "operation-count", "test_sha256": digest, "oracle_sha256": digest,
                    "environment_id": "isolated-python", "buggy_revision": "fixture-buggy",
                    "fixed_revision": "fixture-fixed", "author": "fixture-agent", "verifier": "fixture-reviewer", "runs": []}
        for phase, mode in (("before", "buggy"), ("after", "fixed")):
            for repetition in (1, 2):
                result = subprocess.run([sys.executable, "-c", source, mode], capture_output=True, text=True, timeout=5)
                failed = result.returncode != 0
                proof = artifact(cls.root, f"{phase}-{repetition}.log", result.stdout + result.stderr)
                cls.good["runs"].append({"phase": phase, "repetition": repetition,
                    "revision": cls.good["buggy_revision" if phase == "before" else "fixed_revision"],
                    "test_id": "one-effect", "test_sha256": digest, "oracle_sha256": digest,
                    "environment_id": "isolated-python", "outcome": "failed" if failed else "passed",
                    "failure_kind": "assertion" if failed and "AssertionError: operation-count" in result.stderr else None,
                    "assertion_id": "operation-count" if failed else None, "evidence": [proof]})
        review = {field: cls.good[field] for field in ("case_id", "test_id", "assertion_id", "test_sha256", "oracle_sha256", "environment_id", "buggy_revision", "fixed_revision", "author")}
        review.update(schema_version=1, kind="independent_regression_review", reviewer=cls.good["verifier"],
                      runs_sha256=regression.runs_digest(cls.good["runs"]), verdict="confirmed")
        cls.good["verification"] = artifact(cls.root, "independent-review.json", json.dumps(review))

    def test_actual_fixture_before_and_after_records_accepted(self):
        self.assertTrue(regression.check_regression(self.good, self.root)["accepted"])

    def test_verifier_name_without_review_artifact_is_not_evidence(self):
        doc = copy.deepcopy(self.good)
        del doc["verification"]
        result = regression.check_regression(doc, self.root)
        self.assertFalse(result["accepted"])
        self.assertIn("missing_or_invalid_verification_record", result["reasons"])

    def test_review_must_bind_exact_case_oracle_and_run_records(self):
        for field, value, reason in (("case_id", "another-case", "verification_case_id_mismatch"),
                                     ("oracle_sha256", "0" * 64, "verification_oracle_sha256_mismatch"),
                                     ("runs_sha256", "0" * 64, "verification_does_not_bind_current_runs")):
            with self.subTest(field=field):
                doc = copy.deepcopy(self.good)
                review = evaluation.load_json(self.root / "independent-review.json")
                review[field] = value
                doc["verification"] = artifact(self.root, "changed-review.json", json.dumps(review))
                result = regression.check_regression(doc, self.root)
                self.assertFalse(result["accepted"])
                self.assertIn(reason, result["reasons"])

    def test_recycled_execution_proof_cannot_show_both_fail_and_pass(self):
        doc = copy.deepcopy(self.good)
        doc["runs"][2]["evidence"] = copy.deepcopy(doc["runs"][0]["evidence"])
        # Even a review freshly bound to this contradictory record cannot make it pass.
        review = evaluation.load_json(self.root / "independent-review.json")
        review["runs_sha256"] = regression.runs_digest(doc["runs"])
        doc["verification"] = artifact(self.root, "recycled-proof-review.json", json.dumps(review))
        result = regression.check_regression(doc, self.root)
        self.assertFalse(result["accepted"])
        self.assertIn("reused_before_after_evidence", result["reasons"])

    def test_review_cannot_relabel_execution_bytes(self):
        doc = copy.deepcopy(self.good)
        doc["verification"] = copy.deepcopy(doc["runs"][0]["evidence"][0])
        result = regression.check_regression(doc, self.root)
        self.assertFalse(result["accepted"])
        self.assertIn("verification_reuses_execution_evidence", result["reasons"])

    def test_import_failure_does_not_count_as_product_regression(self):
        doc = copy.deepcopy(self.good)
        doc["runs"][0]["failure_kind"] = "import"
        result = regression.check_regression(doc, self.root)
        self.assertFalse(result["accepted"])
        self.assertIn("runner_or_environment_failure", result["reasons"])

    def test_unrelated_assertion_does_not_count(self):
        doc = copy.deepcopy(self.good)
        doc["runs"][0]["assertion_id"] = "unrelated-assertion"
        self.assertIn("unrelated_assertion_failure", regression.check_regression(doc, self.root)["reasons"])

    def test_mixed_baseline_results_detect_instability(self):
        doc = copy.deepcopy(self.good)
        doc["runs"][0].update(outcome="passed", failure_kind=None, assertion_id=None)
        reasons = regression.check_regression(doc, self.root)["reasons"]
        self.assertIn("inconsistent_before_results", reasons)
        self.assertIn("test_passed_on_buggy_revision", reasons)

    def test_skips_timeouts_and_changed_oracles_refused(self):
        for field, value, expected in (("outcome", "skipped", "skipped_test"),
                                       ("outcome", "timeout", "runner_or_environment_failure"),
                                       ("oracle_sha256", "0" * 64, "oracle_sha256_mismatch"),
                                       ("environment_id", "other", "environment_id_mismatch")):
            with self.subTest(field=field, value=value):
                doc = copy.deepcopy(self.good)
                doc["runs"][0][field] = value
                self.assertIn(expected, regression.check_regression(doc, self.root)["reasons"])

    def test_missing_runs_tamper_and_same_verifier_refused(self):
        doc = copy.deepcopy(self.good)
        doc["runs"] = doc["runs"][2:]
        self.assertIn("missing_before_runs", regression.check_regression(doc, self.root)["reasons"])
        doc = copy.deepcopy(self.good)
        doc["runs"][0]["evidence"][0]["sha256"] = "0" * 64
        self.assertIn("missing_or_invalid_evidence", regression.check_regression(doc, self.root)["reasons"])
        doc["verifier"] = doc["author"]
        self.assertIn("no_independent_verifier", regression.check_regression(doc, self.root)["reasons"])

    def test_duplicate_repetitions_and_invalid_types_rejected(self):
        doc = copy.deepcopy(self.good)
        doc["runs"][1]["repetition"] = 1
        with self.assertRaises(evaluation.InputError):
            regression.check_regression(doc, self.root)
        doc = copy.deepcopy(self.good)
        doc["runs"][0]["outcome"] = []
        with self.assertRaises(evaluation.InputError):
            regression.check_regression(doc, self.root)


if __name__ == "__main__":
    unittest.main()
