#!/usr/bin/env python3
"""Build an allowlisted, deterministic runtime package without grader material."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "INSTALL-RECEIPT.json"
MAX_FILE_BYTES = 4 * 1024 * 1024
EXCLUDED_PARTS = {".git", "tests", "tools", "graders", "heldout", "holdout", "__pycache__"}
EXCLUDED_NAMES = {"evaluation-cases.json", "trigger-cases.json", "benchmark_fixture.py", "behavior_lab.py", "network_fault_lab.py"}


def safe_relative(name: str) -> str:
    if not isinstance(name, str) or not name or len(name) > 240 or "\\" in name:
        raise ValueError("Invalid package path")
    p = PurePosixPath(name)
    w = PureWindowsPath(name)
    if p.is_absolute() or w.drive or str(p) != name or any(x in (".", "..", "") for x in p.parts):
        raise ValueError("Package path must be a canonical relative path")
    if any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", x) or x.endswith((".", " ")) for x in p.parts):
        raise ValueError("Package path is not portable")
    return name


def read_regular(root: Path, name: str) -> bytes:
    name = safe_relative(name)
    path = root / name
    for part in (path, *path.parents):
        if part == root.parent:
            break
        if part.is_symlink():
            raise ValueError("Symlinks are not distributable")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
        raise ValueError("Package entry must be a bounded regular file")
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Package entry exceeds size limit")
    return data


def runtime_snapshot(root: Path = ROOT) -> tuple[dict, dict[str, bytes]]:
    root = root.resolve()
    spec = json.loads(read_regular(root, "package-manifest.json"))
    if spec.get("schema_version") != 1 or spec.get("name") != "deep-product-audit":
        raise ValueError("Unsupported package specification")
    version = spec.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.]+)?", version):
        raise ValueError("Invalid package version")
    if read_regular(root, "VERSION").decode("utf-8").strip() != version:
        raise ValueError("Version file and package specification disagree")
    names = spec.get("runtime_files")
    if not isinstance(names, list) or not names or len(names) > 200 or any(not isinstance(x, str) for x in names) or len(set(names)) != len(names):
        raise ValueError("Runtime allowlist must contain unique paths")
    files = {}
    for name in sorted(names):
        safe_relative(name)
        parts = PurePosixPath(name).parts
        if set(parts) & EXCLUDED_PARTS or parts[-1] in EXCLUDED_NAMES or parts[-1].startswith("test_") or name == RECEIPT:
            raise ValueError("Test or grader material cannot enter the runtime package")
        files[name] = read_regular(root, name)
    if not {"SKILL.md", "VERSION", "LICENSE", "NOTICE.md"}.issubset(files):
        raise ValueError("Missing mandatory runtime documentation")
    metadata = {"schema_version": 1, "name": "deep-product-audit", "version": version,
                "kind": "runtime_allowlist", "files": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()},
                "grader_material_included": False}
    return metadata, files


def receipt_bytes(metadata: dict) -> bytes:
    return (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("utf-8")


def build(output: Path, root: Path = ROOT) -> dict:
    metadata, files = runtime_snapshot(root)
    files[RECEIPT] = receipt_bytes(metadata)
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new file")
    # Snapshot all inputs before opening output; no source change can split a build.
    with output.open("xb") as raw:
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo("deep-product-audit/" + name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, data)
    return {"version": metadata["version"], "runtime_files": len(metadata["files"]),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "contains_grading_answers": False, "publication_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.out), indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
