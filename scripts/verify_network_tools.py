#!/usr/bin/env python3
"""Verify installed k6/Toxiproxy against owned localhost fixtures, never products."""
from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

TOOLS = {"k6": "k6", "toxiproxy": "toxiproxy-server"}
TOTAL_SECONDS = 30


def child_environment() -> dict[str, str]:
    # Do not inherit configured cloud outputs, dashboards or proxy routing.
    proxies = {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    return {key: value for key, value in os.environ.items()
            if not key.upper().startswith("K6_") and key.lower() not in proxies}


def remaining(deadline: float, cap: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError("network-tool verification deadline exhausted")
    return min(value, cap)


class Handler(BaseHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(0.5)

    def log_message(self, *_args: Any) -> None:
        pass

    def do_GET(self) -> None:
        with self.server.fixture_lock:
            self.server.fixture_requests += 1
        body = self.server.fixture_nonce.encode()
        try:
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass


@contextmanager
def fixture():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    server.block_on_close = True
    server.fixture_nonce = uuid.uuid4().hex
    server.fixture_requests = 0
    server.fixture_lock = threading.Lock()
    server.fixture_closed = False
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01},
                              name="audit-network-tool-fixture")
    try:
        thread.start()
        yield server
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()
        if thread.ident is not None:
            thread.join(timeout=1)
        server.fixture_closed = not thread.is_alive() and server.socket.fileno() == -1
        if not server.fixture_closed:
            raise RuntimeError("owned HTTP fixture did not close")


def get_fixture(port: int, nonce: str, deadline: float) -> dict[str, Any]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=remaining(deadline, 0.5))
    try:
        connection.request("GET", "/fixture")
        response = connection.getresponse()
        body = response.read(4096).decode()
        return {"valid": response.status == 200 and body == nonce, "status": response.status,
                "transport_error": None}
    except (OSError, http.client.HTTPException) as exc:
        return {"valid": False, "status": None, "transport_error": type(exc).__name__}
    finally:
        connection.close()


def run_k6(binary: str, directory: Path, server: Any, deadline: float) -> dict[str, Any]:
    config, script, summary = directory / "config.json", directory / "smoke.js", directory / "summary.json"
    config.write_text("{}\n")
    url = f"http://127.0.0.1:{server.server_address[1]}/fixture"
    options = {"scenarios": {"smoke": {"executor": "shared-iterations", "vus": 1, "iterations": 3,
                                       "maxDuration": "3s"}},
               "thresholds": {"checks": ["rate==1"], "http_req_failed": ["rate==0"]}}
    script.write_text("import http from 'k6/http';\nimport { check } from 'k6';\n"
                      + "export const options = " + json.dumps(options) + ";\n"
                      + "export default function () { const r = http.get(" + json.dumps(url)
                      + ", { timeout: '1s' }); check(r, { 'owned fixture body': x => x.status === 200 && x.body === "
                      + json.dumps(server.fixture_nonce) + " }); }\n")
    args = [binary, "run", "--no-usage-report", "--include-system-env-vars=false", "--config", str(config),
            "--quiet", "--no-color", "--summary-export", str(summary), str(script)]
    result = subprocess.run(args, stdin=subprocess.DEVNULL, text=True, capture_output=True,
                            timeout=remaining(deadline, 10), env=child_environment())
    data = json.loads(summary.read_text()) if summary.is_file() else {}
    metric = data.get("metrics", {}).get("iterations", {})
    iterations = metric.get("values", metric).get("count")
    checks = {"process_passed_thresholds": result.returncode == 0, "summary_iterations_three": iterations == 3,
              "fixture_received_three_requests": server.fixture_requests == 3}
    return {"checks": checks, "fixture_verified": all(checks.values()), "exit_code": result.returncode,
            "observed_requests": server.fixture_requests, "iterations": iterations,
            "runner_output_tail": (result.stdout + result.stderr)[-2500:]}


def control(port: int, method: str, path: str, deadline: float, payload: Any = None) -> Any:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=remaining(deadline, 0.5)) as response:
        body = response.read(65536)
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body.decode("utf-8")


def stop_child(child: subprocess.Popen[Any]) -> bool:
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=1)
    return child.poll() is not None


def run_toxiproxy(binary: str, directory: Path, server: Any, deadline: float) -> dict[str, Any]:
    # The selected port is random and loopback-only; readiness also checks our child remains alive.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    name = "audit_" + uuid.uuid4().hex
    result: dict[str, Any] = {"fixture_verified": False, "owned_child_stopped": False}
    created = False
    with (directory / "toxiproxy.log").open("w+") as log:
        child = subprocess.Popen([binary, "-host", "127.0.0.1", "-port", str(port)],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 env=child_environment())
        try:
            ready_by = min(deadline, time.monotonic() + 3)
            while True:
                if child.poll() is not None:
                    raise RuntimeError("owned Toxiproxy process exited before readiness")
                try:
                    control(port, "GET", "/version", ready_by)
                    if child.poll() is not None:
                        raise RuntimeError("owned Toxiproxy process exited during readiness")
                    break
                except (OSError, ValueError):
                    remaining(ready_by, 0.5)
                    time.sleep(0.02)
            proxy = control(port, "POST", "/proxies", deadline, {
                "name": name, "listen": "127.0.0.1:0",
                "upstream": f"127.0.0.1:{server.server_address[1]}", "enabled": True})
            created = True
            host, proxy_port = proxy["listen"].rsplit(":", 1)
            if host != "127.0.0.1" or not 0 < int(proxy_port) < 65536:
                raise RuntimeError("proxy did not return a loopback ephemeral listener")
            baseline = get_fixture(int(proxy_port), server.fixture_nonce, deadline)
            control(port, "POST", f"/proxies/{name}/toxics", deadline, {
                "name": "audit_timeout", "type": "timeout", "stream": "downstream", "toxicity": 1.0,
                "attributes": {"timeout": 50}})
            fault = get_fixture(int(proxy_port), server.fixture_nonce, deadline)
            control(port, "DELETE", f"/proxies/{name}/toxics/audit_timeout", deadline)
            recovery = get_fixture(int(proxy_port), server.fixture_nonce, deadline)
            checks = {"baseline_valid": baseline["valid"],
                      "fault_observed": fault["transport_error"] in {"TimeoutError", "RemoteDisconnected", "ConnectionResetError"},
                      "recovery_valid": recovery["valid"], "independent_fixture_received_requests": server.fixture_requests >= 2}
            result.update({"checks": checks, "fixture_verified": all(checks.values()), "baseline": baseline,
                           "fault": fault, "recovery": recovery, "observed_requests": server.fixture_requests})
        finally:
            if created and child.poll() is None:
                try:
                    control(port, "DELETE", f"/proxies/{name}", time.monotonic() + 0.5)
                except (OSError, ValueError):
                    result["proxy_cleanup"] = "owned process termination required"
            result["owned_child_stopped"] = stop_child(child)
            result["fixture_verified"] = result["fixture_verified"] and result["owned_child_stopped"]
    return result


def verify_tools(names: list[str]) -> dict[str, Any]:
    if not names or len(set(names)) != len(names) or any(name not in TOOLS for name in names):
        raise ValueError("select unique tool names from k6,toxiproxy")
    deadline = time.monotonic() + TOTAL_SECONDS
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="deep-audit-network-tools-") as temporary:
        for name in names:
            binary = shutil.which(TOOLS[name])
            record: dict[str, Any] = {"tool": name, "binary": binary, "discovered": binary is not None,
                                      "runnable": False, "fixture_verified": False, "product_executed": False,
                                      "state": "missing" if binary is None else "discovered"}
            results.append(record)
            if binary is None:
                continue
            try:
                version = subprocess.run([binary, "version" if name == "k6" else "-version"],
                                         stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                         timeout=remaining(deadline, 3), env=child_environment())
                record["version"] = (version.stdout + version.stderr).strip()[:512]
                record["runnable"] = version.returncode == 0
                if not record["runnable"]:
                    record["state"] = "blocked"
                    record["reason"] = "version command failed"
                    continue
                directory = Path(temporary) / name
                directory.mkdir()
                with fixture() as server:
                    observed = (run_k6 if name == "k6" else run_toxiproxy)(binary, directory, server, deadline)
                record.update(observed)
                record["fixture_server_closed"] = server.fixture_closed
                record["fixture_verified"] = record["fixture_verified"] and server.fixture_closed
                record["state"] = "fixture_verified" if record["fixture_verified"] else "failed"
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
                record["state"] = "blocked"
                record["reason"] = f"{type(exc).__name__}: {exc}"
    return {"schema_version": 1, "kind": "installed_network_tool_fixture_verification", "tools": results,
            "all_selected_fixture_verified": all(record["fixture_verified"] for record in results),
            "product_executed": False, "product_accepted": False, "temporary_data_removed": not Path(temporary).exists(),
            "scope": "Owned ephemeral localhost HTTP fixtures only; no product or external destination was tested.",
            "limits": "1 VU/3 k6 iterations and one Toxiproxy baseline/fault/recovery; no load, soak or product coverage."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", default="k6,toxiproxy", help="Comma-separated selection: k6,toxiproxy")
    parser.add_argument("--out", type=Path, help="Create a new result file; existing files/symlinks are rejected before execution.")
    args = parser.parse_args(argv)
    names = args.tools.split(",")
    if not names or len(set(names)) != len(names) or any(name not in TOOLS for name in names):
        parser.error("--tools must select unique names from k6,toxiproxy")
    if args.out and (args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir()):
        parser.error("--out must be a new file in an existing directory")
    try:
        result = verify_tools(names)
        if args.out:
            with args.out.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2)
                handle.write("\n")
        print(json.dumps(result, indent=2))
        return 0 if result["all_selected_fixture_verified"] else 1
    except KeyboardInterrupt:
        print(json.dumps({"status": "cancelled", "product_executed": False}), file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc), "product_executed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    def cancel(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, cancel)
    sys.exit(main())
