#!/usr/bin/env python3
"""Isolated ledger contract tests; fixtures are synthetic and never audit a product."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import audit_ledger as ledger


SCRIPT = Path(ledger.__file__)
BEFORE_REVISION = "1" * 40
CURRENT_REVISION = "2" * 40
ARTIFACT_DIGEST = hashlib.sha256(b"synthetic fixture artifact").hexdigest()


def evidence(bundle: Path, name: str, kind: str = "test", *, case_id: str | None = "C-001",
             subject: str | None = None, content: str | None = None) -> dict:
    path = bundle / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or f"Synthetic evidence for {name}; this is a helper test, not product evidence.\n")
    value = {"path": name, "type": kind, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
             "observed_at": ledger.now(), "summary": "Synthetic contract-test fixture"}
    if case_id is not None:
        value["case_id"] = case_id
    if subject is not None:
        value["subject"] = subject
    return value


def make_v2_fixture(bundle: Path, *, kind: str = "native", environment: str = "local",
                    with_fixed: bool = False) -> dict:
    """Create a fully populated synthetic contract fixture for integrations/tests only."""
    targets = {
        "web": {"kind": "web", "locator": "https://example.test"},
        "api": {"kind": "api", "locator": "https://example.test/api"},
        "native": {"kind": "native", "locator": "com.example.AuditFixture", "platform": "macos"},
        "cli": {"kind": "cli", "locator": "/usr/bin/fixture-cli"},
        "mobile": {"kind": "mobile", "locator": "com.example.AuditFixture", "platform": "ios"},
    }
    run = evidence(bundle, "evidence/case.log")
    data = {
        "schema_version": 2,
        "scope": {"id": "fixture-audit", "target": targets[kind], "environment": environment,
                  "profile": "advanced", "started_at": ledger.now(), "build": "fixture-v2",
                  "audit_actor": "executor-session", "roles": ["fixture-user"], "viewports": ["native"],
                  "exclusions": []},
        "capabilities": {},
        "coverage": [{"id": "C-001", "route": "fixture/save", "role": "fixture-user", "viewport": "native",
                      "state": "success", "invariant": "The fixture commits one operation exactly once",
                      "expected": "One durable fixture record", "actual": "Observed one fixture record",
                      "risk": "P1", "required": True, "observed_build": ARTIFACT_DIGEST,
                      "status": "passed", "reason": "", "evidence": [run]}],
        "findings": [],
        "provenance": {
            "source": {"revision": CURRENT_REVISION, "recorded_by": "executor-session",
                       "evidence": [evidence(bundle, "evidence/source.json", "source", case_id=None, subject="source")]},
            "artifact": {"sha256": ARTIFACT_DIGEST, "source_revision": CURRENT_REVISION,
                         "recorded_by": "builder-session",
                         "evidence": [evidence(bundle, "evidence/build.json", "build", case_id=None, subject="artifact")]},
            "deployment": None,
            "runtime": {"identity": "fixture-process-instance", "artifact_sha256": ARTIFACT_DIGEST,
                        "source_revision": CURRENT_REVISION, "deployment_identity": None,
                        "recorded_by": "executor-session",
                        "evidence": [evidence(bundle, "evidence/runtime.json", "runtime", case_id=None, subject="runtime")]},
        },
        "release_review": {"reviewer": "independent-session", "executor": "executor-session",
                           "reviewed_at": ledger.now(), "summary": "Synthetic independent review fixture",
                           "source_revision": CURRENT_REVISION, "artifact_sha256": ARTIFACT_DIGEST,
                           "runtime_identity": "fixture-process-instance",
                           "evidence": [evidence(bundle, "evidence/release-review.json", "verification", case_id=None, subject="release")]},
    }
    if environment != "local":
        data["provenance"]["deployment"] = {
            "identity": "fixture-deploy-001", "artifact_sha256": ARTIFACT_DIGEST,
            "recorded_by": "deployment-observer",
            "evidence": [evidence(bundle, "evidence/deployment.json", "deployment", case_id=None, subject="deployment")],
        }
        data["provenance"]["runtime"]["deployment_identity"] = "fixture-deploy-001"

    if with_fixed:
        from regression_evidence import runs_digest
        before = evidence(bundle, "evidence/before-1.log", content="Synthetic failure run 1: expected one fixture record, got two.\n")
        before2 = evidence(bundle, "evidence/before-2.log", content="Synthetic failure run 2: expected one fixture record, got two.\n")
        after2 = evidence(bundle, "evidence/after-2.log", content="Synthetic passing run 2: observed one fixture record.\n")
        test_definition = evidence(bundle, "evidence/regression-test.py", "source", content="def test_commit_once():\n    assert fixture.commit_count('op-1') == 1\n")
        oracle_definition = evidence(bundle, "evidence/oracle.json", "source", content='{"operation_id":"op-1","expected_durable_commits":1}\n')
        environment_definition = evidence(bundle, "evidence/environment.json", "source", content='{"runner":"synthetic-fixture","seed":17,"isolation":"disposable"}\n')
        comparison = {
            "schema_version": 1, "case_id": "C-001", "test_id": "fixture.test_commit_once",
            "assertion_id": "one_durable_commit", "test_sha256": test_definition["sha256"],
            "oracle_sha256": oracle_definition["sha256"],
            "environment_id": "sha256:" + environment_definition["sha256"],
            "buggy_revision": BEFORE_REVISION, "fixed_revision": CURRENT_REVISION,
            "fixed_artifact_sha256": ARTIFACT_DIGEST,
            "author": "fixer-session", "verifier": "independent-session", "runs": [],
        }
        for phase, observations in (("before", [before, before2]), ("after", [run, after2])):
            for repetition, observation in enumerate(observations, 1):
                comparison["runs"].append({
                    "phase": phase, "repetition": repetition,
                    "revision": BEFORE_REVISION if phase == "before" else CURRENT_REVISION,
                    "test_id": comparison["test_id"], "test_sha256": comparison["test_sha256"],
                    "oracle_sha256": comparison["oracle_sha256"], "environment_id": comparison["environment_id"],
                    "outcome": "failed" if phase == "before" else "passed",
                    "exit_code": 1 if phase == "before" else 0,
                    "failure_kind": "assertion" if phase == "before" else None,
                    "assertion_id": comparison["assertion_id"] if phase == "before" else None,
                    "artifact_sha256": ARTIFACT_DIGEST if phase == "after" else "a" * 64,
                    "evidence": [observation],
                })
        review = {key: comparison[key] for key in (
            "case_id", "test_id", "assertion_id", "test_sha256", "oracle_sha256",
            "environment_id", "buggy_revision", "fixed_revision", "author")}
        review.update({"schema_version": 1, "kind": "independent_regression_review",
                       "reviewer": comparison["verifier"], "runs_sha256": runs_digest(comparison["runs"]),
                       "verdict": "confirmed", "reviewed_at": ledger.now()})
        review_evidence = evidence(bundle, "evidence/fix-review.json", "verification", content=json.dumps(review))
        comparison["verification"] = {"path": review_evidence["path"], "sha256": review_evidence["sha256"]}
        comparison_evidence = evidence(bundle, "regression-C001.json", "test", content=json.dumps(comparison))
        data["findings"] = [{
            "id": "F-001", "title": "Duplicate synthetic fixture operation", "impact": "Duplicate record",
            "severity": "P1", "kind": "defect", "confidence": "certain", "reported_by": "hunter-session",
            "expected": "One record", "actual": "Two records before repair", "steps": ["Run the fixture twice with one operation ID"],
            "coverage_ids": ["C-001"], "evidence": [before],
            "root_cause": {"status": "unknown", "hypothesis": "", "evidence": []},
            "resolution": {
                "state": "fixed", "fixer": "fixer-session", "verifier": "independent-session",
                "fixed_revision": CURRENT_REVISION, "verified_at": review["reviewed_at"], "summary": "Synthetic before/after review",
                "regression": {"case_ids": ["C-001"], "record": comparison_evidence,
                               "test_definition": test_definition, "oracle_definition": oracle_definition,
                               "environment_definition": environment_definition},
                "verification_evidence": [review_evidence],
            },
        }]
    data["release_review"]["reviewed_at"] = ledger.now()
    return data


def make_v1_fixture(bundle: Path) -> dict:
    item = evidence(bundle, "legacy.log")
    return {"schema_version": 1,
            "scope": {"id": "legacy-audit", "target": "https://example.test", "profile": "advanced",
                      "environment": "local", "started_at": ledger.now(), "build": None,
                      "roles": ["user"], "viewports": ["desktop"]},
            "capabilities": {}, "coverage": [{"id": "C-001", "route": "/", "role": "user", "viewport": "desktop",
                                                "state": "success", "expected": "Fixture renders", "status": "passed",
                                                "reason": "", "evidence": [item]}], "findings": []}


class LedgerContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="deep-audit-ledger-test-")
        self.bundle = Path(self.temp.name)
        self.data = make_v2_fixture(self.bundle)

    def tearDown(self):
        self.temp.cleanup()

    def result(self, data=None):
        return ledger.Validator(self.bundle).validate(self.data if data is None else data)

    def assertInvalid(self, data=None, text=None):
        result = self.result(data)
        self.assertFalse(result["gates"]["ledger_valid"], result)
        self.assertFalse(result["gates"]["release_accepted"], result)
        if text:
            self.assertTrue(any(text in message for message in result["integrity"]["errors"]), result)
        return result

    def write(self, data=None):
        path = self.bundle / "audit.json"
        path.write_text(json.dumps(self.data if data is None else data))
        return path

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], text=True, capture_output=True, timeout=15)

    def mutate_comparison(self, data, mutation, rebind_review=False):
        from regression_evidence import runs_digest
        resolution = data["findings"][0]["resolution"]
        record = resolution["regression"]["record"]
        path = self.bundle / record["path"]
        comparison = json.loads(path.read_text())
        mutation(comparison)
        if rebind_review:
            review_metadata = resolution["verification_evidence"][0]
            review_path = self.bundle / review_metadata["path"]
            review = json.loads(review_path.read_text())
            for field in ("case_id", "test_id", "assertion_id", "test_sha256", "oracle_sha256",
                          "environment_id", "buggy_revision", "fixed_revision", "author"):
                review[field] = comparison[field]
            review["runs_sha256"] = runs_digest(comparison["runs"])
            review["reviewed_at"] = ledger.now()
            resolution["verified_at"] = review["reviewed_at"]
            review_path.write_text(json.dumps(review))
            review_metadata["sha256"] = hashlib.sha256(review_path.read_bytes()).hexdigest()
            comparison["verification"]["sha256"] = review_metadata["sha256"]
        path.write_text(json.dumps(comparison))
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        data["release_review"]["reviewed_at"] = ledger.now()

    def test_successful_native_fixture_has_distinct_gates(self):
        result = self.result()
        self.assertTrue(result["gates"]["ledger_valid"], result)
        self.assertTrue(result["gates"]["audit_complete"], result)
        self.assertTrue(result["gates"]["recorded_checks_passed"], result)
        self.assertTrue(result["gates"]["release_accepted"], result)
        self.assertFalse(result["acceptance"]["product_accepted"])

    def test_supported_target_types(self):
        for kind in sorted(ledger.TARGET_KINDS):
            with self.subTest(kind=kind):
                data = make_v2_fixture(self.bundle, kind=kind)
                self.assertTrue(self.result(data)["gates"]["release_accepted"])

    def test_staging_provenance_is_complete(self):
        data = make_v2_fixture(self.bundle, kind="web", environment="staging")
        self.assertTrue(self.result(data)["gates"]["release_accepted"])

    def test_missing_build_does_not_gain_release_acceptance(self):
        self.data["provenance"]["artifact"] = None
        self.data["coverage"][0]["observed_build"] = None
        result = self.result()
        self.assertTrue(result["gates"]["ledger_valid"])
        self.assertTrue(result["gates"]["recorded_checks_passed"])
        self.assertFalse(result["gates"]["release_accepted"])

    def test_missing_deployment_blocks_staging_but_not_local(self):
        self.data["scope"]["environment"] = "staging"
        self.data["provenance"]["runtime"]["deployment_identity"] = "unknown-deploy"
        result = self.result()
        self.assertTrue(result["gates"]["ledger_valid"])
        self.assertFalse(result["gates"]["release_accepted"])

    def test_mismatched_runtime_artifact_is_invalid(self):
        self.data["provenance"]["runtime"]["artifact_sha256"] = "f" * 64
        self.assertInvalid(text="does not match the built artifact")

    def test_mismatched_artifact_source_is_invalid(self):
        self.data["provenance"]["artifact"]["source_revision"] = BEFORE_REVISION
        self.assertInvalid(text="does not match recorded source revision")

    def test_case_from_old_artifact_blocks_release(self):
        self.data["coverage"][0]["observed_build"] = "f" * 64
        result = self.result()
        self.assertTrue(result["gates"]["ledger_valid"])
        self.assertTrue(result["gates"]["recorded_checks_passed"])
        self.assertFalse(result["gates"]["release_accepted"])

    def test_boolean_claim_cannot_bypass_evidence_gate(self):
        self.data["release_review"] = None
        self.data["release_accepted"] = True
        self.data["product_accepted"] = True
        result = self.result()
        self.assertFalse(result["gates"]["release_accepted"])
        self.assertFalse(result["acceptance"]["product_accepted"])

    def test_independent_release_review_is_required(self):
        self.data["release_review"]["reviewer"] = "executor-session"
        self.assertInvalid(text="must be distinct")

    def test_release_review_cannot_relabel_runtime_evidence(self):
        item = copy.deepcopy(self.data["provenance"]["runtime"]["evidence"][0])
        item.update({"type": "verification", "subject": "release"})
        self.data["release_review"]["evidence"] = [item]
        self.assertInvalid(text="independent review evidence")

    def test_uppercase_digest_cannot_bypass_reused_review_check(self):
        item = copy.deepcopy(self.data["provenance"]["runtime"]["evidence"][0])
        item.update({"type": "verification", "subject": "release", "sha256": item["sha256"].upper()})
        self.data["release_review"]["evidence"] = [item]
        self.assertInvalid(text="independent review evidence")

    def test_actor_whitespace_cannot_fake_independence(self):
        self.data["release_review"]["reviewer"] = " executor-session "
        self.assertInvalid(text="distinct")
        data = make_v2_fixture(self.bundle, with_fixed=True)
        data["findings"][0]["resolution"]["verifier"] = " fixer-session "
        self.assertInvalid(data, "fixer and verifier")

    def test_actor_case_variation_cannot_fake_independence(self):
        self.data["release_review"]["reviewer"] = "EXECUTOR-SESSION"
        self.assertInvalid(text="distinct")

    def test_release_review_must_follow_actual_fix_review_record(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        resolution = data["findings"][0]["resolution"]
        baseline = datetime.now(timezone.utc)
        fix_time = (baseline + timedelta(seconds=20)).isoformat()
        resolution["verified_at"] = fix_time
        review_meta = resolution["verification_evidence"][0]
        review_file = self.bundle / review_meta["path"]
        review = json.loads(review_file.read_text())
        review["reviewed_at"] = fix_time
        review_file.write_text(json.dumps(review))
        review_meta.update(sha256=hashlib.sha256(review_file.read_bytes()).hexdigest(), observed_at=fix_time)
        record_meta = resolution["regression"]["record"]
        record_file = self.bundle / record_meta["path"]
        comparison = json.loads(record_file.read_text())
        comparison["verification"]["sha256"] = review_meta["sha256"]
        record_file.write_text(json.dumps(comparison))
        record_meta["sha256"] = hashlib.sha256(record_file.read_bytes()).hexdigest()
        data["release_review"]["reviewed_at"] = (baseline + timedelta(seconds=10)).isoformat()
        self.assertInvalid(data, "final release review predates")

    def test_stale_release_review_is_invalid(self):
        self.data["release_review"]["reviewed_at"] = "2020-01-01T00:00:00Z"
        self.assertInvalid(text="predates the observations")

    def test_future_observation_is_invalid(self):
        self.data["coverage"][0]["evidence"][0]["observed_at"] = "2099-01-01T00:00:00Z"
        self.assertInvalid(text="future")

    def test_fixed_finding_retains_original_history_and_passes(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        original = copy.deepcopy(data["findings"][0]["evidence"])
        result = self.result(data)
        self.assertTrue(result["gates"]["release_accepted"], result)
        self.assertEqual(data["findings"][0]["evidence"], original)
        self.assertEqual(result["acceptance"]["findings"], 1)
        self.assertEqual(result["acceptance"]["dispositions"], {"fixed": 1})

    def test_free_text_fixed_status_does_not_close_finding(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        data["findings"][0]["resolution"] = {"state": "open"}
        data["findings"][0]["fix_status"] = "fixed and independently verified"
        result = self.result(data)
        self.assertTrue(result["gates"]["audit_complete"])
        self.assertFalse(result["gates"]["recorded_checks_passed"])
        self.assertFalse(result["gates"]["release_accepted"])

    def test_self_verified_fix_is_invalid(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        data["findings"][0]["resolution"]["verifier"] = "fixer-session"
        self.assertInvalid(data, "fixer and verifier")

    def test_import_error_is_not_regression_proof(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        self.mutate_comparison(data, lambda record: record["runs"][0].update(failure_kind="import"), rebind_review=True)
        self.assertInvalid(data, "runner_or_environment_failure")

    def test_different_test_cannot_prove_a_fix(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        self.mutate_comparison(data, lambda record: record["runs"][2].update(test_id="unrelated.always_pass"), rebind_review=True)
        self.assertInvalid(data, "test_id_mismatch")

    def test_changed_oracle_is_bound_to_actual_file(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        oracle = data["findings"][0]["resolution"]["regression"]["oracle_definition"]
        path = self.bundle / oracle["path"]
        path.write_text('{"expected_durable_commits":"anything"}')
        oracle["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertInvalid(data, "actual immutable definition file")

    def test_environment_drift_cannot_prove_a_fix(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        self.mutate_comparison(data, lambda record: record["runs"][2].update(environment_id="different-environment"), rebind_review=True)
        self.assertInvalid(data, "environment_id_mismatch")

    def test_passing_exit_code_must_not_be_boolean(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        self.mutate_comparison(data, lambda record: record["runs"][2].update(exit_code=False), rebind_review=True)
        self.assertInvalid(data, "integer zero")

    def test_fix_needs_current_build_retest(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        def old_artifact(record):
            record["fixed_artifact_sha256"] = "e" * 64
            for run in record["runs"]:
                if run["phase"] == "after":
                    run["artifact_sha256"] = "e" * 64
        self.mutate_comparison(data, old_artifact, rebind_review=True)
        result = self.result(data)
        self.assertTrue(result["gates"]["ledger_valid"])
        self.assertFalse(result["gates"]["release_accepted"])

    def test_fix_verification_needs_separate_evidence(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        resolution = data["findings"][0]["resolution"]
        item = copy.deepcopy(data["coverage"][0]["evidence"][0])
        item["type"] = "verification"
        resolution["verification_evidence"] = [item]
        self.assertInvalid(data, "distinct independent review")

    def reviewed_disposition(self, state):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        finding = data["findings"][0]
        finding["resolution"] = {
            "state": state, "reviewer": "independent-reviewer", "reviewed_at": ledger.now(),
            "reason": "Synthetic disposition decision", "owner": "fixture-owner",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "evidence": [evidence(self.bundle, "evidence/disposition.json", "verification")],
        }
        data["release_review"]["reviewed_at"] = ledger.now()
        return data

    def test_high_risk_cannot_be_accepted_as_residual_risk(self):
        data = self.reviewed_disposition("accepted_risk")
        self.assertInvalid(data, "critical/high findings")

    def test_low_risk_acceptance_requires_current_decision(self):
        data = self.reviewed_disposition("accepted_risk")
        data["findings"][0]["severity"] = "P2"
        self.assertTrue(self.result(data)["gates"]["release_accepted"])
        data["findings"][0]["resolution"]["expires_at"] = "2020-01-01T00:00:00Z"
        result = self.result(data)
        self.assertTrue(result["gates"]["ledger_valid"])
        self.assertFalse(result["gates"]["recorded_checks_passed"])
        self.assertFalse(result["gates"]["release_accepted"])

    def test_rejection_requires_independent_reviewer(self):
        data = self.reviewed_disposition("rejected")
        self.assertTrue(self.result(data)["gates"]["release_accepted"])
        data["findings"][0]["resolution"]["reviewer"] = data["findings"][0]["reported_by"]
        self.assertInvalid(data, "reviewer distinct from its reporter")

    def test_relabeling_original_failure_does_not_refute_it(self):
        data = self.reviewed_disposition("rejected")
        reused = copy.deepcopy(data["findings"][0]["evidence"][0])
        reused.update(type="verification", sha256=reused["sha256"].upper())
        data["findings"][0]["resolution"]["evidence"] = [reused]
        self.assertInvalid(data, "distinct review record")

    def test_acknowledgment_cannot_hide_a_defect(self):
        data = self.reviewed_disposition("acknowledged")
        self.assertInvalid(data, "reserved for design/product suggestions")
        data["findings"][0]["kind"] = "suggestion"
        self.assertTrue(self.result(data)["gates"]["release_accepted"])

    def test_open_suggestion_does_not_block_functional_acceptance(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        data["findings"][0].update({"kind": "suggestion", "resolution": {"state": "open"}})
        self.assertTrue(self.result(data)["gates"]["release_accepted"])

    def test_confirmed_cause_requires_evidence(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        data["findings"][0]["root_cause"]["status"] = "confirmed"
        self.assertInvalid(data, "must contain evidence")

    def test_failed_investigation_can_be_complete_without_release(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        data["coverage"][0]["status"] = "failed"
        data["findings"][0]["resolution"] = {"state": "open"}
        result = self.result(data)
        self.assertTrue(result["gates"]["audit_complete"], result)
        self.assertFalse(result["gates"]["recorded_checks_passed"])
        self.assertFalse(result["gates"]["release_accepted"])

    def test_unexplained_failed_case_is_incomplete(self):
        self.data["coverage"][0]["status"] = "failed"
        self.assertFalse(self.result()["gates"]["audit_complete"])

    def test_critical_required_exclusion_does_not_make_green(self):
        self.data["coverage"][0].update({"status": "out_of_scope", "reason": "No fixture account"})
        self.data["scope"]["exclusions"] = [{"case_id": "C-001", "reason": "No fixture account"}]
        result = self.result()
        self.assertTrue(result["gates"]["ledger_valid"])
        self.assertFalse(result["gates"]["audit_complete"])
        self.assertFalse(result["gates"]["release_accepted"])

    def test_low_risk_exclusion_is_explicit_and_preserves_scope(self):
        row = copy.deepcopy(self.data["coverage"][0])
        row.update({"id": "C-002", "risk": "P3", "required": False, "status": "out_of_scope",
                    "reason": "Unsupported legacy browser outside declared support", "evidence": []})
        self.data["coverage"].append(row)
        self.data["scope"]["exclusions"] = [{"case_id": "C-002", "reason": row["reason"]}]
        self.assertTrue(self.result()["gates"]["release_accepted"])
        self.data["scope"]["exclusions"] = []
        self.assertInvalid(text="scope.exclusions")

    def test_untested_blocked_and_unknown_are_not_passes(self):
        for status in ("not_tested", "blocked", "unknown"):
            with self.subTest(status=status):
                self.data["coverage"][0].update({"status": status, "reason": "Execution incomplete"})
                result = self.result()
                self.assertTrue(result["gates"]["ledger_valid"])
                self.assertFalse(result["gates"]["audit_complete"])
                self.assertFalse(result["gates"]["release_accepted"])

    def test_evidence_digest_is_mandatory(self):
        self.data["coverage"][0]["evidence"][0].pop("sha256")
        self.assertInvalid(text="SHA-256")

    def test_evidence_content_tampering_is_detected(self):
        (self.bundle / "evidence/case.log").write_text("Changed after collection")
        self.assertInvalid(text="does not match the evidence file")

    def test_wrong_evidence_case_relationship_is_invalid(self):
        self.data["coverage"][0]["evidence"][0]["case_id"] = "C-OTHER"
        self.assertInvalid(text="must reference a case covered")

    def test_wrong_provenance_subject_is_invalid(self):
        self.data["provenance"]["artifact"]["evidence"][0]["subject"] = "runtime"
        self.assertInvalid(text="must be artifact")

    def test_traversal_and_absolute_evidence_paths_are_rejected(self):
        for path in ("../outside.log", "/etc/passwd", "C:\\outside.log", "a/../../outside.log"):
            with self.subTest(path=path):
                self.data["coverage"][0]["evidence"][0]["path"] = path
                self.assertInvalid(text="relative bundle path")

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="audit-outside-") as outside:
            target = Path(outside) / "secret.log"
            target.write_text("outside fixture")
            (self.bundle / "escape.log").symlink_to(target)
            self.data["coverage"][0]["evidence"][0]["path"] = "escape.log"
            self.assertInvalid(text="escapes the bundle")

    def test_empty_evidence_is_rejected(self):
        (self.bundle / "evidence/case.log").write_bytes(b"")
        self.assertInvalid(text="nonempty regular file")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO available on Unix")
    def test_nonregular_evidence_is_rejected_without_reading(self):
        os.mkfifo(self.bundle / "pipe")
        self.data["coverage"][0]["evidence"][0]["path"] = "pipe"
        self.assertInvalid(text="nonempty regular file")

    def test_malformed_json_types_never_raise(self):
        paths = [("scope",), ("coverage",), ("findings",), ("provenance",), ("release_review",),
                 ("scope", "target"), ("scope", "roles"), ("scope", "exclusions"),
                 ("coverage", 0), ("coverage", 0, "id"), ("coverage", 0, "status"),
                 ("coverage", 0, "risk"), ("coverage", 0, "evidence"),
                 ("coverage", 0, "evidence", 0), ("coverage", 0, "evidence", 0, "sha256"),
                 ("provenance", "source"), ("provenance", "artifact", "source_revision"),
                 ("release_review", "reviewer")]
        values = [None, True, 1, [], {}, ["x"], {"x": "y"}]
        for path in paths:
            for value in values:
                with self.subTest(path=path, value=value):
                    data = copy.deepcopy(self.data)
                    parent = data
                    for part in path[:-1]:
                        parent = parent[part]
                    parent[path[-1]] = value
                    result = self.result(data)
                    self.assertIsInstance(result["gates"]["ledger_valid"], bool)

    def test_malformed_finding_types_never_raise(self):
        original = make_v2_fixture(self.bundle, with_fixed=True)
        paths = [("findings", 0), ("findings", 0, "kind"), ("findings", 0, "coverage_ids"),
                 ("findings", 0, "root_cause"), ("findings", 0, "resolution"),
                 ("findings", 0, "resolution", "state"), ("findings", 0, "resolution", "regression"),
                 ("findings", 0, "resolution", "regression", "case_ids"),
                 ("findings", 0, "resolution", "regression", "before")]
        for path in paths:
            for value in (None, [], {}, True, 2):
                with self.subTest(path=path, value=value):
                    data = copy.deepcopy(original)
                    parent = data
                    for part in path[:-1]:
                        parent = parent[part]
                    parent[path[-1]] = value
                    self.result(data)

    def test_legacy_v1_integrity_and_strict_semantics_remain(self):
        result = self.result(make_v1_fixture(self.bundle))
        self.assertTrue(result["integrity"]["valid"])
        self.assertTrue(result["acceptance"]["strict_gate_passed"])
        self.assertFalse(result["gates"]["release_accepted"])
        self.assertFalse(result["acceptance"]["product_accepted"])

    def test_native_init_creates_empty_v2_draft(self):
        target = self.bundle / "new-native"
        result = self.cli("init", "--out", target, "--target-kind", "native", "--target", "com.example.NativeFixture", "--platform", "macos")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((target / "audit.json").read_text())
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(data["coverage"], [])
        self.assertTrue(all(value is None for value in data["provenance"].values()))
        validation = ledger.Validator(target).validate(data)
        self.assertTrue(validation["gates"]["ledger_valid"], validation)
        self.assertFalse(validation["gates"]["audit_complete"])
        self.assertFalse(validation["gates"]["release_accepted"])

    def test_init_never_overwrites(self):
        target = self.bundle / "exists"
        target.mkdir()
        (target / "audit.json").write_text("owned existing content")
        result = self.cli("init", "--out", target, "--target", "https://example.test")
        self.assertEqual(result.returncode, 2)
        self.assertEqual((target / "audit.json").read_text(), "owned existing content")

    def test_cli_gate_exit_codes(self):
        path = self.write()
        for args in (("--gate", "ledger"), ("--gate", "audit"), ("--strict",), ("--gate", "release")):
            with self.subTest(args=args):
                result = self.cli("validate", path, *args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.data["release_review"] = None
        self.write()
        self.assertEqual(self.cli("validate", path, "--gate", "release").returncode, 1)
        self.assertEqual(self.cli("validate", path, "--strict").returncode, 0)

    def test_legacy_release_gate_fails(self):
        path = self.write(make_v1_fixture(self.bundle))
        self.assertEqual(self.cli("validate", path, "--gate", "release").returncode, 1)

    def test_evidence_helper_hashes_without_updating_audit(self):
        path = self.write()
        before = path.read_bytes()
        result = self.cli("evidence", "--bundle", self.bundle, "--path", "evidence/case.log", "--type", "test",
                          "--case-id", "C-001", "--observed-at", ledger.now(), "--summary", "Fixture only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["sha256"], self.data["coverage"][0]["evidence"][0]["sha256"])
        self.assertEqual(path.read_bytes(), before)

    def test_evidence_helper_rejects_escape_before_hashing(self):
        result = self.cli("evidence", "--bundle", self.bundle, "--path", "../outside.log", "--type", "test",
                          "--case-id", "C-001", "--observed-at", ledger.now(), "--summary", "Fixture only")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_report_renders_history_and_never_overwrites(self):
        data = make_v2_fixture(self.bundle, with_fixed=True)
        path = self.write(data)
        output = self.bundle / "report.md"
        result = self.cli("report", path, "--out", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Original observation", output.read_text())
        self.assertIn("release_accepted", output.read_text())
        before = output.read_bytes()
        self.assertEqual(self.cli("report", path, "--out", output).returncode, 2)
        self.assertEqual(output.read_bytes(), before)

    def test_malformed_json_is_bounded_cli_error(self):
        for text in ('{"schema_version":2,"schema_version":1}', '{"value":NaN}', '[]', '{'):
            with self.subTest(text=text):
                path = self.bundle / "malformed.json"
                path.write_text(text)
                result = self.cli("validate", path)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_credentials_in_target_are_rejected(self):
        for url in ("https://user:secret@example.test", "https://example.test?token=secret"):
            with self.subTest(url=url):
                self.data["scope"]["target"] = {"kind": "web", "locator": url}
                self.assertInvalid()

    def test_cli_target_is_an_identifier_not_a_shell_command(self):
        self.data["scope"]["target"] = {"kind": "cli", "locator": "tool --dangerous"}
        self.assertInvalid(text="without shell arguments")

    def test_unsupported_schema_is_invalid(self):
        self.data["schema_version"] = True
        self.assertFalse(self.result()["gates"]["ledger_valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
