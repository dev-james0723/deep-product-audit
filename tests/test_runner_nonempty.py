import pathlib
import subprocess
import sys
import unittest


class RunnerContractTests(unittest.TestCase):
    def test_no_tests_is_not_success(self):
        runner = pathlib.Path(__file__).resolve().parents[1] / "tools/run_tests.py"
        result = subprocess.run([sys.executable, "-B", str(runner), "no_such_tests_*.py"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("No tests discovered", result.stderr)


if __name__ == "__main__":
    unittest.main()
