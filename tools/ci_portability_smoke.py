#!/usr/bin/env python3
"""Portable, bounded, disposable smoke. No production endpoints or paid providers."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TOOLS = ROOT / "tools"
TIMEOUT_SECONDS = 90


def run(script: Path, *args: str, expect: int = 0) -> str:
    command = [sys.executable, "-B", str(script), *map(str, args)]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"{script.name} expected exit {expect}, got {result.returncode}\n"
            f"stdout tail: {result.stdout[-1200:]}\nstderr tail: {result.stderr[-1200:]}"
        )
    return result.stdout


def ensure(path: Path, *, minimum_bytes: int = 4) -> dict:
    content = path.read_bytes()
    assert len(content) >= minimum_bytes, path
    return json.loads(content)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dpa qa spaces ") as root_dir:
        work = Path(root_dir)
        legacy = work / "legacy demo.json"
        behavior = work / "behavior demo.json"
        network = work / "network demo.json"
        archive = work / "portable runtime.zip"
        destination = work / "installed skill folder"

        run(SCRIPTS / "benchmark_fixture.py", "--self-test", "--out", legacy)
        run(SCRIPTS / "behavior_lab.py", "--out", behavior)
        run(SCRIPTS / "network_fault_lab.py", "--mode", "compare", "--out", network)
        for path in (legacy, behavior, network):
            ensure(path, minimum_bytes=100)

        run(TOOLS / "package_skill.py", "--out", archive)
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            assert all(n.startswith("deep-product-audit/") for n in names)
            assert "deep-product-audit/INSTALL-RECEIPT.json" in names
            assert not any(n.startswith("deep-product-audit/tests/") for n in names)
            assert not any(n.startswith("deep-product-audit/docs/") for n in names)

        assert ensure_json_stdout(
            run(TOOLS / "install_skill.py", "install", "--destination", destination),
            "version", "4.0.0-rc.1"
        )
        run(destination / "scripts" / "regression_evidence.py", "--help")
        assert ensure_json_stdout(
            run(TOOLS / "install_skill.py", "verify", "--destination", destination),
            "verified", True
        )
        # Negative control: foreign file must prevent removal, preserving user data.
        foreign = destination / "do-not-remove.txt"
        foreign.write_text("owned by caller", encoding="utf-8")
        run(TOOLS / "install_skill.py", "uninstall", "--destination", destination, expect=2)
        assert foreign.read_text(encoding="utf-8") == "owned by caller"
        foreign.unlink()
        assert ensure_json_stdout(
            run(TOOLS / "install_skill.py", "uninstall", "--destination", destination),
            "uninstalled", True
        )
        assert not destination.exists()

        # Full history review stays out of runtime package. A fixed legacy
        # synthetic URL credential must be surfaced, NOT silently suppressed.
        output = work / "history scan.json"
        run(TOOLS / "public_scan.py", "--history", "--out", output, expect=1)
        scan = ensure(output)
        assert scan["history"] == "scanned" and scan["status"] == "failed"
        assert scan["findings"] and all(
            f["rule"] == "url-credential" and
            ("tests/test_audit_ledger.py" in f["path"])
            for f in scan["findings"]
        ), scan["findings"]
        print(json.dumps({
            "result": "passed",
            "platform": platform.system(),
            "python": platform.python_version(),
            "known_bug_labs": 3,
            "normal_and_negative_controls": "passed",
            "runtime_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "public_history_reviewable_fixture_findings": len(scan["findings"]),
            "installer_uninstall_verify": "passed",
        }, sort_keys=True))
    return 0


def ensure_json_stdout(output: str, key: str, expected: object) -> bool:
    parsed = json.loads(output)
    assert parsed[key] == expected, parsed
    return True


if __name__ == "__main__":
    raise SystemExit(main())
