"""Regressions for fixture-input identity and truthful per-item outcomes."""
from contextlib import closing
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import behavior_lab as lab


class OracleRegressionTests(unittest.TestCase):
    def changed_digest(self, old, new):
        source = Path(lab.__file__).read_text(encoding="utf-8")
        changed = source.replace(old, new)
        self.assertNotEqual(changed, source, "The mutation must affect a real fixture input")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changed_lab.py"
            path.write_text(changed, encoding="utf-8")
            spec = importlib.util.spec_from_file_location("changed_fixture", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.checks_hash()

    def test_hash_binds_database_seed_input(self):
        changed = self.changed_digest(
            "INSERT INTO documents VALUES(1,0,'old'),(2,1,'old');",
            "INSERT INTO documents VALUES(1,0,'new'),(2,1,'old');")
        self.assertNotEqual(lab.checks_hash(), changed)

    def test_hash_binds_stream_fixture_input(self):
        changed = self.changed_digest(
            'full = b\'{"delta":"hello"}\\n{"done":true}\\n\'',
            'full = b\'{"delta":"changed"}\\n{"done":true}\\n\'')
        self.assertNotEqual(lab.checks_hash(), changed)

    def test_hash_binds_transport_observation_helper(self):
        changed = self.changed_digest('"received_bytes": len(data)', '"received_bytes": len(data) + 1')
        self.assertNotEqual(lab.checks_hash(), changed)

    def test_all_missing_batch_items_are_correctly_reported_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            with lab.serve("fixed", Path(temporary) / "db.sqlite") as (port, app):
                requested = [998, 999]
                receipt = lab.request(port, "/batch", {"ids": requested})
                with closing(sqlite3.connect(str(app.database))) as db:
                    rows = [{"id": row[0], "value": row[1]} for row in db.execute(
                        "SELECT id,value FROM documents WHERE id IN (?,?)", requested)]
                observation = {"requested_ids": requested, "rows": rows, "status_code": receipt["status_code"],
                               "response": json.loads(receipt["body"])}
                self.assertTrue(lab.evaluate_observation("batch", observation))
                observation["response"]["all_succeeded"] = True
                self.assertFalse(lab.evaluate_observation("batch", observation))

    def batch_observation(self):
        return {"requested_ids": [1, 2], "rows": [{"id": 1, "value": "new"}, {"id": 2, "value": "old"}],
                "status_code": 200, "response": {"all_succeeded": False,
                "items": [{"id": 1, "ok": True}, {"id": 2, "ok": False}]}}

    def test_numeric_child_success_does_not_count_as_boolean_outcome(self):
        observation = self.batch_observation()
        observation["response"]["items"][0]["ok"] = 1
        self.assertFalse(lab.evaluate_observation("batch", observation))

    def test_duplicate_or_unrequested_child_outcomes_are_rejected(self):
        original = self.batch_observation()
        for items in ([{"id": 1, "ok": True}, {"id": 1, "ok": True}],
                      [{"id": 1, "ok": True}, {"id": 999, "ok": False}]):
            observation = copy.deepcopy(original)
            observation["response"]["items"] = items
            self.assertFalse(lab.evaluate_observation("batch", observation))

    def test_non_boolean_terminal_values_cannot_complete(self):
        for value in (1, 1.0, "true", None, False, [], {}):
            body = json.dumps({"done": value}) + "\n"
            receipt = {"status_code": 200, "body": body, "received_bytes": len(body),
                       "declared_bytes": len(body), "truncated": False}
            self.assertNotEqual(lab.consume_stream("fixed", receipt), "completed")

    def test_valid_formatted_terminal_event_is_accepted_by_independent_oracle(self):
        body = '{"delta": "hello"}\n{"done": true}\n'
        receipt = {"status_code": 200, "body": body, "received_bytes": len(body),
                   "declared_bytes": len(body), "truncated": False}
        receipt["application_state"] = lab.consume_stream("fixed", receipt)
        self.assertEqual(receipt["application_state"], "completed")
        self.assertTrue(lab.evaluate_observation("stream", receipt))


if __name__ == "__main__":
    unittest.main()
