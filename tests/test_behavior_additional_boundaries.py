"""Checks for documented fixture boundaries beyond its seeded demonstrations."""
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import behavior_lab as lab


class AdditionalBoundaryTests(unittest.TestCase):
    def test_correct_partial_batch_with_missing_id_satisfies_oracle(self):
        with tempfile.TemporaryDirectory(prefix="missing-batch-test-") as temporary:
            with lab.serve("fixed", Path(temporary) / "state.sqlite") as (port, app):
                requested = [1, 999]
                receipt = lab.request(port, "/batch", {"ids": requested})
                with closing(sqlite3.connect(str(app.database))) as db:
                    rows = [{"id": row[0], "value": row[1]}
                            for row in db.execute("SELECT id,value FROM documents WHERE id IN (?,?) ORDER BY id", requested)]
                observation = {"requested_ids": requested, "rows": rows,
                               "status_code": receipt["status_code"], "response": json.loads(receipt["body"])}
                self.assertEqual(observation["response"]["items"], [
                    {"id": 1, "ok": True}, {"id": 999, "ok": False, "error": "locked_or_missing"}])
                self.assertFalse(observation["response"]["all_succeeded"])
                self.assertTrue(lab.evaluate_observation("batch", observation), observation)

    def test_numeric_done_marker_is_not_boolean_terminal_success(self):
        body = '{"done":1}\n'
        receipt = {"status_code": 200, "body": body, "received_bytes": len(body),
                   "declared_bytes": len(body), "truncated": False}
        self.assertNotEqual(lab.consume_stream("fixed", receipt), "completed")

    def test_check_digest_binds_atomic_snapshot_expected_input(self):
        original = Path(lab.__file__).read_text(encoding="utf-8")
        changed = original.replace('first = {"theme": "new"}', 'first = {"theme": "changed-oracle-input"}')
        self.assertNotEqual(changed, original, "The test must actually change the atomic fixture's expected input")
        with tempfile.TemporaryDirectory(prefix="check-hash-test-") as temporary:
            path = Path(temporary) / "changed_lab.py"
            path.write_text(changed, encoding="utf-8")
            spec = importlib.util.spec_from_file_location("changed_lab", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertNotEqual(lab.checks_hash(), module.checks_hash(),
                                "Changing a fixture's expected result must change its recorded check digest")


if __name__ == "__main__":
    unittest.main()
