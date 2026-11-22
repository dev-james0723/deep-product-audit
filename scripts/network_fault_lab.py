#!/usr/bin/env python3
"""Bounded, loopback-only network fixtures; never a live-product acceptance test."""
from __future__ import annotations

import argparse
import http.client
import json
import signal
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

VERSION = "1.0"
LOOPBACK = "127.0.0.1"
REQUEST_TIMEOUT = 0.5
TIMEOUT_FAULT_DELAY = 0.35
TIMEOUT_CLIENT_WAIT = 0.10
MAX_DEADLINE_SECONDS = 15.0
LAB_SCENARIOS = ("NET-001", "NET-004", "NET-005", "NET-009", "NET-017")
SEEDED_DEFECT_SCENARIOS = frozenset(("NET-004", "NET-005", "NET-017"))


class DeadlineExceeded(Exception):
    pass


class PayloadConflict(Exception):
    pass


class Deadline:
    def __init__(self, seconds: float):
        if not 0 < seconds <= MAX_DEADLINE_SECONDS:
            raise ValueError("deadline must be greater than 0 and at most 15 seconds")
        self.end = time.monotonic() + seconds

    def remaining(self, limit: float = REQUEST_TIMEOUT) -> float:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise DeadlineExceeded("fixture deadline exhausted")
        return min(limit, remaining)


class Store:
    """An atomic durable operation record and a separately queryable effects table."""

    def __init__(self, path: Path):
        self.path = path
        with self.connect() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS operations (op_id TEXT PRIMARY KEY, amount INTEGER NOT NULL);"
                "CREATE TABLE IF NOT EXISTS effects (seq INTEGER PRIMARY KEY, op_id TEXT NOT NULL, amount INTEGER NOT NULL);"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.path), timeout=REQUEST_TIMEOUT)
        try:
            with db:
                yield db
        finally:
            db.close()

    def apply(self, op_id: str, amount: int, mode: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT amount FROM operations WHERE op_id=?", (op_id,)).fetchone()
            if mode == "corrected" and existing:
                if existing[0] != amount:
                    raise PayloadConflict("same operation identity has a different payload")
                return {"operation_id": op_id, "replayed": True}
            db.execute("INSERT INTO effects(op_id, amount) VALUES (?, ?)", (op_id, amount))
            db.execute("INSERT OR REPLACE INTO operations(op_id, amount) VALUES (?, ?)", (op_id, amount))
            return {"operation_id": op_id, "replayed": False}

    def effect_count(self, op_id: str) -> int:
        # Independent oracle: inspect committed effects, never infer success from HTTP.
        with self.connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM effects WHERE op_id=?", (op_id,)).fetchone()[0])


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False

    def __init__(self, store: Store, mode: str):
        self.store = store
        self.mode = mode
        self.stopping = threading.Event()
        self.limited: set[str] = set()
        self.attempts: dict[str, int] = {}
        self.state_lock = threading.Lock()
        super().__init__((LOOPBACK, 0), Handler)


class Handler(BaseHTTPRequestHandler):
    server: FixtureServer
    protocol_version = "HTTP/1.0"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT)

    def log_message(self, _format: str, *args: Any) -> None:
        pass

    def send_json(self, status: int, value: dict[str, Any], *, retry_after: str | None = None) -> None:
        payload = json.dumps(value).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if retry_after is not None:
                self.send_header("Retry-After", retry_after)
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Expected when the deliberate timeout has already closed the client.
            self.close_connection = True

    def do_POST(self) -> None:
        if self.path != "/operate":
            self.send_json(404, {"error": "fixture_endpoint_only"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("bounded body required")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("object required")
            op_id, amount = body.get("operation_id"), body.get("amount")
            if not isinstance(op_id, str) or not 1 <= len(op_id) <= 100 or type(amount) is not int:
                raise ValueError("invalid fixture payload")
            fault = self.headers.get("X-Fixture-Fault", "none")
            if fault not in {"none", "drop_reply", "delay_reply", "rate_limit_once"}:
                raise ValueError("unknown fixture fault")
        except (ValueError, TypeError, OSError):
            self.send_json(400, {"error": "invalid_fixture_request"})
            return
        with self.server.state_lock:
            self.server.attempts[op_id] = self.server.attempts.get(op_id, 0) + 1
            limited = fault == "rate_limit_once" and op_id not in self.server.limited
            if limited:
                self.server.limited.add(op_id)
        if limited:
            self.send_json(429, {"error": "fixture_rate_limit"}, retry_after="0")
            return
        try:
            outcome = self.server.store.apply(op_id, amount, self.server.mode)
        except PayloadConflict:
            self.send_json(409, {"error": "operation_payload_conflict"})
            return
        except sqlite3.Error:
            self.send_json(500, {"error": "fixture_database_error"})
            return
        if fault == "drop_reply":
            # The transaction above has committed before the response is lost.
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return
        if fault == "delay_reply":
            self.server.stopping.wait(TIMEOUT_FAULT_DELAY)
        self.send_json(200, outcome)


class Fixture:
    def __init__(self, store: Store, mode: str, owned: list["Fixture"]):
        if mode not in {"buggy", "corrected"}:
            raise ValueError("unknown fixture mode")
        self.server = FixtureServer(store, mode)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            name=f"audit-network-fixture-{self.port}",
        )
        self.closed = False
        owned.append(self)

    def __enter__(self) -> "Fixture":
        try:
            self.thread.start()
        except BaseException:
            self.server.server_close()
            self.closed = True
            raise
        return self

    def __exit__(self, _kind: Any, _error: Any, _tb: Any) -> None:
        self.server.stopping.set()
        try:
            self.server.shutdown()
        finally:
            self.server.server_close()
            self.thread.join(timeout=1.0)
            self.closed = not self.thread.is_alive() and self.server.socket.fileno() == -1
        if not self.closed:
            raise RuntimeError("owned fixture did not close")


def request(port: int, deadline: Deadline, operation: str, *, fault: str = "none", amount: int = 1,
            timeout: float = REQUEST_TIMEOUT) -> dict[str, Any]:
    """Internal fixture helper. Host is hardcoded; the CLI exposes no target option."""
    conn = http.client.HTTPConnection(LOOPBACK, port, timeout=deadline.remaining(timeout))
    payload = json.dumps({"operation_id": operation, "amount": amount})
    phase = "connect"
    connected = False
    write_attempted = False
    try:
        # Separate connect from request writing: errno text varies across operating systems,
        # while an unattempted HTTP write gives the offline fixture a portable boundary.
        conn.connect()
        connected = True
        phase = "write_request"
        write_attempted = True
        conn.request("POST", "/operate", body=payload, headers={
            "Content-Type": "application/json", "X-Fixture-Fault": fault,
        })
        phase = "read_response"
        response = conn.getresponse()
        body = response.read(4096)
        return {"status": response.status, "body": json.loads(body),
                "retry_after": response.getheader("Retry-After"), "transport_error": None,
                "transport_phase": "response_complete", "connection_established": connected,
                "request_write_attempted": write_attempted}
    except (OSError, http.client.HTTPException) as exc:
        return {"status": None, "body": None, "retry_after": None,
                "transport_error": type(exc).__name__, "transport_phase": phase,
                "connection_established": connected, "request_write_attempted": write_attempted,
                "operation_outcome": "not_sent" if phase == "connect" and not write_attempted else "unknown"}
    finally:
        conn.close()


def make_case(case_id: str, title: str, checks: dict[str, bool], observations: dict[str, Any]) -> dict[str, Any]:
    return {"id": case_id, "title": title, "status": "passed" if all(checks.values()) else "failed",
            "checks": checks, "observations": observations}


def execute_case(case_id: str, root: Path, mode: str, deadline: Deadline, owned: list[Fixture]) -> dict[str, Any]:
    deadline.remaining()
    store = Store(root / f"{case_id}.sqlite3")
    operation = f"fixture-{case_id}"
    if case_id == "NET-001":
        # A bound, non-listening port prevents another process taking the tested port.
        # Linux may refuse immediately; macOS can time out before connecting. Require
        # evidence of the pre-write boundary, not one platform's errno spelling.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unavailable:
            unavailable.bind((LOOPBACK, 0))
            first = request(unavailable.getsockname()[1], deadline, operation)
            before = store.effect_count(operation)
        with Fixture(store, mode, owned) as server:
            retry = request(server.port, deadline, operation)
            after = store.effect_count(operation)
        return make_case(case_id, "Offline before submission then recovery", {
            "connection_unavailable_before_send": (
                first["transport_error"] in {"ConnectionRefusedError", "TimeoutError"}
                and first.get("transport_phase") == "connect"
                and first.get("connection_established") is False
                and first.get("request_write_attempted") is False
                and first["status"] is None
            ),
            "no_effect_before_recovery": before == 0,
            "recovered_response": retry["status"] == 200, "effect_once": after == 1,
        }, {"first": first, "recovery": retry, "effects_before_recovery": before, "effects_after_recovery": after})
    if case_id == "NET-009":
        with Fixture(store, mode, owned) as server:
            first = request(server.port, deadline, operation, fault="rate_limit_once")
            before = store.effect_count(operation)
            # Retry-After=0 permits an immediate retry; total attempts remain exactly two.
            retry = request(server.port, deadline, operation, fault="rate_limit_once")
            after = store.effect_count(operation)
            attempts = server.server.attempts.get(operation, 0)
        return make_case(case_id, "Rate limit then one bounded recovery attempt", {
            "rate_limit_observed": first["status"] == 429 and first["retry_after"] == "0",
            "rate_limit_has_no_effect": before == 0, "recovered_response": retry["status"] == 200,
            "bounded_attempts": attempts == 2, "effect_once": after == 1,
        }, {"first": first, "recovery": retry, "attempts": attempts, "effects_before_recovery": before,
            "effects_after_recovery": after})
    fault = "delay_reply" if case_id == "NET-005" else "drop_reply"
    with Fixture(store, mode, owned) as server:
        first = request(server.port, deadline, operation, fault=fault,
                        timeout=TIMEOUT_CLIENT_WAIT if fault == "delay_reply" else REQUEST_TIMEOUT)
        before = store.effect_count(operation)
        if case_id != "NET-017":
            retry = request(server.port, deadline, operation)
            after = store.effect_count(operation)
    if case_id == "NET-017":
        # Fresh Store + HTTP server objects; only the SQLite file carries state forward.
        restarted_store = Store(store.path)
        with Fixture(restarted_store, mode, owned) as restarted:
            retry = request(restarted.port, deadline, operation)
            after = restarted_store.effect_count(operation)
    expected_errors = {"TimeoutError"} if fault == "delay_reply" else {"RemoteDisconnected", "ConnectionResetError"}
    return make_case(case_id, {
        "NET-004": "Committed operation with a lost reply and retry",
        "NET-005": "Committed operation with a response timeout and retry",
        "NET-017": "Lost reply then fresh server instance with durable operation records",
    }[case_id], {
        "fault_observed": first["transport_error"] in expected_errors,
        "effect_committed_before_retry": before == 1, "recovered_response": retry["status"] == 200,
        "effect_once": after == 1,
    }, {"first": first, "recovery": retry, "effects_before_retry": before, "effects_after_retry": after,
        "restart_kind": "new_server_and_store_instances_same_sqlite_file" if case_id == "NET-017" else None})


def run_fixture_suite(mode: str, deadline: Deadline) -> dict[str, Any]:
    if mode not in {"buggy", "corrected"}:
        raise ValueError("fixture mode must be buggy or corrected")
    cases: list[dict[str, Any]] = []
    owned: list[Fixture] = []
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="deep-product-audit-network-") as temporary:
        root = Path(temporary)
        for case_id in LAB_SCENARIOS:
            try:
                cases.append(execute_case(case_id, root, mode, deadline, owned))
            except (OSError, sqlite3.Error, DeadlineExceeded, RuntimeError) as exc:
                cases.append({"id": case_id, "status": "blocked", "reason": f"{type(exc).__name__}: {exc}"})
                errors.append(f"{case_id}: {type(exc).__name__}")
                if isinstance(exc, DeadlineExceeded):
                    break
    completed = {case["id"] for case in cases}
    for case_id in LAB_SCENARIOS:
        if case_id not in completed:
            cases.append({"id": case_id, "status": "not_tested", "reason": "fixture deadline exhausted"})
    cleanup = {"temporary_data_removed": not root.exists(),
               "owned_servers_closed": all(server.closed for server in owned),
               "owned_server_threads_stopped": all(not server.thread.is_alive() for server in owned)}
    return {"mode": mode, "cases": cases, "cleanup": cleanup, "infrastructure_errors": errors,
            "all_invariants_passed": all(case["status"] == "passed" for case in cases) and all(cleanup.values())}


def run_lab(mode: str = "compare", deadline_seconds: float = MAX_DEADLINE_SECONDS) -> dict[str, Any]:
    if mode not in {"compare", "buggy", "corrected"}:
        raise ValueError("mode must be compare, buggy, or corrected")
    start = time.monotonic()
    deadline = Deadline(deadline_seconds)
    modes = ("buggy", "corrected") if mode == "compare" else (mode,)
    suites = [run_fixture_suite(item, deadline) for item in modes]
    passed = all(suite["all_invariants_passed"] for suite in suites)
    discrimination: dict[str, Any] | None = None
    if mode == "compare":
        buggy, corrected = suites
        observed = {case["id"] for case in buggy["cases"] if case["status"] == "failed"}
        # Accept only the intended, independently observed duplicate-effect failures.
        exact_duplicate_failures = all(
            case.get("checks", {}).get("effect_once") is False
            and all(value for name, value in case.get("checks", {}).items() if name != "effect_once")
            and case.get("observations", {}).get("effects_after_retry") == 2
            for case in buggy["cases"] if case["id"] in SEEDED_DEFECT_SCENARIOS
        )
        unaffected_pass = all(case["status"] == "passed" for case in buggy["cases"]
                              if case["id"] not in SEEDED_DEFECT_SCENARIOS)
        discrimination = {"expected_seeded_failures": sorted(SEEDED_DEFECT_SCENARIOS),
                          "observed_seeded_failures": sorted(observed),
                          "duplicate_effect_oracle_confirmed": exact_duplicate_failures,
                          "unaffected_cases_passed": unaffected_pass}
        passed = (observed == SEEDED_DEFECT_SCENARIOS and exact_duplicate_failures and unaffected_pass
                  and corrected["all_invariants_passed"] and not buggy["infrastructure_errors"]
                  and all(buggy["cleanup"].values()))
    return {"schema_version": 1, "lab_version": VERSION, "kind": "isolated_fixture_validation", "mode": mode,
            "fixture_validation_passed": passed, "product_accepted": False,
            "scope": "Synthetic loopback HTTP fixtures only; no audited product was contacted.",
            "elapsed_seconds": round(time.monotonic() - start, 4), "deadline_seconds": deadline_seconds,
            "suites": suites, "discrimination": discrimination,
            "limitations": ["Fresh server instances simulate restart; this is not an OS/process crash test.",
                            "Rate-limit fixture uses Retry-After=0 and one retry; it does not validate jitter/backoff policies.",
                            "No TLS, DNS, WebSocket, packet loss, real browser, native UI, or production load is exercised.",
                            "Passing the lab validates these fixtures and oracles, not any product or third-party adapter."]}


def load_profiles() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "assets" / "network-profiles.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("compare", "buggy", "corrected"), default="compare")
    parser.add_argument("--out", type=Path, help="Create a new JSON result file; never overwrite existing evidence.")
    parser.add_argument("--deadline-seconds", type=float, default=MAX_DEADLINE_SECONDS,
                        help="Cooperative deadline, greater than 0 and at most 15; socket operations have separate bounds.")
    parser.add_argument("--list-profiles", action="store_true", help="Read bundled profiles without starting fixtures.")
    args = parser.parse_args(argv)
    if not 0 < args.deadline_seconds <= MAX_DEADLINE_SECONDS:
        parser.error("--deadline-seconds must be greater than 0 and at most 15")
    if args.out and (args.out.exists() or args.out.is_symlink()):
        parser.error("--out must name a new file")
    if args.out and not args.out.parent.is_dir():
        parser.error("--out parent directory must already exist")
    try:
        result = load_profiles() if args.list_profiles else run_lab(args.mode, args.deadline_seconds)
        if args.out:
            with args.out.open("x", encoding="utf-8") as output:
                json.dump(result, output, indent=2)
                output.write("\n")
            print(json.dumps({"out": str(args.out), "fixture_validation_passed": result.get("fixture_validation_passed"),
                              "product_accepted": False}))
        else:
            print(json.dumps(result, indent=2))
        return 0 if args.list_profiles or result["fixture_validation_passed"] else 1
    except KeyboardInterrupt:
        print(json.dumps({"status": "cancelled", "product_accepted": False}), file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}", "product_accepted": False}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    # A normal SIGTERM follows the same owned-fixture cleanup path as Ctrl-C.
    def cancel(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, cancel)
    sys.exit(main())
