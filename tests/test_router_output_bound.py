"""An authorized guard still must not consume unbounded parent output memory."""
import sys
import tracemalloc
import unittest

from impact_router import run


class RouterOutputBoundTests(unittest.TestCase):
    def test_large_child_output_is_rejected_with_bounded_parent_memory(self):
        tracemalloc.start()
        try:
            code, out, error = run([sys.executable, "-c", "import sys;sys.stdout.write('x'*(16*1024*1024))"], timeout=5)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertNotEqual(code, 0, "Output beyond the guard budget must not be accepted")
        self.assertLess(peak, 4 * 1024 * 1024, "Parent must not buffer the complete child output")
        self.assertIn("output_limit", error)

    def test_stderr_flood_is_also_bounded(self):
        code, out, error = run([sys.executable, "-c", "import sys;sys.stderr.write('x'*(4*1024*1024))"], timeout=5)
        self.assertNotEqual(code, 0)
        self.assertIn("output_limit", error)

    def test_timeout_is_not_a_success(self):
        code, _, error = run([sys.executable, "-c", "import time;time.sleep(5)"], timeout=0.05)
        self.assertNotEqual(code, 0)
        self.assertEqual(error, "TimeoutExpired")


if __name__ == "__main__":
    unittest.main()
