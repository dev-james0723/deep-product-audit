"""Independent disposable regressions for install and release-screen boundaries."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import install_skill
import package_skill
import public_scan


class IndependentPackageBoundaries(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="package-review-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def make_git(self, root):
        root.mkdir()
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0")
        def git(*args):
            return subprocess.run(["git", *args], cwd=root, env=env, check=True,
                                  capture_output=True, timeout=10)
        for args in (("init", "-q"), ("config", "user.name", "fixture"),
                     ("config", "user.email", "fixture@example.invalid"),
                     ("config", "commit.gpgsign", "false"),
                     ("config", "core.hooksPath", os.devnull)):
            git(*args)
        return git

    def test_removed_grader_directory_is_flagged_in_history(self):
        root = self.root / "history"
        git = self.make_git(root)
        heldout = root / "heldout"
        heldout.mkdir()
        (heldout / "cases.json").write_text('{"cases":[{"id":"sample","answer":"clean"}]}\n')
        git("add", ".")
        git("commit", "-qm", "Add fixture")
        shutil.rmtree(heldout)
        (root / "README.md").write_text("Public fixture\n")
        git("add", "-A")
        git("commit", "-qm", "Remove fixture")
        report = public_scan.scan(root, history=True)
        self.assertEqual(report["status"], "failed", report)
        self.assertTrue(any("private-or-grader" in row["rule"] and row["path"].startswith("history:")
                            for row in report["findings"]), report)

    def test_same_blob_at_safe_path_does_not_hide_forbidden_history_name(self):
        root = self.root / "history-alias"
        git = self.make_git(root)
        for name in ("README.md", ".env"):
            (root / name).write_text("Identical fixture bytes\n")
        git("add", ".")
        git("commit", "-qm", "Add fixtures")
        (root / ".env").unlink()
        git("add", "-A")
        git("commit", "-qm", "Remove private filename")
        report = public_scan.scan(root, history=True)
        self.assertEqual(report["status"], "failed", report)
        self.assertTrue(any("private-or-grader" in row["rule"] and row["path"].startswith("history:")
                            for row in report["findings"]), report)

    def test_documented_runtime_cli_keeps_install_verifiable(self):
        destination = self.root / "installed with spaces é"
        install_skill.install(destination)
        env = dict(os.environ)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        env.pop("PYTHONPYCACHEPREFIX", None)
        result = subprocess.run([sys.executable, str(destination / "scripts/regression_evidence.py"), "--help"],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(install_skill.verify(destination)["verified"])

    def test_uninstall_preserves_foreign_empty_directory(self):
        destination = self.root / "installed"
        install_skill.install(destination)
        foreign = destination / "user-owned-empty-folder"
        foreign.mkdir()
        with self.assertRaises(ValueError):
            install_skill.uninstall(destination)
        self.assertTrue(foreign.is_dir(), "An unowned directory must remain")

    def test_unlisted_arbitrary_files_never_enter_snapshot(self):
        clone = self.root / "source"
        shutil.copytree(package_skill.ROOT, clone, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist"))
        before, files_before = package_skill.runtime_snapshot(clone)
        (clone / "unlisted-private-data.txt").write_text("Private fixture content\n")
        (clone / "mystery-grader").mkdir()
        (clone / "mystery-grader/results.txt").write_text("Fixture answers\n")
        after, files_after = package_skill.runtime_snapshot(clone)
        self.assertEqual(before, after)
        self.assertEqual(files_before, files_after)

    def test_allowlisted_symlink_is_refused(self):
        clone = self.root / "source"
        shutil.copytree(package_skill.ROOT, clone, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist"))
        outside = self.root / "outside.txt"
        outside.write_text("Unrelated fixture\n")
        link = clone / "VERSION"
        link.unlink()
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaises(ValueError):
            package_skill.runtime_snapshot(clone)


if __name__ == "__main__":
    unittest.main()
