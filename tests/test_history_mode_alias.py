"""A historical file mode is part of its identity, even for identical blob bytes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import public_scan


class HistoricalModeTests(unittest.TestCase):
    def test_regular_file_head_does_not_hide_historical_symlink(self):
        with tempfile.TemporaryDirectory(prefix="mode-alias-review-") as temporary:
            root = Path(temporary)
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
            def git(*args):
                return subprocess.run(["git", *args], cwd=root, env=env, check=True,
                                      capture_output=True, timeout=10)
            for args in (("init", "-q"), ("config", "user.name", "fixture"),
                         ("config", "user.email", "fixture@example.invalid"),
                         ("config", "commit.gpgsign", "false"),
                         ("config", "core.hooksPath", os.devnull)):
                git(*args)
            leaf = root / "leaf"
            try:
                leaf.symlink_to("target")
            except OSError as error:
                self.skipTest(str(error))
            git("add", "leaf")
            git("commit", "-qm", "Add symlink fixture")
            leaf.unlink()
            leaf.write_text("target")  # Identical blob, same path, different mode.
            git("add", "leaf")
            git("commit", "-qm", "Replace with regular file")
            report = public_scan.scan(root, history=True)
            self.assertEqual(report["status"], "failed", report)
            self.assertTrue(any(row["rule"] == "historical-symlink-or-submodule-requires-review"
                                for row in report["findings"]), report)


if __name__ == "__main__":
    unittest.main()
