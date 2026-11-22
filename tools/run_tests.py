#!/usr/bin/env python3
"""Run the local standard-library test suite without package installation."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))
sys.dont_write_bytecode = True

if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else "test_*.py"
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern)
    if suite.countTestCases() == 0:
        print("No tests discovered; refusing an empty successful run", file=sys.stderr)
        raise SystemExit(2)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
