"""Public packaging boundaries and conservative installation lifecycle."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import install_skill
import package_skill


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="public-audit-package-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def test_runtime_excludes_tests_answers_and_demonstrations(self):
        metadata, files = package_skill.runtime_snapshot()
        self.assertFalse(metadata["grader_material_included"])
        self.assertNotIn("assets/evaluation-cases.json", files)
        self.assertNotIn("assets/trigger-cases.json", files)
        self.assertNotIn("scripts/benchmark_fixture.py", files)
        self.assertNotIn("scripts/behavior_lab.py", files)
        self.assertFalse(any(n.startswith(("tests/", "tools/", "docs/")) for n in files))

    def test_archive_is_deterministic_and_verifiable(self):
        a, b = self.root / "one.zip", self.root / "two.zip"
        first = package_skill.build(a)
        second = package_skill.build(b)
        self.assertEqual(first["sha256"], second["sha256"])
        with zipfile.ZipFile(a) as z:
            prefix = "deep-product-audit/"
            receipt = json.loads(z.read(prefix + package_skill.RECEIPT))
            for name, digest in receipt["files"].items():
                self.assertEqual(hashlib.sha256(z.read(prefix + name)).hexdigest(), digest)

    def test_archive_never_overwrites(self):
        out = self.root / "keep.zip"
        out.write_bytes(b"keep")
        with self.assertRaises(ValueError):
            package_skill.build(out)
        self.assertEqual(out.read_bytes(), b"keep")

    def test_install_verify_and_uninstall(self):
        dest = self.root / "path with spaces" / "deep-product-audit"
        result = install_skill.install(dest)
        self.assertTrue(result["verified"])
        self.assertEqual(result, install_skill.verify(dest))
        self.assertTrue(install_skill.uninstall(dest)["uninstalled"])
        self.assertFalse(dest.exists())

    def test_install_never_merges_existing_directory(self):
        dest = self.root / "existing"
        dest.mkdir()
        (dest / "user.txt").write_text("keep")
        with self.assertRaises(ValueError):
            install_skill.install(dest)
        self.assertEqual((dest / "user.txt").read_text(), "keep")

    def test_uninstall_preserves_modified_installation(self):
        dest = self.root / "installed"
        install_skill.install(dest)
        (dest / "SKILL.md").write_text("local change")
        with self.assertRaises(ValueError):
            install_skill.uninstall(dest)
        self.assertEqual((dest / "SKILL.md").read_text(), "local change")

    def test_uninstall_preserves_foreign_files(self):
        dest = self.root / "installed"
        install_skill.install(dest)
        (dest / "user-notes.txt").write_text("keep")
        with self.assertRaises(ValueError):
            install_skill.uninstall(dest)
        self.assertTrue((dest / "user-notes.txt").exists())

    def test_receipt_path_traversal_rejected(self):
        dest = self.root / "installed"
        install_skill.install(dest)
        path = dest / package_skill.RECEIPT
        receipt = json.loads(path.read_text())
        receipt["files"]["../outside"] = "0" * 64
        path.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            install_skill.verify(dest)

    def test_symlink_installation_is_refused(self):
        if not hasattr(pathlib.Path, "symlink_to"):
            self.skipTest("symlink API unavailable")
        dest = self.root / "installed"
        install_skill.install(dest)
        link = self.root / "alias"
        try:
            link.symlink_to(dest, target_is_directory=True)
        except OSError:
            self.skipTest("symlink privilege unavailable on this host")
        with self.assertRaises(ValueError):
            install_skill.uninstall(link)
        self.assertTrue(dest.exists())

    def test_portable_paths_reject_escape_drive_and_reserved_names(self):
        for name in ("../escape", "/absolute", "C:/escape", "a\\b", "CON.txt", "a//b", "a/../b", "a/b "):
            with self.subTest(name=name), self.assertRaises(ValueError):
                package_skill.safe_relative(name)

    def test_grader_allowlist_injection_is_refused(self):
        clone = self.root / "source"
        shutil.copytree(package_skill.ROOT, clone, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist"))
        spec_path = clone / "package-manifest.json"
        spec = json.loads(spec_path.read_text())
        spec["runtime_files"].append("scripts/benchmark_fixture.py")
        spec_path.write_text(json.dumps(spec))
        with self.assertRaises(ValueError):
            package_skill.runtime_snapshot(clone)

    def test_installed_ledger_runs_with_no_agent(self):
        dest = self.root / "installed"
        install_skill.install(dest)
        bundle = self.root / "audit-output"
        result = subprocess.run([sys.executable, "-B", str(dest / "scripts/audit_ledger.py"),
                                 "init", "--out", str(bundle), "--target", "fixture-cli",
                                 "--target-kind", "cli", "--profile", "standard", "--environment", "local"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((bundle / "audit.json").is_file())
        self.assertTrue(install_skill.verify(dest)["verified"])

    def test_evaluator_requires_external_manifest(self):
        result = subprocess.run([sys.executable, "-B", str(package_skill.ROOT / "scripts/evaluate_audit.py"),
                                 "prompts", "--out", str(self.root / "prompts.json")],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "prompts.json").exists())


if __name__ == "__main__":
    unittest.main()
