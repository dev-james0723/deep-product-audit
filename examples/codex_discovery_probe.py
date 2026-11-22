#!/usr/bin/env python3
"""Offline, model-free Codex skill discovery in a fresh isolated CODEX_HOME.

This optional example requires an installed Codex CLI. It never starts a model
turn, touches live skill directories or consumes paid API tokens.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import subprocess
import sys
from threading import Thread
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Write receipt to a new file")
    args = parser.parse_args()
    codex = shutil.which("codex")
    if not codex:
        print(json.dumps({"status": "blocked", "reason": "Codex CLI not installed"}))
        return 2
    with tempfile.TemporaryDirectory(prefix="dpa-codex-check-") as tmp_string:
        tmp = Path(tmp_string)
        home = tmp / "codex"
        destination = home / "skills" / "deep-product-audit"
        installation = subprocess.run(
            [sys.executable, "-B", str(SOURCE / "tools" / "install_skill.py"),
             "install", "--destination", str(destination)],
            capture_output=True, text=True, cwd=SOURCE, timeout=20
        )
        if installation.returncode:
            raise RuntimeError("Isolated installer refused new destination")
        workspace = tmp / "workspace"
        workspace.mkdir()
        allowed = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG")
        env = {key: os.environ[key] for key in allowed if key in os.environ}
        env.update({
            "HOME": str(tmp), "CODEX_HOME": str(home),
            "XDG_DATA_HOME": str(tmp / "xdg-data"),
            "XDG_CONFIG_HOME": str(tmp / "xdg-config"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "CODEX_DISABLE_NETWORK": "1",
        })
        proc = subprocess.Popen(
            [codex, "app-server", "--stdio"], cwd=workspace,
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1
        )
        messages: Queue = Queue()

        def read_lines():
            for line in proc.stdout:
                try:
                    messages.put(json.loads(line))
                except json.JSONDecodeError:
                    messages.put({"malformed_reply": True})

        thread = Thread(target=read_lines, daemon=True)
        thread.start()

        def send(payload):
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()

        def receive(request_id, timeout=12):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    item = messages.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
                except Empty:
                    if proc.poll() is not None:
                        raise RuntimeError("App server terminated before reply")
                    continue
                if item.get("id") == request_id:
                    if item.get("error"):
                        raise RuntimeError("App server returned a protocol error")
                    return item["result"]
            raise TimeoutError("No Codex app-server reply in time")

        try:
            send({"id": 1, "method": "initialize",
                  "params": {"clientInfo": {"name": "dpa-portability-probe", "version": "1.0"},
                             "capabilities": {}}})
            receive(1)
            send({"method": "initialized", "params": {}})
            cwd = str(workspace)
            send({"id": 2, "method": "skills/list", "params": {
                "cwds": [cwd], "forceReload": True,
                "perCwdExtraUserRoots": [{"cwd": cwd, "extraUserRoots": [str(home / "skills")]}],
            }})
            groups = receive(2)["data"]
            matches = [
                skill for group in groups for skill in group.get("skills", [])
                if skill.get("name") == "deep-product-audit"
                and Path(skill.get("path", "")).resolve() == (destination / "SKILL.md").resolve()
            ]
            errors = [error for group in groups for error in group.get("errors", [])]
            if errors or len(matches) != 1 or not matches[0].get("enabled", True):
                raise AssertionError("Isolated Codex discovery not uniquely enabled or returned errors")
            receipt = {
                "status": "passed",
                "host": "Codex app-server skills/list",
                "matched_skill": "deep-product-audit",
                "matched_count": len(matches),
                "enabled": True,
                "installed_version": (SOURCE / "VERSION").read_text().strip(),
                "path": "[isolated CODEX_HOME]/skills/deep-product-audit/SKILL.md",
                "model_turn_started": False,
                "real_existing_host_modified": False,
                "api_credentials_read": False,
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            thread.join(timeout=2)
        if args.out:
            with args.out.open("x", encoding="utf-8") as output:
                output.write(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
