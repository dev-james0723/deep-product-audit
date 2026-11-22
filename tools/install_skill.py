#!/usr/bin/env python3
"""Explicit destination install, verify and conservative uninstall; no dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from package_skill import MAX_FILE_BYTES, RECEIPT, ROOT, read_regular, receipt_bytes, runtime_snapshot, safe_relative


def verify(destination: Path) -> dict:
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Installation must be a regular directory, not a symlink")
    root = destination.resolve()
    metadata = json.loads(read_regular(root, RECEIPT))
    if metadata.get("schema_version") != 1 or metadata.get("name") != "deep-product-audit" or metadata.get("kind") != "runtime_allowlist":
        raise ValueError("Not a recognized installation")
    hashes = metadata.get("files")
    if not isinstance(hashes, dict) or not hashes or len(hashes) > 200:
        raise ValueError("Invalid installation receipt")
    expected_directories = set()
    for name in hashes:
        safe_relative(name)
        expected_directories.update(p.as_posix() for p in Path(name).parents if p != Path("."))
    actual, actual_directories = set(), set()
    for p in root.rglob("*"):
        if p.is_symlink():
            raise ValueError("Installation contains a symlink")
        if p.is_file():
            actual.add(p.relative_to(root).as_posix())
        elif p.is_dir():
            actual_directories.add(p.relative_to(root).as_posix())
        else:
            raise ValueError("Installation contains a special file")
    if actual != set(hashes) | {RECEIPT}:
        raise ValueError("Unexpected or missing files; preserve the installation for inspection")
    if actual_directories != expected_directories:
        raise ValueError("Unexpected or missing directories; preserve user-owned folders")
    for name, digest in hashes.items():
        safe_relative(name)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid recorded file digest")
        if hashlib.sha256(read_regular(root, name)).hexdigest() != digest:
            raise ValueError("Modified installation; preserve local changes")
    if not {"SKILL.md", "VERSION", "LICENSE", "NOTICE.md"}.issubset(hashes):
        raise ValueError("Missing required installed files")
    if read_regular(root, "VERSION").decode("utf-8").strip() != metadata.get("version"):
        raise ValueError("Installed version mismatch")
    return {"verified": True, "version": metadata["version"], "files": len(hashes)}


def install(destination: Path, source: Path = ROOT) -> dict:
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination exists; select a fresh versioned directory")
    metadata, files = runtime_snapshot(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()  # Exclusive directory creation; never merge with existing user files.
    for name, data in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as out:
            out.write(data)
    # Write marker only after all data is present. Interrupted copies are not verified installs.
    with (destination / RECEIPT).open("xb") as out:
        out.write(receipt_bytes(metadata))
    return verify(destination)


def uninstall(destination: Path) -> dict:
    result = verify(destination)
    # Refuse accidental source-tree deletion even if a receipt was copied into it.
    root = destination.resolve()
    if root == ROOT or root in ROOT.parents:
        raise ValueError("Refusing to uninstall the source repository or its parent")
    shutil.rmtree(destination)
    return {"uninstalled": True, **result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "verify", "uninstall"))
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        operation = {"install": install, "verify": verify, "uninstall": uninstall}[args.action]
        print(json.dumps(operation(args.destination), indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
