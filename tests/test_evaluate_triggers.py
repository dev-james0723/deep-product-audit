import unittest
from evaluate_triggers import score
class TriggerTests(unittest.TestCase):
    def test_correct_complete(self):
        cases={"schema_version":1,"cases":[{"id":"1","should_trigger":True},{"id":"2","should_trigger":False}]}
        got={"schema_version":1,"observations":[{"case_id":"1","triggered":True,"run_id":"r1","agent_session":"a"},{"case_id":"2","triggered":False,"run_id":"r2","agent_session":"b"}]}
        result=score(cases,got)
        self.assertTrue(result["comparison_complete"])
        self.assertEqual(result["precision"],1.0)
    def test_missing_stays_unknown(self):
        cases={"schema_version":1,"cases":[{"id":"1","should_trigger":True},{"id":"2","should_trigger":False}]}
        got={"schema_version":1,"observations":[]}
        self.assertFalse(score(cases,got)["comparison_complete"])
        self.assertEqual(score(cases,got)["confusion"]["not_measured"],2)
    def test_duplicate_rejected(self):
        cases={"schema_version":1,"cases":[{"id":"1","should_trigger":True}]}
        obs={"case_id":"1","triggered":True,"run_id":"r1","agent_session":"a"}
        with self.assertRaises(ValueError):score(cases,{"schema_version":1,"observations":[obs,obs]})
    def test_false_positive_counted(self):
        cases={"schema_version":1,"cases":[{"id":"1","should_trigger":False}]}
        got={"schema_version":1,"observations":[{"case_id":"1","triggered":True,"run_id":"r1","agent_session":"a"}]}
        self.assertEqual(score(cases,got)["confusion"]["fp"],1)
    def test_reused_run_id_rejected(self):
        cases={"schema_version":1,"cases":[{"id":"1","should_trigger":True},{"id":"2","should_trigger":False}]}
        observations={"schema_version":1,"observations":[{"case_id":"1","triggered":True,"run_id":"same","agent_session":"a"},{"case_id":"2","triggered":False,"run_id":"same","agent_session":"b"}]}
        with self.assertRaises(ValueError):score(cases,observations)
    def test_empty_manifest_not_complete(self):
        with self.assertRaises(ValueError):score({"schema_version":1,"cases":[]},{"schema_version":1,"observations":[]})
    def test_invalid_session_identifier_rejected(self):
        cases={"schema_version":1,"cases":[{"id":"1","should_trigger":True}]}
        obs={"schema_version":1,"observations":[{"case_id":"1","triggered":True,"run_id":"r1","agent_session":{"fake":True}}]}
        with self.assertRaises(ValueError):score(cases,obs)
    def test_duplicate_whitespace_run_id_rejected(self):
        cases={"schema_version":1,"cases":[{"id":"1","should_trigger":True},{"id":"2","should_trigger":False}]}
        obs={"schema_version":1,"observations":[{"case_id":"1","triggered":True,"run_id":" r1","agent_session":"a"},{"case_id":"2","triggered":False,"run_id":"r1 ","agent_session":"b"}]}
        with self.assertRaises(ValueError):score(cases,obs)
    def test_non_object_rejected(self):
        with self.assertRaises(ValueError):score([],[])
if __name__=="__main__":unittest.main()
