#!/usr/bin/env python3
"""Behavioral checks for safe capability discovery."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_capabilities as probe


class CapabilityTests(unittest.TestCase):
    def test_readiness_never_implies_execution(self):
        self.assertEqual(probe.readiness({"path": None}), "missing")
        self.assertEqual(probe.readiness({"path": "/tool"}), "discovered")
        self.assertEqual(probe.readiness({"path": "/tool", "version_probe": {"exit_code": 1}}),
                         "not_verified_runnable")
        self.assertEqual(probe.readiness({"path": "/tool", "version_probe": {"exit_code": 0}}),
                         "runnable")

    def test_timeout_is_an_explicit_failure(self):
        result = probe.run([sys.executable, "-c", "import time; time.sleep(1)"], timeout=0.03)
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["error"], "timeout")

    @unittest.skipUnless(shutil.which("node"), "Node unavailable for package metadata fixture")
    def test_metadata_resolution_does_not_execute_package_and_preserves_complete_json(self):
        with tempfile.TemporaryDirectory(prefix="audit-probe-") as directory:
            root = pathlib.Path(directory)
            marker = root / "executed.txt"
            for name in probe.PACKAGES:
                package = root / "node_modules" / name
                package.mkdir(parents=True)
                (package / "package.json").write_text(json.dumps({
                    "name": name, "version": "1.2.3", "exports": "./index.js",
                }))
                (package / "index.js").write_text(
                    "require('fs').writeFileSync(" + json.dumps(str(marker)) + ",'bad');")
            result = probe.inventory(root, timeout_seconds=10)
            self.assertFalse(marker.exists())
            self.assertEqual(set(result["packages"]), set(probe.PACKAGES))
            for item in result["packages"].values():
                self.assertEqual(item["status"], "available")
                self.assertEqual(item["readiness"], "discovered")
                self.assertFalse(item["fixture_verified"])
                self.assertFalse(item["product_executed"])
            self.assertEqual(result["playwright"]["browser_readiness"], "not_tested")
            self.assertEqual(result["product_behavior"], "not_tested")
            for item in result["commands"].values():
                self.assertFalse(item["fixture_verified"])
                self.assertFalse(item["product_executed"])

    def test_invalid_project_cannot_create_or_install_anything(self):
        with tempfile.TemporaryDirectory(prefix="audit-probe-invalid-") as directory:
            missing = pathlib.Path(directory) / "absent"
            result = subprocess.run(
                [sys.executable, "-B", str(pathlib.Path(probe.__file__)),
                 "--project", str(missing)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(missing.exists())

    def test_unknown_tool_arguments_are_not_executed(self):
        result = subprocess.run(
            [sys.executable, "-B", str(pathlib.Path(probe.__file__)),
             "--command", "echo dangerous"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("dangerous\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
