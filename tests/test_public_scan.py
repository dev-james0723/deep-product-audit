"""Negative controls and privacy-preserving scanning, including deleted history."""
import os
import pathlib
import subprocess
import tempfile
import unittest

import public_scan


class PublicScanTests(unittest.TestCase):
    def test_secret_match_is_reported_without_value(self):
        secret = "ghp_" + "A" * 36
        rows = public_scan.content_findings(secret.encode(), "fixture")
        self.assertTrue(any(x["rule"] == "github-token" for x in rows))
        self.assertNotIn(secret, str(rows))

    def test_placeholder_email_and_ordinary_code_are_clean(self):
        self.assertEqual(public_scan.content_findings(b"fixture@example.invalid\nvalue=3\n", "fixture"), [])

    def test_personal_path_and_private_term_are_detected(self):
        path = "/" + "Users" + "/sample-person/source"
        rows = public_scan.content_findings((path + "\ninternal-only-project").encode(), "fixture", ["internal-only-project"])
        self.assertEqual({x["rule"] for x in rows}, {"personal-home-path", "private-term"})

    def test_binary_is_not_silently_accepted(self):
        self.assertEqual(public_scan.content_findings(b"\xff\x00", "opaque")[0]["rule"], "opaque-binary-requires-review")

    def test_history_detects_deleted_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
            def git(*args):
                subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, check=True)
            git("init", "-q")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "user.name", "fixture")
            git("config", "commit.gpgsign", "false")
            git("config", "core.hooksPath", os.devnull)
            p = root / "file.txt"
            p.write_text("ghp_" + "B" * 36)
            git("add", "file.txt")
            git("commit", "-qm", "fixture")
            p.write_text("clean\n")
            git("add", "file.txt")
            git("commit", "-qm", "remove")
            report = public_scan.scan(root, history=True)
            self.assertEqual(report["status"], "failed")
            self.assertTrue(any(x["rule"] == "github-token" and x["path"].startswith("history:") for x in report["findings"]))

    def test_empty_history_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            with self.assertRaises(ValueError):
                public_scan.scan(root, history=True)


if __name__ == "__main__":
    unittest.main()
