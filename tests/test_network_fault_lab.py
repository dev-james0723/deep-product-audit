#!/usr/bin/env python3
"""Behavioral checks for the isolated network lab; no external service required."""
from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import network_fault_lab as lab


class NetworkLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.comparison = lab.run_lab("compare")

    def test_compare_detects_actual_duplicate_effects_and_corrected_recovery(self) -> None:
        result = self.comparison
        self.assertTrue(result["fixture_validation_passed"], result)
        buggy, corrected = result["suites"]
        self.assertFalse(buggy["all_invariants_passed"])
        self.assertTrue(corrected["all_invariants_passed"])
        for suite, count in ((buggy, 2), (corrected, 1)):
            cases = {case["id"]: case for case in suite["cases"]}
            for case_id in ("NET-004", "NET-005", "NET-017"):
                self.assertEqual(cases[case_id]["observations"]["effects_before_retry"], 1)
                self.assertEqual(cases[case_id]["observations"]["effects_after_retry"], count)
        self.assertEqual(result["discrimination"]["observed_seeded_failures"], ["NET-004", "NET-005", "NET-017"])

    def test_lab_never_claims_product_acceptance(self) -> None:
        self.assertIs(self.comparison["product_accepted"], False)
        self.assertEqual(self.comparison["kind"], "isolated_fixture_validation")
        self.assertIn("Synthetic", self.comparison["scope"])

    def test_offline_and_429_attempts_have_no_early_effect(self) -> None:
        for suite in self.comparison["suites"]:
            cases = {case["id"]: case for case in suite["cases"]}
            for case_id in ("NET-001", "NET-009"):
                observed = cases[case_id]["observations"]
                self.assertEqual(observed["effects_before_recovery"], 0)
                self.assertEqual(observed["effects_after_recovery"], 1)
            self.assertEqual(cases["NET-009"]["observations"]["attempts"], 2)
            self.assertEqual(cases["NET-009"]["observations"]["first"]["status"], 429)
            offline = cases["NET-001"]["observations"]["first"]
            self.assertEqual(offline["transport_phase"], "connect")
            self.assertFalse(offline["connection_established"])
            self.assertFalse(offline["request_write_attempted"])
            self.assertEqual(offline["operation_outcome"], "not_sent")

    def test_connect_timeout_preserves_no_delivery_and_real_recovery(self) -> None:
        original_connect = lab.http.client.HTTPConnection.connect
        calls = 0

        def connect(connection):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("simulated non-listening-port connect timeout")
            return original_connect(connection)

        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(lab.http.client.HTTPConnection, "connect", connect):
                case = lab.execute_case("NET-001", Path(temporary), "corrected", lab.Deadline(5), [])
        self.assertEqual(calls, 2)
        self.assertEqual(case["status"], "passed", case)
        self.assertEqual(case["observations"]["first"]["transport_error"], "TimeoutError")
        self.assertEqual(case["observations"]["first"]["operation_outcome"], "not_sent")
        self.assertEqual(case["observations"]["effects_before_recovery"], 0)
        self.assertEqual(case["observations"]["effects_after_recovery"], 1)

    def test_timeout_after_request_write_is_not_offline_before_submission(self) -> None:
        original_request = lab.request
        calls = 0

        def request(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"status": None, "body": None, "transport_error": "TimeoutError",
                        "transport_phase": "read_response", "connection_established": True,
                        "request_write_attempted": True, "operation_outcome": "unknown"}
            return original_request(*args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(lab, "request", request):
                case = lab.execute_case("NET-001", Path(temporary), "corrected", lab.Deadline(5), [])
        self.assertEqual(case["status"], "failed")
        self.assertFalse(case["checks"]["connection_unavailable_before_send"])
        self.assertTrue(case["checks"]["no_effect_before_recovery"])
        self.assertTrue(case["checks"]["recovered_response"])
        self.assertTrue(case["checks"]["effect_once"])

    def test_owned_resources_are_closed_and_temporary_data_removed(self) -> None:
        for suite in self.comparison["suites"]:
            self.assertEqual(suite["infrastructure_errors"], [])
            self.assertTrue(all(suite["cleanup"].values()), suite["cleanup"])

    def test_budget_exhaustion_is_not_success(self) -> None:
        result = lab.run_lab("compare", deadline_seconds=1e-9)
        self.assertFalse(result["fixture_validation_passed"])
        self.assertFalse(result["product_accepted"])
        self.assertTrue(any(case["status"] == "blocked" for suite in result["suites"] for case in suite["cases"]))
        self.assertTrue(any(case["status"] == "not_tested" for suite in result["suites"] for case in suite["cases"]))

    def test_payload_conflict_after_new_server_instance_has_no_extra_effect(self) -> None:
        owned: list[lab.Fixture] = []
        deadline = lab.Deadline(5)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.sqlite3"
            first_store = lab.Store(path)
            with lab.Fixture(first_store, "corrected", owned) as first:
                response = lab.request(first.port, deadline, "same-operation", fault="drop_reply", amount=1)
                self.assertIsNotNone(response["transport_error"])
            fresh_store = lab.Store(path)
            with lab.Fixture(fresh_store, "corrected", owned) as second:
                conflict = lab.request(second.port, deadline, "same-operation", amount=2)
                replay = lab.request(second.port, deadline, "same-operation", amount=1)
            self.assertEqual(conflict["status"], 409)
            self.assertEqual(replay["status"], 200)
            self.assertTrue(replay["body"]["replayed"])
            self.assertEqual(fresh_store.effect_count("same-operation"), 1)
        self.assertTrue(all(fixture.closed for fixture in owned))

    def test_concurrent_same_operation_commits_once(self) -> None:
        owned: list[lab.Fixture] = []
        deadline = lab.Deadline(5)
        with tempfile.TemporaryDirectory() as temporary:
            store = lab.Store(Path(temporary) / "race.sqlite3")
            with lab.Fixture(store, "corrected", owned) as server:
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    responses = list(pool.map(lambda _: lab.request(server.port, deadline, "concurrent-operation"), range(4)))
            self.assertEqual([response["status"] for response in responses], [200] * 4)
            self.assertEqual(sum(not response["body"]["replayed"] for response in responses), 1)
            self.assertEqual(store.effect_count("concurrent-operation"), 1)

    def test_keyboard_interrupt_closes_owned_fixture(self) -> None:
        owned: list[lab.Fixture] = []
        with tempfile.TemporaryDirectory() as temporary:
            store = lab.Store(Path(temporary) / "cancel.sqlite3")
            with self.assertRaises(KeyboardInterrupt):
                with lab.Fixture(store, "corrected", owned):
                    raise KeyboardInterrupt
        self.assertTrue(owned[0].closed)
        self.assertFalse(owned[0].thread.is_alive())
        self.assertEqual(owned[0].server.socket.fileno(), -1)

    def test_profile_catalog_is_unexecuted_and_matches_fixture_ids(self) -> None:
        catalog = lab.load_profiles()
        self.assertEqual(catalog["assessment_status"], "not_run")
        self.assertEqual(len(catalog["profiles"]), 20)
        self.assertEqual(len({profile["id"] for profile in catalog["profiles"]}), 20)
        fixture_ids = {profile["id"] for profile in catalog["profiles"] if profile["execution_support"] == "loopback_fixture"}
        self.assertEqual(fixture_ids, set(lab.LAB_SCENARIOS))
        for profile in catalog["profiles"]:
            self.assertEqual(profile["assessment_status"], "not_run")
            self.assertTrue(profile["independent_oracles"])
            self.assertTrue(profile["recovery"])

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(Path(lab.__file__)), *args],
                              text=True, capture_output=True, timeout=20)

    def test_cli_has_no_external_target_option(self) -> None:
        result = self.invoke("--target", "https://example.invalid")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_cli_rejects_out_of_bounds_deadline(self) -> None:
        for value in ("0", "-1", "16", "nan", "inf"):
            with self.subTest(value=value):
                result = self.invoke("--deadline-seconds", value)
                self.assertEqual(result.returncode, 2)

    def test_cli_never_overwrites_existing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            original = "preserve existing evidence\n"
            path.write_text(original)
            result = self.invoke("--out", str(path))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_text(), original)

    def test_cli_writes_new_result_and_buggy_mode_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            result = self.invoke("--mode", "buggy", "--out", str(path))
            self.assertEqual(result.returncode, 1, result.stderr)
            saved = json.loads(path.read_text())
            self.assertFalse(saved["fixture_validation_passed"])
            self.assertFalse(saved["product_accepted"])
            self.assertEqual(sum(case["status"] == "failed" for case in saved["suites"][0]["cases"]), 3)

    def test_list_profiles_does_not_require_starting_servers(self) -> None:
        result = self.invoke("--list-profiles")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["assessment_status"], "not_run")


if __name__ == "__main__":
    unittest.main()
