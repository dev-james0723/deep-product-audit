#!/usr/bin/env python3
"""Create, check, and summarize a local product-audit evidence bundle.

Only the Python standard library is required. Version 1 ledgers remain readable.
Version 2 distinguishes data integrity, investigation completeness, recorded
checks passing, and evidence-backed release eligibility. These gates check records,
not evidence authenticity, undiscovered coverage, or authority to deploy.
Evidence paths use relative POSIX notation. Output commands never overwrite files.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import parse_qsl, unquote, urlsplit
import uuid


STATUSES = {"passed", "failed", "blocked", "not_tested", "out_of_scope"}
EVIDENCE_TYPES = {"screenshot", "trace", "video", "test", "log", "source", "runtime"}
EXECUTION_EVIDENCE = {"runtime", "test", "log"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
URL = re.compile(r"https?://[^\s<>\"`]+", re.IGNORECASE)
SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
SENSITIVE_QUERY_KEYS = {
    "token", "accesstoken", "refreshtoken", "idtoken", "authtoken", "bearer",
    "secret", "clientsecret", "password", "passwd", "pwd", "passcode", "otp",
    "key", "apikey", "accesskey", "secretkey", "signature", "sig", "credential",
    "authorization", "auth", "code", "verificationcode", "session", "sessionid",
    "ticket", "cookie", "policy", "awsaccesskeyid", "xamzcredential",
    "xamzsecuritytoken", "xamzsignature", "xgoogcredential", "xgoogsignature",
}
MAX_LEDGER_BYTES = 8 * 1024 * 1024


class LedgerError(Exception):
    """An expected CLI or ledger loading error with a safe, bounded message."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def timestamp_ok(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (ValueError, OverflowError):
        return False


def url_problem(value: str, require_http: bool = False) -> str | None:
    """Check URL shape and obvious credential-bearing URL components, not secrets generally."""
    try:
        parsed = urlsplit(value)
        if require_http and (parsed.scheme not in {"http", "https"} or not parsed.hostname):
            return "must be an absolute HTTP(S) URL with a hostname"
        if parsed.username is not None or parsed.password is not None:
            return "contains URL user information; remove credentials"
        _ = parsed.port  # Also reject invalid ports.
        for part in (parsed.query, parsed.fragment):
            decoded = unquote(part)
            for key, _value in parse_qsl(decoded, keep_blank_values=True):
                key = re.sub(r"[^a-z0-9]", "", unquote(key).lower())
                if key in SENSITIVE_QUERY_KEYS or key.endswith(("token", "secret", "password")):
                    return "contains a secret-like query or fragment parameter; use a clean URL"
        if re.search(r"(?:^|[/=])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", unquote(value)):
            return "contains a token-like URL component; use a clean URL"
        if any(ord(char) < 32 for char in value) or (require_http and any(char.isspace() for char in value)):
            return "contains invalid whitespace or control characters"
    except (ValueError, UnicodeError):
        return "is not a valid URL"
    return None


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError("Ledger contains duplicate JSON object keys.")
        result[key] = value
    return result


def reject_constant(_value: str) -> None:
    raise LedgerError("Ledger contains a non-finite JSON number.")


def load_ledger(path: str) -> tuple[Path, dict]:
    candidate = Path(path).expanduser()
    if candidate.is_dir():
        candidate /= "audit.json"
    try:
        candidate = candidate.resolve(strict=True)
        if not candidate.is_file() or candidate.stat().st_size > MAX_LEDGER_BYTES:
            raise LedgerError("Ledger must be a regular JSON file no larger than 8 MiB.")
        data = json.loads(candidate.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise LedgerError("Cannot read ledger as valid UTF-8 JSON.") from exc
    if not isinstance(data, dict):
        raise LedgerError("Ledger root must be a JSON object.")
    return candidate, data


class LegacyValidator:
    def __init__(self, bundle: Path):
        self.bundle = bundle.resolve()
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.ids: set[str] = set()

    def error(self, location: str, message: str) -> None:
        self.errors.append(f"{location}: {message}")

    def text(self, obj: dict, key: str, location: str, allow_empty: bool = False) -> bool:
        value = obj.get(key)
        valid = isinstance(value, str) and (allow_empty or bool(value.strip()))
        if not valid:
            self.error(f"{location}.{key}", "must be a string" if allow_empty else "must be a nonempty string")
        return valid

    def enum(self, obj: dict, key: str, allowed: set[str], location: str) -> bool:
        value = obj.get(key)
        if not isinstance(value, str) or value not in allowed:
            self.error(f"{location}.{key}", "must be one of " + ", ".join(sorted(allowed)))
            return False
        return True

    def string_list(self, value: object, location: str, nonempty: bool = False) -> bool:
        if not isinstance(value, list) or any(not is_text(item) for item in value):
            self.error(location, "must be a list of nonempty strings")
            return False
        if nonempty and not value:
            self.error(location, "must contain at least one item")
            return False
        return True

    def identifier(self, obj: dict, location: str) -> bool:
        value = obj.get("id")
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            self.error(f"{location}.id", "must be a 1–128 character identifier (letters, numbers, . _ : -)")
            return False
        if value in self.ids:
            self.error(f"{location}.id", "duplicates another coverage or finding ID")
            return False
        self.ids.add(value)
        return True

    def scan_urls(self, value: object, location: str = "$") -> None:
        if isinstance(value, dict):
            for index, (key, child) in enumerate(value.items()):
                safe_key = key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,40}", key) else f"key_{index}"
                self.scan_urls(key, f"{location}.[key {index}]")
                self.scan_urls(child, f"{location}.{safe_key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self.scan_urls(child, f"{location}[{index}]")
        elif isinstance(value, str):
            for match in URL.finditer(value):
                problem = url_problem(match.group().rstrip(").,;]}"))
                if problem:
                    self.error(location, problem)

    def evidence(self, value: object, location: str, nonempty: bool = False) -> set[str]:
        valid_types: set[str] = set()
        if not isinstance(value, list):
            self.error(location, "must be a list of evidence objects")
            return valid_types
        if nonempty and not value:
            self.error(location, "must contain evidence")
        for index, item in enumerate(value):
            loc = f"{location}[{index}]"
            if not isinstance(item, dict):
                self.error(loc, "must be an evidence object")
                continue
            error_count = len(self.errors)
            self.enum(item, "type", getattr(self, "evidence_types", EVIDENCE_TYPES), loc)
            if "observed_at" in item and not timestamp_ok(item["observed_at"]):
                self.error(f"{loc}.observed_at", "must be an ISO 8601 timestamp with a timezone")
            if "summary" in item:
                self.text(item, "summary", loc)
            digest = item.get("sha256")
            if "sha256" in item and (not isinstance(digest, str) or not SHA256.fullmatch(digest)):
                self.error(f"{loc}.sha256", "must be a 64-character hexadecimal digest")
            if not self.text(item, "path", loc):
                continue
            raw = item["path"]
            relative = PurePosixPath(raw)
            if (relative.is_absolute() or ".." in relative.parts or "\\" in raw
                    or re.match(r"^[A-Za-z]:", raw) or "\x00" in raw or raw in {".", ""}):
                self.error(f"{loc}.path", "must be a relative bundle path without traversal")
                continue
            try:
                resolved = (self.bundle / raw).resolve(strict=True)
                if not resolved.is_relative_to(self.bundle):
                    self.error(f"{loc}.path", "escapes the bundle, including through a symlink")
                    continue
                info = resolved.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                    self.error(f"{loc}.path", "must reference an existing nonempty regular file")
                    continue
                if isinstance(digest, str) and SHA256.fullmatch(digest):
                    hasher = hashlib.sha256()
                    with resolved.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            hasher.update(chunk)
                    if hasher.hexdigest() != digest.lower():
                        self.error(f"{loc}.sha256", "does not match the evidence file")
            except (OSError, RuntimeError, ValueError):
                self.error(f"{loc}.path", "cannot resolve or read the evidence file")
            if len(self.errors) == error_count:
                valid_types.add(item["type"])
        return valid_types

    def validate(self, data: dict) -> dict:
        self.scan_urls(data)
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            self.error("$.schema_version", "must be integer 1")
        scope = data.get("scope")
        if not isinstance(scope, dict):
            self.error("$.scope", "must be an object")
            scope = {}
        for key in ("id", "target"):
            self.text(scope, key, "$.scope")
        if is_text(scope.get("target")):
            problem = url_problem(scope["target"], require_http=True)
            if problem:
                self.error("$.scope.target", problem)
        self.enum(scope, "profile", {"standard", "advanced"}, "$.scope")
        self.enum(scope, "environment", {"local", "staging", "production"}, "$.scope")
        if not timestamp_ok(scope.get("started_at")):
            self.error("$.scope.started_at", "must be an ISO 8601 timestamp with a timezone")
        if "build" not in scope or (scope["build"] is not None and not is_text(scope["build"])):
            self.error("$.scope.build", "must be a nonempty build identifier or null if unknown")
        elif scope["build"] is None:
            self.warnings.append("Build identity is unrecorded; evidence is not tied to a verified build.")
        for key in ("roles", "viewports"):
            if self.string_list(scope.get(key), f"$.scope.{key}"):
                if len(scope[key]) != len(set(scope[key])):
                    self.error(f"$.scope.{key}", "contains duplicate declarations")
                if not scope[key]:
                    self.warnings.append(f"Scope {key} have not been declared.")
        if not isinstance(data.get("capabilities"), dict):
            self.error("$.capabilities", "must be an object recording observed tool availability")

        coverage = data.get("coverage")
        if not isinstance(coverage, list):
            self.error("$.coverage", "must be a list")
            coverage = []
        coverage_ids: set[str] = set()
        for index, row in enumerate(coverage):
            loc = f"$.coverage[{index}]"
            if not isinstance(row, dict):
                self.error(loc, "must be a coverage object")
                continue
            if self.identifier(row, loc):
                coverage_ids.add(row["id"])
            for key in ("route", "role", "viewport", "state", "expected"):
                self.text(row, key, loc)
            self.text(row, "reason", loc, allow_empty=True)
            status_valid = self.enum(row, "status", STATUSES, loc)
            types = self.evidence(row.get("evidence"), f"{loc}.evidence")
            if status_valid and row["status"] in {"passed", "failed"} and not types & EXECUTION_EVIDENCE:
                self.error(f"{loc}.evidence", "passed/failed coverage requires valid runtime, test, or log evidence")
            if status_valid and row["status"] in {"blocked", "out_of_scope"} and not is_text(row.get("reason")):
                self.error(f"{loc}.reason", "blocked/out_of_scope coverage requires a reason")
            for singular, plural in (("role", "roles"), ("viewport", "viewports")):
                declared = scope.get(plural)
                if isinstance(declared, list) and declared and row.get(singular) not in declared:
                    self.error(f"{loc}.{singular}", "is not declared in scope")

        findings = data.get("findings")
        if not isinstance(findings, list):
            self.error("$.findings", "must be a list")
            findings = []
        for index, finding in enumerate(findings):
            loc = f"$.findings[{index}]"
            if not isinstance(finding, dict):
                self.error(loc, "must be a finding object")
                continue
            self.identifier(finding, loc)
            for key in ("title", "impact", "expected", "actual", "fix_status"):
                self.text(finding, key, loc)
            self.enum(finding, "severity", {"P0", "P1", "P2", "P3"}, loc)
            self.enum(finding, "kind", {"defect", "risk", "suggestion"}, loc)
            self.enum(finding, "confidence", {"certain", "likely", "guessing"}, loc)
            self.string_list(finding.get("steps"), f"{loc}.steps", nonempty=finding.get("kind") == "defect")
            refs = finding.get("coverage_ids")
            if self.string_list(refs, f"{loc}.coverage_ids"):
                if len(refs) != len(set(refs)):
                    self.error(f"{loc}.coverage_ids", "contains duplicate references")
                for ref_index, ref in enumerate(refs):
                    if ref not in coverage_ids:
                        self.error(f"{loc}.coverage_ids[{ref_index}]", "does not reference an existing coverage ID")
            self.evidence(finding.get("evidence"), f"{loc}.evidence", nonempty=True)
            root = finding.get("root_cause")
            if not isinstance(root, dict):
                self.error(f"{loc}.root_cause", "must be an object")
            else:
                self.text(root, "status", f"{loc}.root_cause")
                self.text(root, "hypothesis", f"{loc}.root_cause", allow_empty=True)
                self.evidence(root.get("evidence"), f"{loc}.root_cause.evidence")

        counts = Counter(row.get("status") for row in coverage if isinstance(row, dict)
                         and isinstance(row.get("status"), str) and row["status"] in STATUSES)
        counts = {key: counts[key] for key in sorted(STATUSES)}
        acceptance_errors: list[str] = []
        if not coverage:
            acceptance_errors.append("No coverage rows are recorded.")
        if coverage and not sum(counts[key] for key in STATUSES - {"out_of_scope"}):
            acceptance_errors.append("No in-scope checks are recorded.")
        for status in ("failed", "blocked", "not_tested"):
            if counts[status]:
                acceptance_errors.append(f"{counts[status]} coverage row(s) are {status}.")
        if findings:
            acceptance_errors.append(f"{len(findings)} finding(s) require review; fix_status alone is not acceptance evidence.")
        if self.errors:
            outcome = "invalid_evidence_bundle"
        elif counts["blocked"] or counts["not_tested"] or not coverage or not (counts["passed"] + counts["failed"]):
            outcome = "incomplete"
        elif counts["failed"] or findings:
            outcome = "findings_require_review"
        else:
            outcome = "recorded_checks_passed"
        return {
            "schema_version": 1,
            "integrity": {"valid": not self.errors, "errors": self.errors, "warnings": self.warnings},
            "acceptance": {"outcome": outcome, "strict_gate_passed": not self.errors and not acceptance_errors,
                           "product_accepted": False, "coverage": counts,
                           "covered": counts["passed"] + counts["failed"],
                           "findings": len(findings), "errors": acceptance_errors},
            "limits": "Checks establish ledger/file integrity and recorded coverage only; they do not prove evidence authenticity, complete product coverage, or release approval.",
        }


V2_STATUSES = STATUSES | {"unknown"}
V2_EVIDENCE_TYPES = EVIDENCE_TYPES | {"build", "deployment", "verification"}
REVISION = re.compile(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})\Z")
UNKNOWN_IDENTITIES = {"unknown", "unassigned", "none", "null", "n/a", "latest", "head", "main", "master"}
TARGET_KINDS = {"web", "api", "native", "cli", "mobile"}


def known_identity(value: object) -> bool:
    return (is_text(value) and value == value.strip() and len(value) <= 512
            and not any(ord(char) < 32 for char in value)
            and value.casefold() not in UNKNOWN_IDENTITIES)


def same_actor(left: object, right: object) -> bool:
    return isinstance(left, str) and isinstance(right, str) and left.strip().casefold() == right.strip().casefold()


def same_digest(left: object, right: object) -> bool:
    return isinstance(left, str) and isinstance(right, str) and left.lower() == right.lower()


def safe_id(value: object) -> str:
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else "<invalid-id>"


def target_problem(target: object) -> str | None:
    """Validate an identifier only; never resolve, open, or execute the target."""
    if not isinstance(target, dict):
        return "must be an object with kind and locator"
    kind, locator = target.get("kind"), target.get("locator")
    if not isinstance(kind, str) or kind not in TARGET_KINDS:
        return "kind must be web, api, native, cli, or mobile"
    if not is_text(locator) or any(ord(char) < 32 for char in locator):
        return "locator must be a nonempty string without control characters"
    if kind in {"web", "api"}:
        return url_problem(locator, require_http=True)
    platform = target.get("platform")
    allowed = {"macos", "windows", "linux"} if kind == "native" else {"ios", "android"}
    if kind in {"native", "mobile"} and (not isinstance(platform, str) or platform not in allowed):
        return "platform must be one of " + ", ".join(sorted(allowed))
    absolute = locator.startswith("/") or bool(re.match(r"^[A-Za-z]:[\\/]", locator))
    bundle_id = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+", locator))
    executable_name = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", locator))
    if kind == "mobile" and not bundle_id:
        return "mobile locator must be a bundle/package identifier"
    if kind == "native" and not (absolute or bundle_id):
        return "native locator must be an absolute app path or bundle/package identifier"
    if kind == "cli" and not (absolute or executable_name):
        return "CLI locator must identify one executable, without shell arguments"
    return None


class V2Validator(LegacyValidator):
    evidence_types = V2_EVIDENCE_TYPES

    def __init__(self, bundle: Path):
        super().__init__(bundle)
        self.observation_times: list[datetime] = []

    def hash_field(self, obj: dict, key: str, loc: str, revision: bool = False,
                   nullable: bool = False) -> bool:
        value = obj.get(key)
        if nullable and key in obj and value is None:
            return True
        pattern = REVISION if revision else SHA256
        if not isinstance(value, str) or not pattern.fullmatch(value):
            self.error(f"{loc}.{key}", "must be a full 40/64-hex source revision" if revision
                       else "must be a SHA-256 digest" + (" or null if unknown" if nullable else ""))
            return False
        return True

    def actor(self, obj: dict, key: str, loc: str) -> bool:
        if not known_identity(obj.get(key)):
            self.error(f"{loc}.{key}", "must identify the actual actor; unknown placeholders are not evidence")
            return False
        return True

    def timestamp(self, obj: dict, key: str, loc: str, allow_future: bool = False) -> bool:
        if not timestamp_ok(obj.get(key)):
            self.error(f"{loc}.{key}", "must be an ISO 8601 timestamp with a timezone")
            return False
        observed = datetime.fromisoformat(obj[key].replace("Z", "+00:00"))
        if not allow_future and observed > datetime.now(timezone.utc) + timedelta(minutes=5):
            self.error(f"{loc}.{key}", "cannot claim an observation more than five minutes in the future")
            return False
        if key in {"observed_at", "verified_at", "reviewed_at"}:
            self.observation_times.append(observed)
        return True

    def evidence(self, value: object, location: str, nonempty: bool = False,
                 case_ids: set[str] | None = None, subject: str | None = None,
                 required_types: set[str] | None = None) -> set[str]:
        start = len(self.errors)
        types = super().evidence(value, location, nonempty=nonempty)
        if not isinstance(value, list):
            return set()
        for index, item in enumerate(value):
            loc = f"{location}[{index}]"
            if not isinstance(item, dict):
                continue
            self.hash_field(item, "sha256", loc)
            self.timestamp(item, "observed_at", loc)
            self.text(item, "summary", loc)
            if case_ids is not None:
                case_id = item.get("case_id")
                if not isinstance(case_id, str) or case_id not in case_ids:
                    self.error(f"{loc}.case_id", "must reference a case covered by this record")
            if subject is not None and item.get("subject") != subject:
                self.error(f"{loc}.subject", f"must be {subject}")
        if required_types and not types & required_types:
            self.error(location, "requires evidence of type " + " or ".join(sorted(required_types)))
        return types if len(self.errors) == start else set()

    def provenance(self, data: dict, scope: dict) -> tuple[dict, list[str]]:
        value = data.get("provenance")
        gaps: list[str] = []
        if not isinstance(value, dict):
            self.error("$.provenance", "must be an object; use null for unobserved stages")
            value = {}
        stages: dict[str, dict] = {}
        for name in ("source", "artifact", "deployment", "runtime"):
            loc = f"$.provenance.{name}"
            record = value.get(name)
            if record is None:
                if name != "deployment" or scope.get("environment") != "local":
                    gaps.append(f"{name} provenance has not been observed.")
                continue
            if not isinstance(record, dict):
                self.error(loc, "must be an object or null")
                continue
            stages[name] = record
            self.actor(record, "recorded_by", loc)
            if name == "source":
                self.hash_field(record, "revision", loc, revision=True)
                required = {"source"}
            elif name == "artifact":
                self.hash_field(record, "sha256", loc)
                self.hash_field(record, "source_revision", loc, revision=True)
                required = {"build"}
            else:
                if not known_identity(record.get("identity")):
                    self.error(f"{loc}.identity", "must be an exact observed identity, not an unknown/branch placeholder")
                self.hash_field(record, "artifact_sha256", loc)
                if name == "runtime":
                    self.hash_field(record, "source_revision", loc, revision=True)
                    if scope.get("environment") != "local":
                        self.text(record, "deployment_identity", loc)
                required = {name}
            self.evidence(record.get("evidence"), f"{loc}.evidence", nonempty=True,
                          subject=name, required_types=required)
        source, artifact = stages.get("source", {}), stages.get("artifact", {})
        runtime, deployment = stages.get("runtime", {}), stages.get("deployment", {})
        if source and artifact and not same_digest(source.get("revision"), artifact.get("source_revision")):
            self.error("$.provenance.artifact.source_revision", "does not match recorded source revision")
        for name, record in (("deployment", deployment), ("runtime", runtime)):
            if artifact and record and not same_digest(artifact.get("sha256"), record.get("artifact_sha256")):
                self.error(f"$.provenance.{name}.artifact_sha256", "does not match the built artifact")
        if source and runtime and not same_digest(source.get("revision"), runtime.get("source_revision")):
            self.error("$.provenance.runtime.source_revision", "does not match recorded source revision")
        if runtime and deployment and runtime.get("deployment_identity") != deployment.get("identity"):
            self.error("$.provenance.runtime.deployment_identity", "does not match the observed deployment")
        if scope.get("environment") != "local" and not deployment:
            gaps.append("A deployed target requires independent deployment and runtime records.")
        review = data.get("release_review")
        if review is None:
            gaps.append("Independent release evidence review has not been recorded.")
        elif not isinstance(review, dict):
            self.error("$.release_review", "must be an object or null")
        else:
            loc = "$.release_review"
            for key in ("reviewer", "executor"):
                self.actor(review, key, loc)
            if same_actor(review.get("reviewer"), review.get("executor")):
                self.error(loc, "reviewer and executor must be distinct actual sessions/people")
            if not same_actor(review.get("executor"), scope.get("audit_actor")):
                self.error(f"{loc}.executor", "must match scope.audit_actor")
            self.timestamp(review, "reviewed_at", loc)
            self.text(review, "summary", loc)
            self.hash_field(review, "source_revision", loc, revision=True)
            self.hash_field(review, "artifact_sha256", loc)
            self.text(review, "runtime_identity", loc)
            self.evidence(review.get("evidence"), f"{loc}.evidence", nonempty=True,
                          subject="release", required_types={"verification"})
            for key, expected in (("source_revision", source.get("revision")),
                                  ("artifact_sha256", artifact.get("sha256")),
                                  ("runtime_identity", runtime.get("identity"))):
                matches = same_digest(review.get(key), expected) if key != "runtime_identity" else review.get(key) == expected
                if expected is not None and not matches:
                    self.error(f"{loc}.{key}", "does not match the observed release provenance")
            runtime_hashes = evidence_digests(runtime.get("evidence"))
            if runtime_hashes and evidence_digests(review.get("evidence")) <= runtime_hashes:
                self.error(f"{loc}.evidence", "must contain independent review evidence, not only the runtime observation again")
            observations = [runtime.get("evidence")]
            rows = data.get("coverage")
            if isinstance(rows, list):
                observations += [row.get("evidence") for row in rows if isinstance(row, dict)]
            latest = latest_evidence_time(observations)
            if latest and timestamp_ok(review.get("reviewed_at")):
                reviewed = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
                if reviewed < latest:
                    self.error(f"{loc}.reviewed_at", "independent review predates the observations it is meant to verify")
        return stages, gaps


    def regression_record(self, regression: object, finding: dict, resolution: dict,
                          loc: str, cases: dict[str, dict], stages: dict) -> tuple[bool, list[str], set[str], set[str], set[str]]:
        gaps: list[str] = []
        before_hashes: set[str] = set()
        after_hashes: set[str] = set()
        review_hashes: set[str] = set()
        if not isinstance(regression, dict):
            self.error(loc, "must reference a shared regression comparison and immutable definitions")
            return False, gaps, before_hashes, after_hashes, review_hashes
        refs = finding.get("coverage_ids")
        finding_ids = set(refs) if isinstance(refs, list) and all(is_text(x) for x in refs) else set()
        reg_ids = regression.get("case_ids")
        valid_ids = self.string_list(reg_ids, f"{loc}.case_ids", nonempty=True)
        selected = set(reg_ids) if valid_ids else set()
        if valid_ids and (len(selected) != len(reg_ids) or not selected <= finding_ids):
            self.error(f"{loc}.case_ids", "must uniquely reference this finding's covered cases")
        supported = valid_ids
        for case_id in selected:
            if cases.get(case_id, {}).get("status") != "passed":
                supported = False
                gaps.append(f"Fixed finding {safe_id(finding.get('id'))} needs a passing current retest for {case_id}.")
        record = regression.get("record")
        before_errors = len(self.errors)
        self.evidence([record], f"{loc}.record", nonempty=True, case_ids=selected, required_types={"test"})
        definitions: dict[str, dict] = {}
        for name in ("test_definition", "oracle_definition", "environment_definition"):
            definition = regression.get(name)
            self.evidence([definition], f"{loc}.{name}", nonempty=True, case_ids=selected, required_types={"source"})
            if isinstance(definition, dict):
                definitions[name] = definition
        if len(self.errors) != before_errors:
            return False, gaps, before_hashes, after_hashes, review_hashes
        try:
            from regression_evidence import check_regression
            _path, comparison = load_ledger(str(self.bundle / record["path"]))
            checked = check_regression(comparison, self.bundle)
        except (ImportError, LedgerError, OSError, ValueError, TypeError, KeyError, RecursionError):
            self.error(f"{loc}.record", "cannot validate the shared regression comparison; inspect its schema, files, and checker availability")
            return False, gaps, before_hashes, after_hashes, review_hashes
        if not checked["accepted"]:
            self.error(f"{loc}.record", "shared regression comparison is not verified: " + ", ".join(checked["reasons"]))
            supported = False
        case_id = comparison.get("case_id")
        if not isinstance(case_id, str) or selected != {case_id}:
            self.error(f"{loc}.case_ids", "must identify the comparison's one primary case; other adjacent cases remain in coverage")
        for key in ("author", "verifier"):
            self.actor(comparison, key, f"{loc}.comparison")
        if not same_actor(comparison.get("verifier"), resolution.get("verifier")):
            self.error(f"{loc}.comparison.verifier", "must match the finding's independent verifier")
        for key in ("buggy_revision", "fixed_revision"):
            self.hash_field(comparison, key, f"{loc}.comparison", revision=True)
        for key, definition_name in (("test_sha256", "test_definition"), ("oracle_sha256", "oracle_definition")):
            if not same_digest(comparison.get(key), definitions[definition_name].get("sha256")):
                self.error(f"{loc}.comparison.{key}", "must match the actual immutable definition file")
        expected_environment = "sha256:" + definitions["environment_definition"]["sha256"].lower()
        if comparison.get("environment_id") != expected_environment:
            self.error(f"{loc}.comparison.environment_id", "must bind the actual environment definition as sha256:<digest>")
        source, artifact = stages.get("source", {}), stages.get("artifact", {})
        if source and not same_digest(comparison.get("fixed_revision"), source.get("revision")):
            gaps.append(f"Fixed finding {safe_id(finding.get('id'))} has not been retested on the current source revision.")
        self.hash_field(comparison, "fixed_artifact_sha256", f"{loc}.comparison")
        if artifact and not same_digest(comparison.get("fixed_artifact_sha256"), artifact.get("sha256")):
            gaps.append(f"Fixed finding {safe_id(finding.get('id'))} has not been retested on the current artifact.")
        before_times: list[datetime] = []
        after_times: list[datetime] = []
        for index, run in enumerate(comparison.get("runs", [])):
            if not isinstance(run, dict):
                continue
            rloc = f"{loc}.comparison.runs[{index}]"
            phase = run.get("phase")
            exit_code = run.get("exit_code")
            if type(exit_code) is not int or (phase == "before" and exit_code <= 0) or (phase == "after" and exit_code != 0):
                self.error(f"{rloc}.exit_code", "must be a positive assertion-failure exit code before and integer zero after")
            self.evidence(run.get("evidence"), f"{rloc}.evidence", nonempty=True,
                          case_ids={case_id} if isinstance(case_id, str) else set(), required_types=EXECUTION_EVIDENCE)
            hashes = evidence_digests(run.get("evidence"))
            observed = latest_evidence_time([run.get("evidence")])
            if phase == "before":
                before_hashes.update(hashes)
                if observed:
                    before_times.append(observed)
            elif phase == "after":
                after_hashes.update(hashes)
                if observed:
                    after_times.append(observed)
                self.hash_field(run, "artifact_sha256", rloc)
                if not same_digest(run.get("artifact_sha256"), comparison.get("fixed_artifact_sha256")):
                    self.error(f"{rloc}.artifact_sha256", "must match the fixed artifact recorded by the comparison")
        if before_times and after_times and max(before_times) > min(after_times):
            self.error(loc, "after executions cannot predate before executions")
        if after_times and timestamp_ok(resolution.get("verified_at")):
            verified = datetime.fromisoformat(resolution["verified_at"].replace("Z", "+00:00"))
            if verified < max(after_times):
                self.error(loc, "independent verification predates the passing executions")
        verification = comparison.get("verification")
        if isinstance(verification, dict):
            review_hashes = evidence_digests([verification])
            try:
                _path, review = load_ledger(str(self.bundle / verification["path"]))
                self.timestamp(review, "reviewed_at", f"{loc}.comparison.verification")
                if timestamp_ok(review.get("reviewed_at")) and timestamp_ok(resolution.get("verified_at")):
                    reviewed = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
                    verified = datetime.fromisoformat(resolution["verified_at"].replace("Z", "+00:00"))
                    if reviewed != verified:
                        self.error(loc, "verified_at must match the actual independent review record")
                    if after_times and reviewed < max(after_times):
                        self.error(loc, "review record predates the passing executions")
            except (LedgerError, OSError, ValueError, TypeError, KeyError, RecursionError):
                self.error(loc, "cannot read the independent regression review")
        return supported, gaps, before_hashes, after_hashes, review_hashes

    def resolution(self, finding: dict, loc: str, cases: dict[str, dict], stages: dict) -> tuple[bool, list[str]]:
        resolution = finding.get("resolution")
        gaps: list[str] = []
        supported = True
        if not isinstance(resolution, dict):
            self.error(f"{loc}.resolution", "must be an object, beginning with state: open")
            return False, gaps
        loc += ".resolution"
        if not self.enum(resolution, "state", {"open", "fixed", "rejected", "accepted_risk", "acknowledged"}, loc):
            return False, gaps
        state = resolution["state"]
        if state == "open":
            return finding.get("kind") == "suggestion", gaps
        refs = finding.get("coverage_ids")
        case_ids = set(refs) if isinstance(refs, list) and all(is_text(x) for x in refs) else set()
        if state == "fixed":
            for key in ("fixer", "verifier"):
                self.actor(resolution, key, loc)
            if same_actor(resolution.get("fixer"), resolution.get("verifier")):
                self.error(loc, "fixer and verifier must be distinct actual sessions/people")
            self.hash_field(resolution, "fixed_revision", loc, revision=True)
            self.timestamp(resolution, "verified_at", loc)
            self.text(resolution, "summary", loc)
            supported, regression_gaps, before_hashes, after_hashes, review_hashes = self.regression_record(
                resolution.get("regression"), finding, resolution, f"{loc}.regression", cases, stages)
            gaps.extend(regression_gaps)
            self.evidence(resolution.get("verification_evidence"), f"{loc}.verification_evidence",
                          nonempty=True, case_ids=case_ids, required_types={"verification"})
            if evidence_digests(resolution.get("verification_evidence")) <= before_hashes | after_hashes:
                self.error(f"{loc}.verification_evidence", "must contain a distinct independent review record")
            if not review_hashes or not review_hashes <= evidence_digests(resolution.get("verification_evidence")):
                self.error(f"{loc}.verification_evidence", "must include the comparison-bound independent regression review")
        else:
            self.actor(resolution, "reviewer", loc)
            self.timestamp(resolution, "reviewed_at", loc)
            self.text(resolution, "reason", loc)
            self.evidence(resolution.get("evidence"), f"{loc}.evidence", nonempty=True,
                          case_ids=case_ids, required_types={"verification"})
            if state == "rejected" and same_actor(resolution.get("reviewer"), finding.get("reported_by")):
                self.error(loc, "rejecting a finding requires a reviewer distinct from its reporter")
            if state == "acknowledged" and finding.get("kind") != "suggestion":
                self.error(loc, "acknowledged is reserved for design/product suggestions, not defects or risks")
            if evidence_digests(resolution.get("evidence")) <= evidence_digests(finding.get("evidence")):
                self.error(f"{loc}.evidence", "must include a distinct review record, not relabeled original finding evidence")
            if state == "accepted_risk":
                if finding.get("severity") not in ("P2", "P3"):
                    self.error(loc, "critical/high findings cannot be accepted as residual risk")
                self.actor(resolution, "owner", loc)
                if self.timestamp(resolution, "expires_at", loc, allow_future=True):
                    expiry = datetime.fromisoformat(resolution["expires_at"].replace("Z", "+00:00"))
                    if expiry <= datetime.now(timezone.utc):
                        supported = False
                        gaps.append(f"Accepted risk {safe_id(finding.get('id'))} has expired.")
        return supported, gaps

    def validate(self, data: dict) -> dict:
        self.scan_urls(data)
        scope = data.get("scope")
        if not isinstance(scope, dict):
            self.error("$.scope", "must be an object")
            scope = {}
        self.text(scope, "id", "$.scope")
        self.text(scope, "audit_actor", "$.scope")
        problem = target_problem(scope.get("target"))
        if problem:
            self.error("$.scope.target", problem)
        self.enum(scope, "profile", {"standard", "advanced"}, "$.scope")
        self.enum(scope, "environment", {"local", "staging", "production"}, "$.scope")
        self.timestamp(scope, "started_at", "$.scope")
        if "build" in scope and scope["build"] is not None and not is_text(scope["build"]):
            self.error("$.scope.build", "must be a build label or null; proof belongs in provenance")
        for key in ("roles", "viewports"):
            if self.string_list(scope.get(key), f"$.scope.{key}"):
                if len(scope[key]) != len(set(scope[key])):
                    self.error(f"$.scope.{key}", "contains duplicate declarations")
        if not isinstance(data.get("capabilities"), dict):
            self.error("$.capabilities", "must be an object; availability is not execution proof")
        exclusions = scope.get("exclusions")
        excluded_ids: set[str] = set()
        if not isinstance(exclusions, list):
            self.error("$.scope.exclusions", "must be a list of explicit case exclusions")
            exclusions = []
        for index, item in enumerate(exclusions):
            loc = f"$.scope.exclusions[{index}]"
            if not isinstance(item, dict):
                self.error(loc, "must be an object with case_id and reason")
                continue
            self.text(item, "reason", loc)
            if self.text(item, "case_id", loc):
                if item["case_id"] in excluded_ids:
                    self.error(f"{loc}.case_id", "duplicates an exclusion")
                excluded_ids.add(item["case_id"])
        coverage = data.get("coverage")
        if not isinstance(coverage, list):
            self.error("$.coverage", "must be a list")
            coverage = []
        cases: dict[str, dict] = {}
        audit_gaps: list[str] = []
        strict_gaps: list[str] = []
        for index, row in enumerate(coverage):
            loc = f"$.coverage[{index}]"
            if not isinstance(row, dict):
                self.error(loc, "must be a coverage object")
                continue
            valid_id = self.identifier(row, loc)
            if valid_id:
                cases[row["id"]] = row
            for key in ("route", "role", "viewport", "state", "expected", "invariant"):
                self.text(row, key, loc)
            for key in ("reason", "actual"):
                self.text(row, key, loc, allow_empty=True)
            self.enum(row, "risk", {"P0", "P1", "P2", "P3"}, loc)
            if type(row.get("required")) is not bool:
                self.error(f"{loc}.required", "must be a boolean")
            self.hash_field(row, "observed_build", loc, nullable=True)
            status_valid = self.enum(row, "status", V2_STATUSES, loc)
            types = self.evidence(row.get("evidence"), f"{loc}.evidence",
                                  case_ids={row["id"]} if valid_id else set())
            status = row.get("status") if status_valid else None
            if status in ("passed", "failed"):
                if not types & EXECUTION_EVIDENCE:
                    self.error(f"{loc}.evidence", "executed cases require runtime, test or log evidence")
                if not is_text(row.get("actual")):
                    self.error(f"{loc}.actual", "executed cases require an observed outcome")
            if status in ("blocked", "unknown", "out_of_scope") and not is_text(row.get("reason")):
                self.error(f"{loc}.reason", "requires an explicit reason")
            if status == "out_of_scope":
                if not valid_id or row["id"] not in excluded_ids:
                    self.error(f"{loc}.status", "must also be declared in scope.exclusions")
                if row.get("required") is True or row.get("risk") in ("P0", "P1"):
                    audit_gaps.append(f"Required/critical case {safe_id(row.get('id'))} cannot be excluded to obtain a passing gate.")
            elif status not in ("passed", "failed"):
                audit_gaps.append(f"Case {safe_id(row.get('id'))} has not reached an observed passed/failed outcome.")
            if status == "failed":
                strict_gaps.append(f"Case {safe_id(row.get('id'))} failed.")
            for singular, plural in (("role", "roles"), ("viewport", "viewports")):
                declared = scope.get(plural)
                if isinstance(declared, list) and declared and row.get(singular) not in declared:
                    self.error(f"{loc}.{singular}", "is not declared in scope")
        for case_id in excluded_ids:
            if cases.get(case_id, {}).get("status") != "out_of_scope":
                self.error("$.scope.exclusions", "each exclusion must reference an out_of_scope coverage case")
        in_scope = [row for row in cases.values() if row.get("status") != "out_of_scope"]
        if not in_scope:
            audit_gaps.append("No in-scope checks are recorded.")
        stages, release_gaps = self.provenance(data, scope)
        findings = data.get("findings")
        if not isinstance(findings, list):
            self.error("$.findings", "must be a list")
            findings = []
        failed_refs: set[str] = set()
        dispositions: Counter = Counter()
        for index, finding in enumerate(findings):
            loc = f"$.findings[{index}]"
            if not isinstance(finding, dict):
                self.error(loc, "must be a finding object")
                continue
            self.identifier(finding, loc)
            for key in ("title", "impact", "expected", "actual"):
                self.text(finding, key, loc)
            self.actor(finding, "reported_by", loc)
            self.enum(finding, "severity", {"P0", "P1", "P2", "P3"}, loc)
            self.enum(finding, "kind", {"defect", "risk", "suggestion"}, loc)
            self.enum(finding, "confidence", {"certain", "likely", "guessing"}, loc)
            self.string_list(finding.get("steps"), f"{loc}.steps", nonempty=finding.get("kind") == "defect")
            refs = finding.get("coverage_ids")
            valid_refs = self.string_list(refs, f"{loc}.coverage_ids", nonempty=True)
            case_ids = set(refs) if valid_refs else set()
            if valid_refs and (len(refs) != len(case_ids) or not case_ids <= cases.keys()):
                self.error(f"{loc}.coverage_ids", "must uniquely reference existing cases")
            types = self.evidence(finding.get("evidence"), f"{loc}.evidence", nonempty=True, case_ids=case_ids)
            if finding.get("kind") == "defect" and not types & EXECUTION_EVIDENCE:
                self.error(f"{loc}.evidence", "a demonstrated defect requires execution evidence")
            if finding.get("kind") in ("defect", "risk"):
                failed_refs.update(case_ids)
            root = finding.get("root_cause")
            if not isinstance(root, dict):
                self.error(f"{loc}.root_cause", "must be an object")
            else:
                self.enum(root, "status", {"unknown", "suspected", "confirmed"}, f"{loc}.root_cause")
                self.text(root, "hypothesis", f"{loc}.root_cause", allow_empty=True)
                self.evidence(root.get("evidence"), f"{loc}.root_cause.evidence", case_ids=case_ids,
                              nonempty=root.get("status") == "confirmed")
            resolved, gaps = self.resolution(finding, loc, cases, stages)
            resolution = finding.get("resolution")
            if isinstance(resolution, dict) and isinstance(resolution.get("state"), str):
                dispositions[resolution["state"]] += 1
            if not resolved:
                strict_gaps.append(f"Finding {safe_id(finding.get('id'))} remains unresolved.")
            release_gaps.extend(gaps)
        for case_id, row in cases.items():
            if row.get("status") == "failed" and case_id not in failed_refs:
                audit_gaps.append(f"Failed case {case_id} needs a linked defect/risk record.")
        artifact = stages.get("artifact", {}).get("sha256")
        for case_id, row in cases.items():
            if row.get("status") == "passed" and (not artifact or not same_digest(row.get("observed_build"), artifact)):
                release_gaps.append(f"Case {case_id} is not tied to the current observed artifact.")
        review = data.get("release_review")
        if isinstance(review, dict) and timestamp_ok(review.get("reviewed_at")) and self.observation_times:
            reviewed_at = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
            if reviewed_at < max(self.observation_times):
                self.error("$.release_review.reviewed_at", "final release review predates finding resolution or other supporting observations")
        if not known_identity(scope.get("audit_actor")):
            release_gaps.append("The actual audit executor has not been identified.")
        counts = Counter(row.get("status") for row in cases.values()
                         if isinstance(row.get("status"), str) and row["status"] in V2_STATUSES)
        counts = {key: counts[key] for key in sorted(V2_STATUSES)}
        strict_errors = audit_gaps + strict_gaps
        release_errors = strict_errors + release_gaps
        valid = not self.errors
        complete = valid and not audit_gaps
        strict = valid and not strict_errors
        release = valid and not release_errors
        outcome = ("invalid_evidence_bundle" if not valid else "recorded_release_eligible" if release else
                   "recorded_checks_passed" if strict else "findings_require_review" if complete else "incomplete")
        self.warnings.append("Digests bind files to records, not to truthful execution or independent authorship. Inspect the evidence contents.")
        return {
            "schema_version": 2,
            "integrity": {"valid": valid, "errors": self.errors, "warnings": self.warnings},
            "gates": {"ledger_valid": valid, "audit_complete": complete, "recorded_checks_passed": strict,
                      "release_accepted": release,
                      "audit_errors": audit_gaps, "strict_errors": strict_errors, "release_errors": release_errors},
            "acceptance": {"outcome": outcome, "strict_gate_passed": strict, "product_accepted": False,
                           "release_eligible": release, "coverage": counts,
                           "covered": counts["passed"] + counts["failed"], "findings": len(findings),
                           "dispositions": dict(dispositions), "errors": release_errors},
            "limits": "Release_accepted means recorded-evidence eligibility for the declared scope only. It does not authenticate evidence, prove complete product coverage, authorize deployment, or certify a bug-free system.",
        }


def evidence_digests(value: object) -> set[str]:
    return {item["sha256"].lower() for item in value if isinstance(item, dict) and isinstance(item.get("sha256"), str)} if isinstance(value, list) else set()


def latest_evidence_time(groups: list) -> datetime | None:
    timestamps = []
    for group in groups:
        if isinstance(group, list):
            timestamps += [datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))
                           for item in group if isinstance(item, dict) and timestamp_ok(item.get("observed_at"))]
    return max(timestamps) if timestamps else None


class Validator:
    """Compatibility dispatch; each validation uses a fresh, isolated accumulator."""
    def __init__(self, bundle: Path):
        self.bundle = bundle

    def validate(self, data: dict) -> dict:
        if type(data.get("schema_version")) is int and data["schema_version"] == 2:
            return V2Validator(self.bundle).validate(data)
        result = LegacyValidator(self.bundle).validate(data)
        counts = result["acceptance"]["coverage"]
        result["gates"] = {
            "ledger_valid": result["integrity"]["valid"],
            "audit_complete": result["integrity"]["valid"] and bool(counts["passed"] + counts["failed"])
                              and not counts["blocked"] and not counts["not_tested"],
            "recorded_checks_passed": result["acceptance"]["strict_gate_passed"],
            "release_accepted": False,
            "release_errors": ["Version 1 records cannot establish release eligibility; start a version 2 bundle and record current evidence."],
        }
        return result


def markdown(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " / ")
    text = "".join(char if ord(char) >= 32 else " " for char in text)
    for character in ("\\", "`", "*", "_", "[", "]", "|", "<", ">"):
        text = text.replace(character, "\\" + character)
    return text


def make_report(data: dict, result: dict) -> str:
    if result["schema_version"] == 2:
        return make_v2_report(data, result)
    integrity = result["integrity"]
    acceptance = result["acceptance"]
    lines = ["# Deep Product Audit", "", f"Generated: {now()}", "",
             "This report describes recorded checks, not certification of the whole product.", "",
             "## Result", "", f"- Data integrity: {'valid' if integrity['valid'] else 'INVALID'}.",
             f"- Recorded outcome: {acceptance['outcome']}.",
             "- Product or release acceptance: not established by this tool."]
    if not integrity["valid"]:
        lines += ["", "## Integrity errors", ""]
        lines += [f"- {markdown(error)}" for error in integrity["errors"]]
        lines += ["", "Original ledger content is omitted until integrity errors are corrected.", ""]
        return "\n".join(lines)
    scope = data["scope"]
    counts = acceptance["coverage"]
    lines += ["", "## Scope", "", f"- Audit: {markdown(scope['id'])}",
              f"- Target: {markdown(scope['target'])}",
              f"- Environment/profile: {scope['environment']} / {scope['profile']}",
              f"- Build: {markdown(scope['build'] or 'not recorded')}",
              f"- Started: {markdown(scope['started_at'])}", "", "## Coverage", "",
              f"Covered: **{acceptance['covered']}** (passed {counts['passed']}, failed {counts['failed']}). "
              f"Blocked: **{counts['blocked']}**. Untested: **{counts['not_tested']}**. "
              f"Out of scope: **{counts['out_of_scope']}**.", "",
              "| ID | Route | Role / viewport | State | Status | Reason |",
              "| --- | --- | --- | --- | --- | --- |"]
    for row in data["coverage"]:
        lines.append("| " + " | ".join(markdown(item) for item in (
            row["id"], row["route"], f"{row['role']} / {row['viewport']}", row["state"], row["status"], row["reason"])) + " |")
    if not data["coverage"]:
        lines.append("| — | No coverage recorded | — | — | not_tested | Audit has not run |")
    if acceptance["errors"]:
        lines += ["", "## Acceptance gaps", ""]
        lines += [f"- {markdown(error)}" for error in acceptance["errors"]]
        lines += ["", "The audit cannot be declared complete or accepted from this ledger."]
    else:
        lines += ["", "All recorded in-scope checks passed. Coverage adequacy and release acceptance remain separate decisions."]
    if integrity["warnings"]:
        lines += ["", "## Evidence limits", ""]
        lines += [f"- {markdown(warning)}" for warning in integrity["warnings"]]
    lines += ["", f"## Findings ({len(data['findings'])})", ""]
    if not data["findings"]:
        lines.append("No findings are recorded; this is not proof that the product has no defects.")
    for finding in data["findings"]:
        lines += [f"### {markdown(finding['id'])}: {markdown(finding['title'])}", "",
                  f"- Severity/kind/confidence: {finding['severity']} / {finding['kind']} / {finding['confidence']}",
                  f"- Impact: {markdown(finding['impact'])}",
                  f"- Expected: {markdown(finding['expected'])}",
                  f"- Actual: {markdown(finding['actual'])}",
                  f"- Fix status (reported): {markdown(finding['fix_status'])}",
                  f"- Coverage IDs: {markdown(', '.join(finding['coverage_ids']) or 'none')}",
                  f"- Root cause (reported {markdown(finding['root_cause']['status'])}): "
                  f"{markdown(finding['root_cause']['hypothesis'] or 'not established')}", "", "Reproduction:", ""]
        lines += [f"{index}. {markdown(step)}" for index, step in enumerate(finding["steps"], 1)] or ["No executable reproduction steps recorded."]
        lines += ["", "Evidence:", ""]
        lines += [f"- {item['type']}: {markdown(item['path'])}" for item in finding["evidence"]]
        if finding["root_cause"]["evidence"]:
            lines += ["", "Root-cause evidence:", ""]
            lines += [f"- {item['type']}: {markdown(item['path'])}"
                      for item in finding["root_cause"]["evidence"]]
        lines.append("")
    lines += ["", "## Coverage evidence", ""]
    for row in data["coverage"]:
        lines.append(f"- {markdown(row['id'])}: " + ("; ".join(
            f"{item['type']} — {markdown(item['path'])}" for item in row["evidence"]) or "none"))
    lines += ["", result["limits"], ""]
    return "\n".join(lines)


def make_v2_report(data: dict, result: dict) -> str:
    gates = result["gates"]
    lines = ["# Deep Product Audit", "", f"Generated: {now()}", "",
             "This report covers recorded evidence and the declared scope; it is not a product certification.",
             "", "## Gates", "",
             "| Gate | Result |", "| --- | --- |"]
    for key in ("ledger_valid", "audit_complete", "recorded_checks_passed", "release_accepted"):
        lines.append(f"| {key} | {'PASS' if gates[key] else 'NOT ESTABLISHED'} |")
    lines += ["", "Release acceptance here means eligibility of the recorded evidence, not deployment authorization."]
    if not result["integrity"]["valid"]:
        lines += ["", "## Integrity errors", ""]
        lines += [f"- {markdown(error)}" for error in result["integrity"]["errors"]]
        lines += ["", "Original ledger content is omitted until integrity errors are corrected.", ""]
        return "\n".join(lines)
    scope = data["scope"]
    target = scope["target"]
    lines += ["", "## Scope", "", f"- Audit: {markdown(scope['id'])}",
              f"- Target: {target['kind']} / {markdown(target['locator'])}",
              f"- Platform: {markdown(target.get('platform', 'not applicable'))}",
              f"- Environment/profile: {scope['environment']} / {scope['profile']}",
              f"- Audit executor: {markdown(scope['audit_actor'])}",
              f"- Started: {markdown(scope['started_at'])}", "", "## Recorded provenance", "",
              "| Stage | Identity |", "| --- | --- |"]
    for stage in ("source", "artifact", "deployment", "runtime"):
        value = data["provenance"].get(stage)
        identity = (value.get("revision") or value.get("sha256") or value.get("identity")) if value else "not observed"
        lines.append(f"| {stage} | {markdown(identity)} |")
    lines += ["", "## Coverage", "", "| ID | Invariant | Route / role / viewport | Risk | Status | Reason |",
              "| --- | --- | --- | --- | --- | --- |"]
    for row in data["coverage"]:
        lines.append("| " + " | ".join(markdown(value) for value in (
            row["id"], row["invariant"], f"{row['route']} / {row['role']} / {row['viewport']}",
            row["risk"], row["status"], row["reason"])) + " |")
    if not data["coverage"]:
        lines.append("| — | No checks recorded | — | — | not_tested | — |")
    for label, key in (("Audit gaps", "audit_errors"), ("Release gaps", "release_errors")):
        if gates[key]:
            lines += ["", f"## {label}", ""]
            lines += [f"- {markdown(gap)}" for gap in gates[key]]
    lines += ["", "## Findings and retained history", ""]
    if not data["findings"]:
        lines.append("No findings are recorded; this is not proof that no defects exist.")
    for finding in data["findings"]:
        resolution = finding["resolution"]
        lines += [f"### {markdown(finding['id'])}: {markdown(finding['title'])}", "",
                  f"- Severity/kind/confidence: {finding['severity']} / {finding['kind']} / {finding['confidence']}",
                  f"- Impact: {markdown(finding['impact'])}",
                  f"- Expected: {markdown(finding['expected'])}",
                  f"- Original observation: {markdown(finding['actual'])}",
                  f"- Disposition: {resolution['state']}",
                  f"- Covered cases: {markdown(', '.join(finding['coverage_ids']))}"]
        if resolution["state"] == "fixed":
            lines += [f"- Fixed revision: {markdown(resolution['fixed_revision'])}",
                      f"- Fixer/verifier: {markdown(resolution['fixer'])} / {markdown(resolution['verifier'])}",
                      f"- Verification: {markdown(resolution['summary'])}"]
        elif resolution["state"] != "open":
            lines.append(f"- Disposition reason: {markdown(resolution['reason'])}")
        lines += ["", "Reproduction:", ""]
        lines += [f"{i}. {markdown(step)}" for i, step in enumerate(finding["steps"], 1)]
        lines += ["", "Original evidence:", ""]
        lines += [f"- {item['type']}: {markdown(item['path'])} ({markdown(item['sha256'])})"
                  for item in finding["evidence"]]
        lines.append("")
    lines += ["", "## Evidence limits", "", result["limits"], ""]
    lines += [f"- {markdown(warning)}" for warning in result["integrity"]["warnings"]]
    lines.append("")
    return "\n".join(lines)


def create_evidence_record(bundle: Path, args: argparse.Namespace) -> dict:
    if not bundle.is_dir():
        raise LedgerError("Evidence bundle must be an existing directory.")
    item = {"path": args.path, "type": args.type, "observed_at": args.observed_at, "summary": args.summary}
    validator = V2Validator(bundle)
    LegacyValidator.evidence(validator, [item], "evidence", nonempty=True)
    if validator.errors:
        raise LedgerError("; ".join(validator.errors))
    candidate = (bundle / args.path).resolve(strict=True)
    hasher = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    item["sha256"] = hasher.hexdigest()
    if args.case_id:
        if not IDENTIFIER.fullmatch(args.case_id):
            raise LedgerError("Evidence case ID is not a valid identifier.")
        item["case_id"] = args.case_id
    else:
        item["subject"] = args.subject
    validator.evidence([item], "evidence", nonempty=True,
                       case_ids={args.case_id} if args.case_id else None, subject=args.subject)
    if validator.errors:
        raise LedgerError("; ".join(validator.errors))
    return item


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create a new, empty audit bundle; output directory must not exist")
    init.add_argument("--out", required=True)
    init.add_argument("--target", required=True)
    init.add_argument("--target-kind", choices=sorted(TARGET_KINDS), default="web")
    init.add_argument("--platform", help="native: macos/windows/linux; mobile: ios/android")
    init.add_argument("--schema-version", type=int, choices=(1, 2), default=2)
    init.add_argument("--audit-actor", default="unassigned", help="actual coordinator/session identity; required before release eligibility")
    init.add_argument("--profile", choices=("standard", "advanced"), default="standard")
    init.add_argument("--environment", choices=("local", "staging", "production"), default="local")
    validate = commands.add_parser("validate", help="validate audit.json or a bundle directory")
    validate.add_argument("path")
    mode = validate.add_mutually_exclusive_group()
    mode.add_argument("--strict", action="store_true", help="require all recorded in-scope checks pass and supported finding dispositions")
    mode.add_argument("--gate", choices=("ledger", "audit", "release"), default="ledger",
                      help="select integrity, investigation completeness, or recorded release eligibility")
    report = commands.add_parser("report", help="render a technical Markdown report")
    report.add_argument("path")
    report.add_argument("--out", help="write a new file instead of stdout; existing files are never overwritten")
    evidence = commands.add_parser("evidence", help="hash one existing evidence file and print metadata; does not claim a test ran")
    evidence.add_argument("--bundle", required=True)
    evidence.add_argument("--path", required=True, help="relative POSIX path inside the bundle")
    evidence.add_argument("--type", required=True, choices=sorted(V2_EVIDENCE_TYPES))
    evidence.add_argument("--observed-at", required=True, help="actual observation time, ISO 8601 with timezone")
    evidence.add_argument("--summary", required=True)
    identity = evidence.add_mutually_exclusive_group(required=True)
    identity.add_argument("--case-id")
    identity.add_argument("--subject", choices=("source", "artifact", "deployment", "runtime", "release"))
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            target = {"kind": args.target_kind, "locator": args.target}
            if args.platform:
                target["platform"] = args.platform
            problem = target_problem(target)
            if problem:
                raise LedgerError("Target " + problem + ".")
            if args.schema_version == 1 and args.target_kind != "web":
                raise LedgerError("Version 1 supports web URL targets only; use schema version 2.")
            output = Path(args.out).expanduser()
            data = {"schema_version": args.schema_version,
                    "scope": {"id": "audit-" + uuid.uuid4().hex[:12], "target": args.target if args.schema_version == 1 else target,
                              "environment": args.environment, "profile": args.profile,
                              "started_at": now(), "build": None, "roles": [], "viewports": []},
                    "capabilities": {}, "coverage": [], "findings": []}
            if args.schema_version == 2:
                data["scope"].update({"audit_actor": args.audit_actor, "exclusions": []})
                data["provenance"] = {stage: None for stage in ("source", "artifact", "deployment", "runtime")}
                data["release_review"] = None
            output.mkdir(parents=True, exist_ok=False)
            ledger = output / "audit.json"
            with ledger.open("x", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
                handle.write("\n")
            print(json.dumps({"created": str(ledger.resolve()), "audit_executed": False}))
            return 0
        if args.command == "evidence":
            print(json.dumps(create_evidence_record(Path(args.bundle).expanduser().resolve(), args),
                             indent=2, ensure_ascii=False, allow_nan=False))
            return 0
        ledger, data = load_ledger(args.path)
        result = Validator(ledger.parent).validate(data)
        if args.command == "validate":
            result["mode"] = "strict" if args.strict else args.gate
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            passed = (result["acceptance"]["strict_gate_passed"] if args.strict else
                      result["gates"][{"ledger": "ledger_valid", "audit": "audit_complete", "release": "release_accepted"}[args.gate]])
            return 0 if passed else 1
        rendered = make_report(data, result)
        if args.out:
            with Path(args.out).expanduser().open("x", encoding="utf-8") as handle:
                handle.write(rendered)
            print(json.dumps({"report": str(Path(args.out).expanduser().resolve()),
                              "integrity_valid": result["integrity"]["valid"],
                              "outcome": result["acceptance"]["outcome"]}))
        else:
            print(rendered, end="")
        return 0 if result["integrity"]["valid"] else 1
    except (LedgerError, OSError, RuntimeError, RecursionError) as exc:
        message = str(exc) if isinstance(exc, LedgerError) else "File operation failed; verify paths and permissions. Existing files are not overwritten."
        print(json.dumps({"error": message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
