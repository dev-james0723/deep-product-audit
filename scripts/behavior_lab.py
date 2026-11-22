#!/usr/bin/env python3
"""Public, known-answer behavioral demonstration; never a hidden benchmark.

Python 3.10+ standard library only. Owns disposable loopback HTTP, SQLite and
file fixtures. No remote target, account, package installation, or paid API.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import inspect
import json
import os
from pathlib import Path
import platform
import queue
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import contextmanager, closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

VERSION = "1.0.0"
TIMEOUT = 5.0
CASE_IDS = ("batch", "privacy", "atomic-file", "stream", "required-jobs")


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def parse_private(raw):
    """This fixture contract accepts only explicit true/false, case-insensitive."""
    if not isinstance(raw, str) or raw.lower() not in ("true", "false"):
        raise ValueError("explicit true or false required")
    return raw.lower() == "true"


def fixture_database_sql():
    """Frozen initial records, separate from either implementation policy."""
    return ("CREATE TABLE documents(id INTEGER PRIMARY KEY, locked INTEGER, value TEXT);"
            "INSERT INTO documents VALUES(1,0,'old'),(2,1,'old');"
            "CREATE TABLE subscriptions(principal TEXT, scope TEXT);")


def fixture_stream_bytes(truncated=False):
    """Frozen complete transport input, separate from completion classification."""
    full = b'{"delta":"hello"}\n{"done":true}\n'
    return full[:18] if truncated else full


class Application:
    def __init__(self, mode, database):
        if mode not in ("buggy", "fixed"):
            raise ValueError("mode must be buggy or fixed")
        self.mode = mode
        self.database = Path(database)
        self.lock = threading.Lock()
        with closing(sqlite3.connect(str(self.database))) as db, db:
            db.executescript(fixture_database_sql())

    def handler(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def setup(self):
                super().setup()
                self.connection.settimeout(TIMEOUT)

            def log_message(self, *_):
                pass

            def reply(self, code, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != "/batch":
                    return self.reply(404, {"error": "unknown_route"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 4096:
                        raise ValueError("invalid_size")
                    body = json.loads(self.rfile.read(size))
                    ids = body["ids"]
                    if (not isinstance(ids, list) or not 1 <= len(ids) <= 10
                            or any(type(i) is not int for i in ids)
                            or len(set(ids)) != len(ids)):
                        raise ValueError("invalid_ids")
                except (ValueError, TypeError, KeyError):
                    return self.reply(400, {"error": "invalid_body"})
                items = []
                with app.lock, closing(sqlite3.connect(str(app.database))) as db, db:
                    for item_id in ids:
                        row = db.execute("SELECT locked FROM documents WHERE id=?", (item_id,)).fetchone()
                        if row is None or row[0]:
                            items.append({"id": item_id, "ok": False, "error": "locked_or_missing"})
                        else:
                            db.execute("UPDATE documents SET value='new' WHERE id=?", (item_id,))
                            items.append({"id": item_id, "ok": True})
                all_succeeded = True if app.mode == "buggy" else all(i["ok"] for i in items)
                # An HTTP 200 can carry partial per-item failures. The aggregate
                # must reflect them instead of presenting a false completion.
                return self.reply(200, {"all_succeeded": all_succeeded, "items": items})

            def do_GET(self):
                request = urlsplit(self.path)
                query = parse_qs(request.query, keep_blank_values=True)
                if request.path == "/subscribe":
                    values = query.get("private", [])
                    raw = values[0] if len(values) == 1 else None
                    if app.mode == "buggy":
                        private = raw == "true"
                    else:
                        try:
                            private = parse_private(raw)
                        except ValueError:
                            return self.reply(400, {"error": "invalid_privacy_mode"})
                    principal = self.headers.get("X-Fixture-Principal", "")
                    if private and principal != "owner":
                        return self.reply(403, {"error": "forbidden"})
                    with app.lock, closing(sqlite3.connect(str(app.database))) as db, db:
                        db.execute("INSERT INTO subscriptions VALUES(?,?)", (principal, "private" if private else "public"))
                    return self.reply(200, {"subscribed": True})
                if request.path == "/stream":
                    full = fixture_stream_bytes()
                    actual = fixture_stream_bytes(truncated=query.get("truncate") == ["1"])
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.send_header("Content-Length", str(len(full)))
                    self.end_headers()
                    self.wfile.write(actual)
                    self.wfile.flush()
                    self.close_connection = True
                    return
                return self.reply(404, {"error": "unknown_route"})

        return Handler


@contextmanager
def serve(mode, database):
    app = Application(mode, database)
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.handler())
    server.daemon_threads = False
    server.block_on_close = True
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    worker.start()
    try:
        yield server.server_address[1], app
    finally:
        server.shutdown()
        server.server_close()
        worker.join(TIMEOUT)
        if worker.is_alive():
            raise RuntimeError("owned HTTP server thread did not stop")


def request(port, path, body=None, principal="guest"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT)
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    try:
        connection.request("GET" if body is None else "POST", path, body=encoded,
                           headers={"Content-Type": "application/json", "X-Fixture-Principal": principal})
        response = connection.getresponse()
        declared = int(response.getheader("Content-Length", "0"))
        truncated = False
        try:
            data = response.read()
        except http.client.IncompleteRead as error:
            data = error.partial
            truncated = True
        return {"status_code": response.status, "declared_bytes": declared,
                "received_bytes": len(data), "truncated": truncated,
                "body": data.decode("utf-8")}
    finally:
        connection.close()


def consume_stream(mode, receipt):
    """Deliberately buggy and corrected UI completion policies for the demo."""
    if mode not in ("buggy", "fixed"):
        raise ValueError("invalid mode")
    if mode == "buggy":
        return "completed" if receipt["body"] else "failed"
    if receipt.get("status_code") != 200:
        return "failed"
    if receipt["truncated"] or receipt["received_bytes"] != receipt["declared_bytes"]:
        return "incomplete"
    try:
        events = [json.loads(line) for line in receipt["body"].splitlines()]
    except ValueError:
        return "failed"
    terminal = events[-1] if events else None
    return ("completed" if isinstance(terminal, dict) and set(terminal) == {"done"}
            and terminal["done"] is True else "incomplete")


def release_gate(mode, contract):
    """Offline CI-record policy demonstration, not a CI or deployment runner."""
    if mode not in ("buggy", "fixed"):
        raise ValueError("invalid mode")
    if not isinstance(contract, dict):
        return False
    if mode == "buggy":
        return contract.get("overall") == "success"
    required, jobs, commit = (contract.get(k) for k in ("required", "jobs", "commit"))
    if (not isinstance(required, list) or not required
            or any(not isinstance(name, str) or not name for name in required)
            or len(set(required)) != len(required)
            or not isinstance(jobs, list) or not isinstance(commit, str) or not commit):
        return False
    seen = {}
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("id"), str) or job["id"] in seen:
            return False
        seen[job["id"]] = job
    return contract.get("overall") == "success" and all(
        name in seen and seen[name].get("status") == "passed"
        and seen[name].get("commit") == commit for name in required)


def atomic_write(mode, path, payload, staged=None, predecessor=None):
    """Publish a complete JSON snapshot; schedule hooks are fixture-only."""
    if mode not in ("buggy", "fixed"):
        raise ValueError("invalid mode")
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    temporary = None
    try:
        if mode == "buggy":
            stream = open(path, "wb")
        else:
            fd, name = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=path.parent)
            temporary = Path(name)
            stream = os.fdopen(fd, "wb")
        with stream:
            if staged is not None:
                staged.set()
            if predecessor is not None and not predecessor.wait(TIMEOUT):
                raise TimeoutError("owned writer predecessor did not complete")
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary is not None:
            os.replace(temporary, path)
            temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def concurrent_snapshot(mode, directory):
    """Force a two-writer interleaving with events, never a timing/sleep race."""
    path = directory / "config.json"
    initial = {"theme": "old"}
    first = {"theme": "new"}
    second = {"theme": "another-valid-theme-with-a-longer-value"}
    path.write_text(json.dumps(initial), encoding="utf-8")
    staged, predecessor = threading.Event(), threading.Event()
    errors = queue.Queue()

    def first_writer():
        try:
            atomic_write(mode, path, first, staged, predecessor)
        except Exception as error:
            errors.put(type(error).__name__ + ": " + str(error))

    worker = threading.Thread(target=first_writer, daemon=True)
    worker.start()
    middle = None
    try:
        if not staged.wait(TIMEOUT):
            raise TimeoutError("owned first writer did not stage")
        atomic_write(mode, path, second)
        middle = json.loads(path.read_text(encoding="utf-8"))
    finally:
        predecessor.set()
        worker.join(TIMEOUT + 1)
    if worker.is_alive():
        raise RuntimeError("owned config writer did not stop")
    if not errors.empty():
        raise RuntimeError(errors.get_nowait())
    raw = path.read_text(encoding="utf-8")
    try:
        final = json.loads(raw)
        valid = True
    except ValueError:
        final, valid = None, False
    return {"middle": middle, "final": final, "valid_json": valid,
            "raw_final": raw, "expected_final": first,
            "remaining_temporaries": [p.name for p in directory.glob("*.tmp")]}


def evaluate_observation(kind, observation):
    """One unchanged requirement/oracle function for both buggy and fixed code."""
    if kind == "batch":
        requested, rows, response = (observation.get(key) for key in ("requested_ids", "rows", "response"))
        if (observation.get("status_code") != 200 or not isinstance(requested, list) or not requested
                or any(type(item_id) is not int for item_id in requested)
                or len(set(requested)) != len(requested)
                or not isinstance(rows, list) or not isinstance(response, dict)):
            return False
        persisted = {}
        for row in rows:
            if (not isinstance(row, dict) or type(row.get("id")) is not int
                    or row["id"] not in requested or row["id"] in persisted
                    or not isinstance(row.get("value"), str)):
                return False
            persisted[row["id"]] = row["value"]
        # A requested ID absent from independently queried state failed; it is
        # not silently dropped from the expected-outcome denominator.
        expected = {item_id: persisted.get(item_id) == "new" for item_id in requested}
        items = response.get("items")
        if not isinstance(items, list) or len(items) != len(requested):
            return False
        outcomes = {}
        for item in items:
            if (not isinstance(item, dict) or type(item.get("id")) is not int
                    or item["id"] not in expected or item["id"] in outcomes
                    or type(item.get("ok")) is not bool):
                return False
            outcomes[item["id"]] = item["ok"]
        return response.get("all_succeeded") is all(expected.values()) and outcomes == expected
    if kind == "privacy":
        if observation["principal"] == "owner":
            return observation["status_code"] == 200 and observation["rows"] == [["owner", "private"]]
        return observation["status_code"] in (400, 403) and observation["rows"] == []
    if kind == "atomic-file":
        return (observation["valid_json"] and observation["final"] == observation["expected_final"]
                and observation["remaining_temporaries"] == [])
    if kind == "stream":
        try:
            decoded = [json.loads(line) for line in observation["body"].splitlines()]
            last = decoded[-1] if decoded else None
            terminal_success = isinstance(last, dict) and len(last) == 1 and last.get("done") is True
        except ValueError:
            terminal_success = False
        wire_complete = (observation["status_code"] == 200 and not observation["truncated"]
                         and observation["received_bytes"] == observation["declared_bytes"]
                         and terminal_success)
        return (observation["application_state"] == "completed") is wire_complete
    if kind == "required-jobs":
        # Oracle is the frozen case requirement, separate from the gate under test.
        return observation["accepted"] is observation["expected_acceptance"]
    raise ValueError("unknown observation kind")


def checks_hash():
    # Bind actual fixture inputs, transport/oracle helpers, scheduling, and
    # case selection. Do not substitute the SUT's source/mode hash for this.
    helpers = (fixture_database_sql, fixture_stream_bytes, request, serve,
               concurrent_snapshot, evaluate_observation, observe, run_demo)
    frozen_checks = {"helpers": {helper.__name__: inspect.getsource(helper) for helper in helpers},
                     "case_ids": CASE_IDS, "timeout_seconds": TIMEOUT}
    return digest(frozen_checks)


def observe(mode, kind, control, directory):
    directory.mkdir()
    if kind in ("batch", "privacy", "stream"):
        with serve(mode, directory / "state.sqlite") as (port, app):
            if kind == "batch":
                ids = [1] if control else [1, 2]
                receipt = request(port, "/batch", {"ids": ids})
                with closing(sqlite3.connect(str(app.database))) as db, db:
                    rows = [{"id": row[0], "value": row[1]} for row in db.execute(
                        "SELECT id,value FROM documents WHERE id IN (" + ",".join("?" for _ in ids) + ") ORDER BY id", ids)]
                return {"requested_ids": ids, "rows": rows, "status_code": receipt["status_code"],
                        "response": json.loads(receipt["body"])}
            if kind == "privacy":
                principal, value = ("owner", "true") if control else ("guest", "True")
                receipt = request(port, "/subscribe?private=" + value, principal=principal)
                with closing(sqlite3.connect(str(app.database))) as db, db:
                    rows = [list(row) for row in db.execute("SELECT principal,scope FROM subscriptions")]
                return {"principal": principal, "input": value, "status_code": receipt["status_code"], "rows": rows}
            receipt = request(port, "/stream?truncate=" + ("0" if control else "1"))
            receipt["application_state"] = consume_stream(mode, receipt)
            return receipt
    if kind == "atomic-file":
        if not control:
            return concurrent_snapshot(mode, directory)
        path = directory / "config.json"
        expected = {"theme": "dark"}
        atomic_write(mode, path, expected)
        return {"valid_json": True, "final": json.loads(path.read_text(encoding="utf-8")),
                "expected_final": expected, "remaining_temporaries": [p.name for p in directory.glob("*.tmp")]}
    if kind == "required-jobs":
        contract = {"commit": "fixture-revision-1", "overall": "success", "required": ["unit", "integration"],
                    "jobs": [{"id": "unit", "status": "passed", "commit": "fixture-revision-1"},
                             {"id": "integration", "status": "passed" if control else "skipped", "commit": "fixture-revision-1"}]}
        return {"contract": contract, "accepted": release_gate(mode, contract), "expected_acceptance": control}
    raise ValueError("unknown case")


def run_demo():
    before = checks_hash()
    results = {}
    with tempfile.TemporaryDirectory(prefix="behavior-lab-") as temporary:
        root = Path(temporary)
        for mode in ("buggy", "fixed"):
            results[mode] = []
            for kind in CASE_IDS:
                for control in (False, True):
                    case_id = kind + ("-clean" if control else "-bug")
                    try:
                        observation = observe(mode, kind, control, root / (mode + "-" + case_id))
                        passed = evaluate_observation(kind, observation)
                        results[mode].append({"case_id": case_id, "kind": kind,
                            "classification": "clean_control" if control else "known_bug",
                            "status": "passed" if passed else "failed", "observation": observation,
                            "observation_sha256": digest(observation)})
                    except (OSError, ValueError, RuntimeError, TimeoutError, sqlite3.Error, http.client.HTTPException) as error:
                        results[mode].append({"case_id": case_id, "kind": kind,
                            "classification": "clean_control" if control else "known_bug",
                            "status": "blocked", "error": type(error).__name__ + ": " + str(error)})
    after = checks_hash()
    failures = [r["case_id"] for r in results["buggy"] if r["classification"] == "known_bug" and r["status"] == "failed"]
    clean_failures = [r["case_id"] for r in results["buggy"] if r["classification"] == "clean_control" and r["status"] != "passed"]
    fixed_failures = [r["case_id"] for r in results["fixed"] if r["status"] != "passed"]
    blocked = [mode + ":" + r["case_id"] for mode, cases in results.items() for r in cases if r["status"] == "blocked"]
    validated = len(failures) == len(CASE_IDS) and not clean_failures and not fixed_failures and not blocked and before == after
    return {"schema_version": 1, "demo_version": VERSION,
            "demonstration_kind": "public_known_answer_fixture", "status": "verified" if validated else "not_verified",
            "demo_validated": validated, "agent_evaluation_executed": False, "hidden_benchmark": False,
            "external_product_tested": False, "observed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "runtime": {"python": platform.python_version(), "platform": sys.platform, "implementation": platform.python_implementation()},
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "checks_sha256_before": before, "checks_sha256_after": after, "unchanged_checks": before == after,
            "known_bug_count": len(CASE_IDS), "clean_control_count": len(CASE_IDS), "per_mode_check_count": len(CASE_IDS) * 2,
            "reproduced_bug_ids": failures, "buggy_clean_control_failures": clean_failures,
            "fixed_failures": fixed_failures, "blocked": blocked, "not_tested": [], "results": results,
            "limits": ["Synthetic fixtures only; not an independent agent performance evaluation.",
                       "CI case checks offline records; no real CI jobs or deployment executed.",
                       "Atomic replace and fsync demonstration does not prove crash durability on every filesystem.",
                       "No browser, mobile device, external provider, real payment, or customer data exercised."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="new JSON result file; never overwrites existing evidence")
    args = parser.parse_args(argv)
    if args.out is not None and args.out.exists():
        parser.error("output already exists")
    result = run_demo()
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        with args.out.open("x", encoding="utf-8") as output:
            output.write(text)
    else:
        print(text, end="")
    return 0 if result["demo_validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
