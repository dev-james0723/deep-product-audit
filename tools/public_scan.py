#!/usr/bin/env python3
"""Bounded secret/privacy/history screening; findings contain no matched values."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys

MAX_BYTES = 4 * 1024 * 1024
MAX_OBJECTS = 10000
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b"),
    "aws-access-id": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "credential-assignment": re.compile(r'''(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\s*[:=]\s*["']([A-Za-z0-9_/+=-]{24,})["']'''),
    "url-credential": re.compile(r"https?://[^\s/:@]+:[^\s/@]+@"),
    "personal-home-path": re.compile(r"(?:/Users/|/home/)[A-Za-z0-9][A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[A-Za-z0-9][A-Za-z0-9._-]+\\"),
}
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
FORBIDDEN_FILES = {"evaluation-cases.json", "grading_manifest.json", ".env", "id_rsa", "id_ed25519"}
FORBIDDEN_DIRECTORIES = {"heldout", "holdout", "private-evidence", "graders"}


def forbidden_path(name: str) -> bool:
    path = Path(name)
    return path.name in FORBIDDEN_FILES or bool(FORBIDDEN_DIRECTORIES.intersection(path.parts))


def content_findings(data: bytes, label: str, deny_terms=()) -> list[dict]:
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [{"path": label, "rule": "opaque-binary-requires-review", "sha256": digest}]
    findings = []
    for rule, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append({"path": label, "rule": rule, "line": text.count("\n", 0, match.start()) + 1, "sha256": digest})
    for match in EMAIL.finditer(text):
        domain = match.group(1).lower()
        if domain.endswith((".invalid", ".test", ".example")) or domain in ("example.com", "example.org", "example.net"):
            continue
        findings.append({"path": label, "rule": "email-requires-review", "line": text.count("\n", 0, match.start()) + 1, "sha256": digest})
    for term in deny_terms:
        if term and term.casefold() in text.casefold():
            findings.append({"path": label, "rule": "private-term", "term_sha256": hashlib.sha256(term.encode()).hexdigest(), "sha256": digest})
    return findings


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError("Git history inspection failed; no history pass recorded")
    return result.stdout


def scan(root: Path, history: bool = False, deny_terms=()) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("Source root must exist")
    findings, files, objects = [], {}, 0
    # Scan every proposed nonignored file, including untracked candidate files.
    if (root / ".git").exists():
        names = sorted(set(git(root, "ls-files", "-c", "-o", "--exclude-standard", "-z").decode().split("\0")) - {""})
    else:
        names = [p.relative_to(root).as_posix() for p in root.rglob("*")
                 if not {".git", "__pycache__", ".venv", "dist"}.intersection(p.relative_to(root).parts) and (p.is_file() or p.is_symlink())]
    for name in names:
        path = root / name
        if path.is_symlink():
            findings.append({"path": name, "rule": "symlink-requires-review"})
            continue
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            findings.append({"path": name, "rule": "oversize-or-special-file-not-scanned"})
            continue
        if forbidden_path(name):
            findings.append({"path": name, "rule": "private-or-grader-file"})
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            findings.append({"path": name, "rule": "changed-size-not-scanned"})
            continue
        files[name] = hashlib.sha256(data).hexdigest()
        findings.extend(content_findings(data, name, deny_terms))
    history_state = "not_tested"
    if history:
        entries = git(root, "rev-list", "--objects", "--all").decode().splitlines()
        if not entries:
            raise ValueError("History has no commits; cannot claim a history scan")
        if len(entries) > MAX_OBJECTS:
            raise ValueError("History exceeds bounded scan limit; obtain separate full-history review")
        # rev-list --objects supplies one representative name per object, so it
        # cannot reveal every alias (for example identical README and .env bytes).
        # Inspect each reachable commit tree before de-duplicating blob contents.
        seen_paths = set()
        for commit in git(root, "rev-list", "--all").decode().splitlines():
            tree = git(root, "ls-tree", "-r", "-z", "--full-tree", commit)
            for row in tree.split(b"\0"):
                if not row:
                    continue
                meta, name_bytes = row.split(b"\t", 1)
                mode, kind, object_id = meta.decode().split()
                name = name_bytes.decode("utf-8")
                identity = (object_id, name, mode, kind)
                if identity in seen_paths:
                    continue
                seen_paths.add(identity)
                if len(seen_paths) > MAX_OBJECTS:
                    raise ValueError("Historical path aliases exceed bounded scan limit")
                label = "history:" + commit + ":" + name
                if forbidden_path(name):
                    findings.append({"path": label, "rule": "historical-private-or-grader-file"})
                if mode == "120000" or kind == "commit":
                    findings.append({"path": label, "rule": "historical-symlink-or-submodule-requires-review"})
        for entry in entries:
            sha, _, name = entry.partition(" ")
            kind = git(root, "cat-file", "-t", sha).decode().strip()
            if kind not in ("blob", "commit", "tag"):
                continue
            size = int(git(root, "cat-file", "-s", sha))
            label = "history:" + sha + (":" + name if name else "")
            if size > MAX_BYTES:
                findings.append({"path": label, "rule": "history-object-too-large-not-scanned"})
                continue
            data = git(root, "cat-file", "-p", sha)
            objects += 1
            if name and forbidden_path(name):
                findings.append({"path": label, "rule": "historical-private-or-grader-file"})
            findings.extend(content_findings(data, label, deny_terms))
        history_state = "scanned"
    return {"schema_version": 1, "status": "failed" if findings else "passed", "files_scanned": len(files),
            "history": history_state, "history_objects_scanned": objects, "findings": findings, "file_sha256": files,
            "limits": ["Heuristic screening is not proof of secret absence or copyright ownership.",
                       "Only proposed nonignored files and reachable Git objects are scanned; excluded private repositories are never exported.",
                       "Public demonstration sources are known examples, not held-out tasks; inspect package allowlist separately.",
                       "Manual provenance, privacy and licensing review remains required."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--deny-term", action="append", default=[])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        report = scan(args.root, args.history, args.deny_term)
        rendered = json.dumps(report, indent=2) + "\n"
        if args.out:
            with args.out.open("x", encoding="utf-8") as out:
                out.write(rendered)
        else:
            print(rendered, end="")
        return 0 if report["status"] == "passed" else 1
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
