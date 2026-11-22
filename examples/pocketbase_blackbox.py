#!/usr/bin/env python3
"""Independent black-box smoke of an upstream PocketBase release; disposable loopback."""
from __future__ import annotations
import argparse
import hashlib
import os
import json
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import zipfile
import time
import urllib.error
import urllib.request

BIN: Path | None = None
RELEASE_SHA = "7f2f7544e9ee5994ab69f84b22a4ab9a3bcfed58c1dad7206d05ebeb753f968b"
RELEASE = "0.40.6"


class _NoExternalRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A tested application must not redirect this probe off loopback.
        return None


_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoExternalRedirects())


def sanitized_env(temporary_home: Path) -> dict[str, str]:
    # Never inherit an operator's real credential, API-token or cloud env.
    return {"PATH": os.defpath, "HOME": str(temporary_home),
            "TMPDIR": str(temporary_home), "LANG": "C"}


def request(base_url, method, route, payload=None, token=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = token
    req = urllib.request.Request(base_url + route, data=data, headers=headers, method=method)
    try:
        with _HTTP.open(req, timeout=4) as res:
            body = res.read(1024 * 1024)
            return res.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as error:
        body = error.read(1024 * 1024)
        return error.code, (json.loads(body) if body else {})


def start(port, data_dir):
    # Only a disposable loopback listener; no external providers and no live accounts.
    proc = subprocess.Popen(
        [str(BIN), "serve", "--http", f"127.0.0.1:{port}", "--dir", str(data_dir)],
        cwd=data_dir.parent, env=sanitized_env(data_dir.parent),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if proc.poll() is not None:
                raise AssertionError("Disposable PocketBase server exited unexpectedly")
            try:
                status, _ = request(f"http://127.0.0.1:{port}", "GET", "/api/health")
                if status == 200:
                    return proc
            except (OSError, ValueError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        raise TimeoutError("No PocketBase health response within 10 seconds")
    except Exception:
        stop(proc)
        raise


def stop(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def assert_status(status, expected, label):
    if status not in expected:
        raise AssertionError(f"{label}: expected {expected}, got HTTP {status}")


def check(label, condition, evidence, observed=None):
    assert condition, f"{label}: {evidence}"
    record = {"check": label, "state": "passed", "oracle": evidence}
    if observed is not None:
        record["observed"] = observed
    return record


def main():
    global BIN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path,
                        help="Manually downloaded official macOS ARM64 PocketBase executable")
    parser.add_argument("--archive", required=True, type=Path,
                        help="Official release ZIP, matched to pinned SHA-256")
    parser.add_argument("--out", required=True, type=Path,
                        help="New report file (refuses overwrite); keep outside source checkout")
    args = parser.parse_args()
    BIN = args.binary.resolve(strict=True)
    archive = args.archive.resolve(strict=True)
    if not BIN.is_file() or not archive.is_file():
        raise ValueError("Both the binary and archive must be regular files")
    check("release_asset_sha256", hashlib.sha256(archive.read_bytes()).hexdigest() == RELEASE_SHA,
          "Official GitHub release digest")
    with zipfile.ZipFile(archive) as z:
        assert hashlib.sha256(BIN.read_bytes()).digest() == hashlib.sha256(z.read("pocketbase")).digest(), (
            "Executable bytes differ from the verified release archive")
    version = subprocess.run([str(BIN), "--version"], text=True,
                             capture_output=True, timeout=10)
    assert version.returncode == 0 and f"version {RELEASE}" in version.stdout, (
        "Unexpected PocketBase executable version")
    with tempfile.TemporaryDirectory(prefix="dpa-owned-upstream-") as td:
        data_dir = Path(td) / "pb_data"
        admin_pass = secrets.token_urlsafe(24)
        user_a_pass = secrets.token_urlsafe(24)
        user_b_pass = secrets.token_urlsafe(24)
        admin_email = "administrator@example.invalid"
        run = subprocess.run(
            [str(BIN), "superuser", "create", admin_email, admin_pass, "--dir", str(data_dir)],
            cwd=td, env=sanitized_env(Path(td)),
            capture_output=True, text=True, timeout=15
        )
        if run.returncode:
            # Avoid printing passwords, private paths or startup output.
            raise AssertionError(f"Disposable superuser creation failed (exit {run.returncode})")

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        results = []
        proc = start(port, data_dir)
        try:
            st, super_auth = request(url, "POST", "/api/collections/_superusers/auth-with-password",
                                     {"identity": admin_email, "password": admin_pass})
            assert_status(st, {200}, "superuser login")
            super_token = super_auth["token"]

            st, members = request(url, "POST", "/api/collections", {
                "name": "members", "type": "auth",
                "fields": [{"name": "displayName", "type": "text"}],
                "passwordAuth": {"enabled": True, "identityFields": ["email"]},
            }, super_token)
            assert_status(st, {200}, "members collection")
            st, notes = request(url, "POST", "/api/collections", {
                "name": "audit_notes", "type": "base",
                "fields": [
                    {"name": "title", "type": "text", "required": True},
                    {"name": "owner", "type": "relation", "required": True,
                     "collectionId": members["id"], "maxSelect": 1},
                ],
                "listRule": '@request.auth.id != "" && owner = @request.auth.id',
                "viewRule": '@request.auth.id != "" && owner = @request.auth.id',
                "createRule": '@request.auth.id != "" && owner = @request.auth.id',
                "updateRule": '@request.auth.id != "" && owner = @request.auth.id',
                "deleteRule": '@request.auth.id != "" && owner = @request.auth.id',
            }, super_token)
            assert_status(st, {200}, "notes collection")
            results.append(check("real_backend_configured", members.get("name") == "members" and notes.get("name") == "audit_notes",
                                 "Superuser-created separate auth and rule-protected base collections"))

            users = []
            for email,password in (("alice@example.invalid", user_a_pass),
                                   ("bob@example.invalid", user_b_pass)):
                st, rec = request(url, "POST", "/api/collections/members/records", {
                    "email": email, "password": password, "passwordConfirm": password,
                }, super_token)
                assert_status(st, {200}, "create disposable user")
                st, authed = request(url, "POST", "/api/collections/members/auth-with-password", {
                    "identity": email, "password": password,
                })
                assert_status(st, {200}, "login disposable user")
                users.append((rec["id"], authed["token"]))
            a_id, a_token = users[0]
            b_id, b_token = users[1]
            results.append(check("real_authentication", a_id != b_id and a_token != b_token,
                                 "Two real user login tokens with distinct server-issued account IDs"))

            # Negative auth control: an invalid credential must never receive a token.
            st_invalid, invalid_auth = request(
                url, "POST", "/api/collections/members/auth-with-password",
                {"identity": "bob@example.invalid", "password": "intentionally-wrong"}
            )
            results.append(check(
                "invalid_auth_denied",
                st_invalid in {400, 401, 403} and not invalid_auth.get("token"),
                "Wrong password denied without an auth token",
                {"wrong_password_login": st_invalid}
            ))

            st, record = request(url, "POST", "/api/collections/audit_notes/records", {
                "title": "persisted-draft-v1", "owner": a_id,
            }, a_token)
            assert_status(st, {200}, "owner create")
            item_id = record["id"]
            results.append(check("owner_write", record.get("owner") == a_id and record.get("title") == "persisted-draft-v1",
                                 "Owner A created a real SQLite-backed record via authenticated REST API"))

            item_url = f"/api/collections/audit_notes/records/{item_id}"
            st, own = request(url, "GET", item_url, token=a_token)
            assert_status(st, {200}, "owner read")
            st_guest, _ = request(url, "GET", item_url)
            st_b, _ = request(url, "GET", item_url, token=b_token)
            st_b_list, b_list = request(url, "GET", "/api/collections/audit_notes/records", token=b_token)
            results.append(check("tenant_read_isolation",
                                 own["id"] == item_id and st_guest in {401, 403, 404}
                                 and st_b in {401, 403, 404}
                                 and st_b_list == 200 and not b_list.get("items"),
                                 "Independent HTTP oracles: owner reads; anonymous/other-user cannot read/list foreign record",
                                 {"owner_get": st, "guest_get": st_guest, "other_user_get": st_b,
                                  "other_user_list": st_b_list, "other_user_items": len(b_list.get("items", []))}))
            st_b_update, _ = request(url, "PATCH", item_url, {"title": "unauthorized-edit"}, b_token)
            st_b_create, _ = request(url, "POST", "/api/collections/audit_notes/records", {
                "title": "unauthorized-own", "owner": a_id,
            }, b_token)
            results.append(check("tenant_write_isolation",
                                 st_b_update in {400, 401, 403, 404}
                                 and st_b_create in {400, 401, 403, 404},
                                 "Cross-account update and forged owner create both denied",
                                 {"other_user_patch": st_b_update, "forged_owner_post": st_b_create}))

            # Clean control: user B *must* be able to create and read B's own data.
            st_b_own, record_b = request(
                url, "POST", "/api/collections/audit_notes/records",
                {"title": "independent-b-draft", "owner": b_id}, b_token
            )
            assert_status(st_b_own, {200}, "authorized B create")
            b_item_id = record_b["id"]
            b_item_url = f"/api/collections/audit_notes/records/{b_item_id}"
            st_b_read, b_own = request(url, "GET", b_item_url, token=b_token)
            st_a_foreign, _ = request(url, "GET", b_item_url, token=a_token)
            st_b_list_own, b_list_own = request(
                url, "GET", "/api/collections/audit_notes/records", token=b_token
            )
            st_a_list_own, a_list_own = request(
                url, "GET", "/api/collections/audit_notes/records", token=a_token
            )
            results.append(check(
                "second_tenant_clean_control",
                st_b_own == 200 and st_b_read == 200
                and b_own.get("id") == b_item_id
                and st_a_foreign in {401, 403, 404}
                and st_b_list_own == 200
                and [x["id"] for x in b_list_own.get("items", [])] == [b_item_id]
                and st_a_list_own == 200
                and [x["id"] for x in a_list_own.get("items", [])] == [item_id],
                "Two tenants each complete their own successful, mutually isolated journey",
                {"b_create": st_b_own, "b_read": st_b_read, "a_foreign_read": st_a_foreign,
                 "b_visible_record_count": len(b_list_own.get("items", [])),
                 "a_visible_record_count": len(a_list_own.get("items", []))}
            ))

            st, changed = request(url, "PATCH", item_url, {"title": "persisted-draft-v2"}, a_token)
            assert_status(st, {200}, "authorized edit")
            results.append(check("authorized_update", changed.get("title") == "persisted-draft-v2",
                                 "Owner A update acknowledged by real server"))

            invalid_update_status, _ = request(
                url, "PATCH", item_url, {"title": ""}, a_token
            )
            unchanged_status, unchanged = request(url, "GET", item_url, token=a_token)
            results.append(check(
                "invalid_input_preserves_prior_state",
                invalid_update_status in {400, 422} and unchanged_status == 200
                and unchanged.get("title") == "persisted-draft-v2",
                "Rejected empty required field cannot corrupt the prior successful write",
                {"invalid_patch": invalid_update_status, "unchanged_read": unchanged_status}
            ))
            stop(proc)
            proc = None
            # Confirm service is not responding while intentionally stopped.
            try:
                request(url, "GET", item_url, token=a_token)
                raise AssertionError("Stopped service still served a request")
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                pass

            proc = start(port, data_dir)
            st, own2 = request(url, "GET", item_url, token=a_token)
            assert_status(st, {200}, "read after process restart")
            st_other2, _ = request(url, "GET", item_url, token=b_token)
            results.append(check("durable_restart_and_isolation",
                                 own2.get("title") == "persisted-draft-v2" and st_other2 in {401, 403, 404},
                                 "Independent new process readback plus continued cross-account deny",
                                 {"owner_restart_get": st, "other_user_restart_get": st_other2}))
            db_path = data_dir / "data.db"
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3) as db:
                rows = db.execute('SELECT id,title,owner FROM audit_notes WHERE id=?', (item_id,)).fetchall()
            results.append(check("independent_sqlite_oracle",
                                 rows == [(item_id, "persisted-draft-v2", a_id)],
                                 "Read-only SQLite inspection matches API ID, owner and saved title",
                                 {"sqlite_matching_rows": len(rows)}))

            st, _ = request(url, "DELETE", item_url, token=a_token)
            assert_status(st, {200, 204}, "owner delete")
            st, _ = request(url, "GET", item_url, token=a_token)
            results.append(check("authorized_delete", st in {400, 404},
                                 "Owner record is no longer retrievable after authorized deletion",
                                 {"owner_post_delete_get": st}))

            # Clean regression: deleting A's record cannot touch B's legitimate record.
            st_b_survives, b_survives = request(url, "GET", b_item_url, token=b_token)
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3) as db:
                remaining = db.execute(
                    'SELECT id,title,owner FROM audit_notes ORDER BY id'
                ).fetchall()
            results.append(check(
                "other_tenant_unchanged_after_delete",
                st_b_survives == 200 and b_survives.get("title") == "independent-b-draft"
                and remaining == [(b_item_id, "independent-b-draft", b_id)],
                "After deleting A, B's record still exists in API and independent SQLite readback",
                {"b_survivor_get": st_b_survives, "remaining_sqlite_rows": len(remaining)}
            ))
        finally:
            if proc is not None:
                stop(proc)
        assert len(results) == 13
        report = {
            "target": "PocketBase open-source backend",
            "target_version": RELEASE,
            "target_release_url": "https://github.com/pocketbase/pocketbase/releases/tag/v0.40.6",
            "binary_archive_sha256": RELEASE_SHA,
            "environment": "disposable macOS ARM64 loopback, no external accounts",
            "test_kind": "black-box integration and persistence smoke; NOT an agent discovery or seeded bug trial",
            "checks": results,
            "passed": len(results), "blocked": 0, "untested": 0,
            "results_scope": [
                "Local authentication, two principal API authorization, CRUD, sqlite readback and process restart",
                "No UI control interaction, payment processing, full security audit or upstream issue reproduction",
            ],
            "credentials": "generated only for disposable local process, never persisted in report",
            "local_data_disposition": "temporary database directory removed at scope exit",
        }
        outfile = args.out
        with outfile.open("x", encoding="utf-8") as out:
            out.write(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"target": report["target"], "version": report["target_version"],
                          "passed": report["passed"], "blocked": 0, "untested": 0,
                          "report": outfile.name}, sort_keys=True))


if __name__ == "__main__":
    main()
