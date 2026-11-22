#!/usr/bin/env python3
"""Scope and missing-capability checks; real binaries require the smoke helper."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verify_network_tools as tools


class NetworkToolTests(unittest.TestCase):
    def test_missing_tools_are_not_verified(self):
        with patch.object(tools.shutil, "which", return_value=None), patch.object(tools, "fixture") as fixture:
            result = tools.verify_tools(["k6", "toxiproxy"])
        fixture.assert_not_called()
        self.assertFalse(result["all_selected_fixture_verified"])
        self.assertFalse(result["product_executed"])
        self.assertFalse(result["product_accepted"])
        self.assertTrue(result["temporary_data_removed"])
        self.assertEqual([record["state"] for record in result["tools"]], ["missing", "missing"])

    def test_no_external_target_argument(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            tools.main(["--target", "https://example.invalid"])
        self.assertEqual(result.exception.code, 2)

    def test_unknown_or_duplicate_tool_rejected(self):
        for selection in ("curl", "k6,k6", "k6,", ""):
            with self.subTest(selection=selection), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                tools.main(["--tools", selection])

    def test_existing_and_symlink_output_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "existing.json"
            existing.write_text("keep")
            link = Path(temporary) / "link.json"
            link.symlink_to(Path(temporary) / "missing.json")
            for path in (existing, link):
                with patch.object(tools, "verify_tools") as verify, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    tools.main(["--out", str(path)])
                verify.assert_not_called()
            self.assertEqual(existing.read_text(), "keep")

    def test_user_k6_outputs_and_proxy_configuration_not_inherited(self):
        with patch.dict(os.environ, {"K6_OUT": "cloud", "K6_WEB_DASHBOARD": "true", "HTTPS_PROXY": "https://example.invalid", "PATH": "/bounded/path"}):
            environment = tools.child_environment()
        self.assertNotIn("K6_OUT", environment)
        self.assertNotIn("K6_WEB_DASHBOARD", environment)
        self.assertNotIn("HTTPS_PROXY", environment)
        self.assertEqual(environment["PATH"], "/bounded/path")

    def test_missing_tool_receipt_written_truthfully(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "receipt.json"
            with patch.object(tools.shutil, "which", return_value=None), contextlib.redirect_stdout(io.StringIO()):
                status = tools.main(["--tools", "k6", "--out", str(output)])
            result = json.loads(output.read_text())
        self.assertEqual(status, 1)
        self.assertFalse(result["all_selected_fixture_verified"])


if __name__ == "__main__":
    unittest.main()
