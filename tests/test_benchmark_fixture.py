import unittest,tempfile,pathlib
from benchmark_fixture import self_check,build,load_service,verify_one
class BenchmarkFixtureTests(unittest.TestCase):
    def test_buggy_and_corrected_oracles(self):
        r=self_check()
        self.assertTrue(r["fixture_validation_passed"])
        self.assertEqual(len(r["buggy_detected_defects"]),6)
        self.assertEqual(r["buggy_clean_controls_failed"],[])
        self.assertEqual(r["corrected_failed_checks"],[])
        self.assertFalse(r["agent_run_executed"])
    def test_grader_not_in_agent_folder(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t)
            data=build(root/"agent",root/"grader")
            self.assertTrue((root/"agent/service.py").exists())
            self.assertFalse((root/"agent/grading_manifest.json").exists())
            self.assertFalse((root/"agent/service_fixed.py").exists())
            self.assertTrue((root/"grader/grading_manifest.json").exists())
    def test_refuse_overwriting_existing_dir(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);(root/"agent").mkdir()
            with self.assertRaises(ValueError):build(root/"agent",root/"grader")
    def test_agent_target_contains_no_reference_fix_branch(self):
        from benchmark_fixture import TARGET_SOURCE,make_buggy_target
        generated=make_buggy_target(TARGET_SOURCE)
        self.assertNotIn("ON CONFLICT",generated)
        self.assertNotIn("CURRENT_MODE ==",generated)
        self.assertIn("if mode != 'buggy'",generated)
        compile(generated,"synthetic-agent-target.py","exec")
    def test_clean_control_includes_owner_access(self):
        from benchmark_fixture import CLEAN_CASES
        self.assertIn("C06",[x[0] for x in CLEAN_CASES])
if __name__=="__main__":unittest.main()
