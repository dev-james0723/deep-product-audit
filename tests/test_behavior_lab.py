"""Behavior and failure-boundary tests for the public demonstration."""
import json
from pathlib import Path
import tempfile
import unittest

import behavior_lab as lab


class DemonstrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = lab.run_demo()

    def test_every_bug_reproduces_without_failed_clean_control(self):
        self.assertTrue(self.result["demo_validated"])
        self.assertEqual(self.result["known_bug_count"], 5)
        self.assertEqual(len(self.result["reproduced_bug_ids"]), 5)
        self.assertEqual(self.result["buggy_clean_control_failures"], [])
        self.assertEqual(self.result["fixed_failures"], [])
        self.assertEqual(self.result["blocked"], [])

    def test_same_assertions_and_inputs_are_bound_by_hash(self):
        self.assertEqual(self.result["checks_sha256_before"], self.result["checks_sha256_after"])
        self.assertEqual(self.result["checks_sha256_after"], lab.checks_hash())
        self.assertEqual(len(self.result["checks_sha256_before"]), 64)

    def test_claims_do_not_expand_to_agent_or_product(self):
        self.assertFalse(self.result["agent_evaluation_executed"])
        self.assertFalse(self.result["hidden_benchmark"])
        self.assertFalse(self.result["external_product_tested"])
        self.assertEqual(self.result["per_mode_check_count"], 10)
        self.assertEqual(len(self.result["results"]["buggy"]), 10)
        self.assertEqual(len(self.result["results"]["fixed"]), 10)

    def test_batch_oracle_observes_disk_not_just_success_response(self):
        case = next(c for c in self.result["results"]["buggy"] if c["case_id"] == "batch-bug")
        self.assertEqual(case["observation"]["status_code"], 200)
        self.assertTrue(case["observation"]["response"]["all_succeeded"])
        self.assertEqual(case["observation"]["rows"], [{"id": 1, "value": "new"}, {"id": 2, "value": "old"}])
        self.assertEqual(case["status"], "failed")

    def test_concurrent_write_failure_is_invalid_durable_json(self):
        case = next(c for c in self.result["results"]["buggy"] if c["case_id"] == "atomic-file-bug")
        self.assertFalse(case["observation"]["valid_json"])
        with self.assertRaises(ValueError):
            json.loads(case["observation"]["raw_final"])

    def test_stream_bug_has_real_transport_truncation(self):
        case = next(c for c in self.result["results"]["buggy"] if c["case_id"] == "stream-bug")
        observation = case["observation"]
        self.assertTrue(observation["truncated"])
        self.assertLess(observation["received_bytes"], observation["declared_bytes"])
        self.assertEqual(observation["application_state"], "completed")
        self.assertEqual(case["status"], "failed")

    def test_existing_evidence_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.json"
            output.write_text("preserve", encoding="utf-8")
            with self.assertRaises(SystemExit):
                lab.main(["--out", str(output)])
            self.assertEqual(output.read_text(encoding="utf-8"), "preserve")

    def test_observation_digests_match_content(self):
        for cases in self.result["results"].values():
            for case in cases:
                self.assertEqual(case["observation_sha256"], lab.digest(case["observation"]))


class PrivacyAndInputTests(unittest.TestCase):
    def test_documented_boolean_encodings(self):
        for raw in ("true", "True", "TRUE"):
            self.assertTrue(lab.parse_private(raw))
        for raw in ("false", "False", "FALSE"):
            self.assertFalse(lab.parse_private(raw))

    def test_ambiguous_or_absent_boolean_is_rejected(self):
        for raw in (None, True, False, 1, 0, "", "1", "0", " true ", "yes", [], {}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                lab.parse_private(raw)

    def test_unauthorized_privacy_variants_never_create_public_subscription(self):
        with tempfile.TemporaryDirectory() as temporary:
            with lab.serve("fixed", Path(temporary) / "db.sqlite") as (port, app):
                for path, code in (("/subscribe?private=True", 403), ("/subscribe?private=TRUE", 403),
                                   ("/subscribe?private=yes", 400), ("/subscribe", 400),
                                   ("/subscribe?private=true&private=false", 400)):
                    self.assertEqual(lab.request(port, path)["status_code"], code)
                import sqlite3
                with sqlite3.connect(str(app.database)) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0], 0)

    def test_explicit_public_subscription_is_a_clean_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            with lab.serve("fixed", Path(temporary) / "db.sqlite") as (port, _):
                self.assertEqual(lab.request(port, "/subscribe?private=false")["status_code"], 200)

    def test_invalid_batch_input_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            with lab.serve("fixed", Path(temporary) / "db.sqlite") as (port, app):
                for payload in ({"ids": [True]}, {"ids": []}, {"ids": [1, 1]}, {"ids": "1"}, [], {}):
                    self.assertEqual(lab.request(port, "/batch", payload)["status_code"], 400)
                import sqlite3
                with sqlite3.connect(str(app.database)) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM documents WHERE value='new'").fetchone()[0], 0)


class ReleaseRecordTests(unittest.TestCase):
    def contract(self):
        return {"commit": "revision-a", "overall": "success", "required": ["unit", "integration"],
                "jobs": [{"id": "unit", "status": "passed", "commit": "revision-a"},
                         {"id": "integration", "status": "passed", "commit": "revision-a"}]}

    def test_complete_required_scope_accepts(self):
        self.assertTrue(lab.release_gate("fixed", self.contract()))

    def test_skipped_cancelled_blocked_unknown_never_pass(self):
        for status in ("skipped", "cancelled", "blocked", "not_tested", "unknown", "failed", None):
            contract = self.contract()
            contract["jobs"][1]["status"] = status
            self.assertFalse(lab.release_gate("fixed", contract))

    def test_missing_required_job_is_not_zero_failures(self):
        contract = self.contract()
        contract["jobs"].pop()
        self.assertFalse(lab.release_gate("fixed", contract))

    def test_stale_commit_cannot_prove_current_scope(self):
        contract = self.contract()
        contract["jobs"][1]["commit"] = "old-revision"
        self.assertFalse(lab.release_gate("fixed", contract))

    def test_duplicate_jobs_cannot_mask_failure(self):
        contract = self.contract()
        contract["jobs"].append({"id": "unit", "status": "failed", "commit": "revision-a"})
        self.assertFalse(lab.release_gate("fixed", contract))

    def test_malformed_scope_fails_closed(self):
        for value in (None, [], "success", {}, {"overall": "success"}):
            self.assertFalse(lab.release_gate("fixed", value))
        for field, value in (("required", []), ("required", ["unit", "unit"]), ("required", [{}]),
                             ("jobs", [None]), ("commit", None)):
            contract = self.contract()
            contract[field] = value
            self.assertFalse(lab.release_gate("fixed", contract))


class StreamAndAtomicTests(unittest.TestCase):
    def test_byte_complete_but_missing_terminal_marker_is_incomplete(self):
        body = '{"delta":"hello"}\n'
        receipt = {"status_code": 200, "body": body, "received_bytes": len(body), "declared_bytes": len(body), "truncated": False}
        self.assertEqual(lab.consume_stream("fixed", receipt), "incomplete")

    def test_malformed_stream_cannot_complete(self):
        receipt = {"status_code": 200, "body": "broken\n", "received_bytes": 7, "declared_bytes": 7, "truncated": False}
        self.assertEqual(lab.consume_stream("fixed", receipt), "failed")

    def test_error_status_with_terminal_marker_is_not_success(self):
        body = '{"done":true}\n'
        receipt = {"status_code": 500, "body": body, "received_bytes": len(body), "declared_bytes": len(body), "truncated": False}
        self.assertEqual(lab.consume_stream("fixed", receipt), "failed")

    def test_atomic_interleaving_is_repeatable_and_leaves_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            for index in range(3):
                directory = Path(temporary) / str(index)
                directory.mkdir()
                observed = lab.concurrent_snapshot("fixed", directory)
                self.assertTrue(lab.evaluate_observation("atomic-file", observed))

    def test_mode_typo_is_not_implicitly_fixed(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                lab.Application("unknown", Path(temporary) / "db.sqlite")
            with self.assertRaises(ValueError):
                lab.atomic_write("unknown", Path(temporary) / "x", {})
        with self.assertRaises(ValueError):
            lab.release_gate("unknown", {})
        with self.assertRaises(ValueError):
            lab.consume_stream("unknown", {})


if __name__ == "__main__":
    unittest.main()
