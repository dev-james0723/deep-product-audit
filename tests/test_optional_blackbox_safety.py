"""No-provider unit checks for the separately opted-in third-party example."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import os
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "optional_pocketbase_blackbox", ROOT / "examples" / "pocketbase_blackbox.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class _RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", "https://example.org/off-host")
        self.end_headers()

    def log_message(self, *_):
        pass


class OptionalBlackboxSafetyTests(unittest.TestCase):
    def test_app_redirect_is_not_followed_off_loopback(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHandler)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            status, body = MODULE.request(
                f"http://127.0.0.1:{server.server_address[1]}", "GET", "/redirect"
            )
            self.assertEqual(status, 302)
            self.assertEqual(body, {})
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())

    def test_vendor_process_does_not_inherit_personal_tokens(self):
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-secret-not-a-real-key",
            "GH_TOKEN": "test-not-a-real-gh-token",
            "AWS_SECRET_ACCESS_KEY": "test-not-a-real-aws-key",
        }):
            e = MODULE.sanitized_env(Path("/tmp/owned-test-home"))
        self.assertEqual(e["HOME"], "/tmp/owned-test-home")
        self.assertTrue({"OPENAI_API_KEY", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY"}.isdisjoint(e))
        self.assertFalse(any("test-not-a-real" in v for v in e.values()))


if __name__ == "__main__":
    unittest.main()
