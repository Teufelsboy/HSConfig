from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Protocol


MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_API_BYTES = 4 * 1024 * 1024
API_TIMEOUT_SECONDS = 120
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SNAPSHOT_KEYS = frozenset(
    {
        "schema_version",
        "repository",
        "topics",
        "actions_permissions",
        "selected_actions",
        "vulnerability_alerts",
        "private_vulnerability_reporting",
        "automated_security_fixes",
        "rulesets",
        "collaborators",
        "community_profile",
    }
)
REPOSITORY_FIELDS = (
    "visibility",
    "description",
    "homepage",
    "has_issues",
    "has_projects",
    "has_wiki",
    "has_discussions",
    "allow_squash_merge",
    "allow_merge_commit",
    "allow_rebase_merge",
    "allow_auto_merge",
    "delete_branch_on_merge",
    "web_commit_signoff_required",
    "security_and_analysis",
)
DESIRED_REPOSITORY = {
    "description": (
        "Deterministic pre-run HearthRanger VisionAI CustomConfig generator "
        "with audited contracts."
    ),
    "has_issues": True,
    "has_projects": False,
    "has_wiki": False,
    "has_discussions": False,
    "allow_squash_merge": True,
    "allow_merge_commit": False,
    "allow_rebase_merge": False,
    "allow_auto_merge": False,
    "delete_branch_on_merge": True,
    "web_commit_signoff_required": False,
    "security_and_analysis": {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
    },
}
DESIRED_TOPICS = [
    "configuration",
    "hearthranger",
    "hearthstone",
    "python",
    "visionai",
]
DESIRED_ACTIONS = {"enabled": True, "allowed_actions": "selected"}
DESIRED_SELECTED_ACTIONS = {
    "github_owned_allowed": True,
    "verified_allowed": False,
    "patterns_allowed": [],
}
RULESET_TEMPLATE = {
    "name": "main-linear-signed",
    "target": "branch",
    "enforcement": "disabled",
    "bypass_actors": [],
    "conditions": {
        "ref_name": {"include": ["refs/heads/main"], "exclude": []},
    },
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "required_linear_history"},
        {"type": "required_signatures"},
    ],
}


class GovernanceError(RuntimeError):
    """A closed governance contract was not satisfied."""


class Transport(Protocol):
    def request(
        self, method: str, endpoint: str, payload: object | None = None
    ) -> object: ...


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise GovernanceError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GovernanceError("state_not_canonical_json") from exc


def _parse_json(raw: str, context: str) -> object:
    try:
        return json.loads(raw, object_pairs_hook=_closed_object)
    except GovernanceError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise GovernanceError(f"{context}_invalid_json") from exc


def _read_bounded(path: Path) -> bytes:
    try:
        metadata = path.lstat()
        if not path.is_file() or path.is_symlink() or metadata.st_size > MAX_STATE_BYTES:
            raise GovernanceError("state_file_unsafe")
        data = path.read_bytes()
        if len(data) != metadata.st_size:
            raise GovernanceError("state_file_identity_changed")
        return data
    except GovernanceError:
        raise
    except OSError as exc:
        raise GovernanceError("state_file_unreadable") from exc


def write_state(path: Path, payload: Mapping[str, object]) -> None:
    canonical = canonical_json(dict(payload))
    envelope = {
        "payload": canonical,
        "payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "schema_version": 1,
    }
    destination = path.resolve(strict=False)
    destination.parent.mkdir(parents=False, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical_json(envelope))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def load_state(path: Path) -> dict[str, object]:
    raw = _read_bounded(path)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise GovernanceError("state_invalid_utf8") from exc
    parsed = _parse_json(text, "state_envelope")
    if not isinstance(parsed, dict) or set(parsed) != {
        "payload",
        "payload_sha256",
        "schema_version",
    }:
        raise GovernanceError("state_envelope_schema_mismatch")
    if parsed["schema_version"] != 1:
        raise GovernanceError("state_envelope_version_mismatch")
    payload_text = parsed["payload"]
    digest = parsed["payload_sha256"]
    if not isinstance(payload_text, str) or not isinstance(digest, str):
        raise GovernanceError("state_envelope_type_mismatch")
    actual = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    if not _constant_time_equal(actual, digest):
        raise GovernanceError("state_digest_mismatch")
    payload = _parse_json(payload_text, "state_payload")
    if not isinstance(payload, dict):
        raise GovernanceError("state_payload_schema_mismatch")
    if canonical_json(payload) != payload_text:
        raise GovernanceError("state_payload_not_canonical")
    return payload


def _constant_time_equal(left: str, right: str) -> bool:
    return len(left) == len(right) and hashlib.sha256(left.encode()).digest() == hashlib.sha256(
        right.encode()
    ).digest()


def _repository(repository: str) -> str:
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise GovernanceError("repository_invalid")
    return f"repos/{repository}"


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GovernanceError(f"{context}_schema_mismatch")
    return dict(value)


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise GovernanceError(f"{context}_schema_mismatch")
    return list(value)


def _enabled(value: object, context: str) -> bool:
    row = _mapping(value, context)
    enabled = row.get("enabled")
    if not isinstance(enabled, bool):
        raise GovernanceError(f"{context}_schema_mismatch")
    return enabled


class GhTransport:
    def __init__(self, gh_path: str = "gh") -> None:
        self._gh_path = gh_path

    def request(self, method: str, endpoint: str, payload: object | None = None) -> object:
        arguments = [
            self._gh_path,
            "api",
            "--method",
            method,
            endpoint,
            "--header",
            "Accept: application/vnd.github+json",
            "--header",
            "X-GitHub-Api-Version: 2022-11-28",
        ]
        input_bytes: bytes | None = None
        if payload is not None:
            arguments.extend(["--input", "-"])
            input_bytes = canonical_json(payload).encode("utf-8")
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "APPDATA",
                "PATH",
                "LOCALAPPDATA",
                "PATHEXT",
                "SYSTEMROOT",
                "WINDIR",
                "COMSPEC",
                "TEMP",
                "TMP",
                "GH_CONFIG_DIR",
                "GH_HOST",
                "GH_TOKEN",
                "GITHUB_TOKEN",
                "HOME",
                "USERPROFILE",
            }
        }
        try:
            completed = subprocess.run(
                arguments,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=API_TIMEOUT_SECONDS,
                check=False,
                shell=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GovernanceError(f"native_command_failed:{self._gh_path}") from exc
        if completed.returncode != 0:
            if (
                method == "GET"
                and endpoint.endswith("/vulnerability-alerts")
                and b"HTTP 404" in completed.stderr
            ):
                return {"enabled": False}
            raise GovernanceError(
                f"native_command_failed:{self._gh_path}:exit={completed.returncode}"
            )
        if len(completed.stdout) > MAX_API_BYTES:
            raise GovernanceError("github_api_response_too_large")
        if not completed.stdout.strip():
            if endpoint.endswith(
                ("/vulnerability-alerts", "/automated-security-fixes")
            ) and method == "GET":
                return {"enabled": True}
            return {}
        try:
            return _parse_json(completed.stdout.decode("utf-8"), "github_api_response")
        except UnicodeError as exc:
            raise GovernanceError("github_api_response_invalid_utf8") from exc


def _ruleset_inventory(base: str, transport: Transport) -> list[object]:
    rows = _list(transport.request("GET", f"{base}/rulesets"), "rulesets")
    result: list[object] = []
    for value in rows:
        row = _mapping(value, "ruleset")
        rule_id = row.get("id")
        if not isinstance(rule_id, int) or rule_id <= 0:
            raise GovernanceError("ruleset_id_invalid")
        if "rules" not in row or "conditions" not in row:
            row = _mapping(
                transport.request("GET", f"{base}/rulesets/{rule_id}"), "ruleset"
            )
        result.append(row)
    return result


def _repository_snapshot(value: object) -> dict[str, object]:
    source = _mapping(value, "repository")
    return {field: source.get(field) for field in REPOSITORY_FIELDS}


def capture_snapshot(repository: str, transport: Transport) -> dict[str, object]:
    base = _repository(repository)
    actions_permissions = _mapping(
        transport.request("GET", f"{base}/actions/permissions"),
        "actions_permissions",
    )
    selected_actions = (
        _mapping(
            transport.request("GET", f"{base}/actions/permissions/selected-actions"),
            "selected_actions",
        )
        if actions_permissions.get("allowed_actions") == "selected"
        else {}
    )
    return {
        "schema_version": 1,
        "repository": _repository_snapshot(transport.request("GET", base)),
        "topics": _mapping(transport.request("GET", f"{base}/topics"), "topics"),
        "actions_permissions": actions_permissions,
        "selected_actions": selected_actions,
        "vulnerability_alerts": {
            "enabled": _enabled(
                transport.request("GET", f"{base}/vulnerability-alerts"),
                "vulnerability_alerts",
            )
        },
        "private_vulnerability_reporting": {
            "enabled": _enabled(
                transport.request("GET", f"{base}/private-vulnerability-reporting"),
                "private_vulnerability_reporting",
            )
        },
        "automated_security_fixes": {
            "enabled": _enabled(
                transport.request("GET", f"{base}/automated-security-fixes"),
                "automated_security_fixes",
            )
        },
        "rulesets": _ruleset_inventory(base, transport),
        "collaborators": _list(
            transport.request("GET", f"{base}/collaborators?affiliation=direct"),
            "collaborators",
        ),
        "community_profile": _mapping(
            transport.request("GET", f"{base}/community/profile"),
            "community_profile",
        ),
    }


def _validate_snapshot(snapshot: Mapping[str, object]) -> None:
    if set(snapshot) != SNAPSHOT_KEYS or snapshot.get("schema_version") != 1:
        raise GovernanceError("snapshot_schema_mismatch")
    _mapping(snapshot["repository"], "snapshot_repository")
    _mapping(snapshot["topics"], "snapshot_topics")
    _mapping(snapshot["actions_permissions"], "snapshot_actions_permissions")
    _mapping(snapshot["selected_actions"], "snapshot_selected_actions")
    _enabled(snapshot["vulnerability_alerts"], "snapshot_vulnerability_alerts")
    _enabled(
        snapshot["private_vulnerability_reporting"],
        "snapshot_private_vulnerability_reporting",
    )
    _enabled(
        snapshot["automated_security_fixes"], "snapshot_automated_security_fixes"
    )
    _list(snapshot["rulesets"], "snapshot_rulesets")
    _list(snapshot["collaborators"], "snapshot_collaborators")
    _mapping(snapshot["community_profile"], "snapshot_community_profile")


def _assert_safe_collaborators(rows: object) -> None:
    for value in _list(rows, "collaborators"):
        row = _mapping(value, "collaborator")
        login = row.get("login")
        permissions = _mapping(row.get("permissions"), "collaborator_permissions")
        can_write = any(permissions.get(name) is True for name in ("push", "maintain", "admin"))
        if can_write and login != "Teufelsboy":
            raise GovernanceError(f"unexpected_write_collaborator:{login}")


def _set_boolean_feature(
    base: str, feature: str, enabled: bool, transport: Transport
) -> None:
    transport.request("PUT" if enabled else "DELETE", f"{base}/{feature}")


def _assert_subset(actual: Mapping[str, object], expected: Mapping[str, object], context: str) -> None:
    for key, value in expected.items():
        current = actual.get(key)
        if isinstance(value, Mapping) and isinstance(current, Mapping):
            _assert_subset(current, value, f"{context}:{key}")
        elif current != value:
            raise GovernanceError(f"{context}_mismatch:{key}")


def _find_ruleset(rows: object, rule_id: int) -> dict[str, object]:
    for value in _list(rows, "rulesets"):
        row = _mapping(value, "ruleset")
        if row.get("id") == rule_id:
            return row
    raise GovernanceError("cutover_ruleset_missing")


def ensure_preflight(
    repository: str, snapshot: Mapping[str, object], transport: Transport
) -> dict[str, object]:
    _validate_snapshot(snapshot)
    base = _repository(repository)
    _assert_safe_collaborators(
        transport.request("GET", f"{base}/collaborators?affiliation=direct")
    )
    transport.request("PATCH", base, DESIRED_REPOSITORY)
    transport.request("PUT", f"{base}/topics", {"names": DESIRED_TOPICS})
    _set_boolean_feature(base, "vulnerability-alerts", True, transport)
    _set_boolean_feature(base, "private-vulnerability-reporting", True, transport)
    _set_boolean_feature(base, "automated-security-fixes", False, transport)
    transport.request("PUT", f"{base}/actions/permissions", DESIRED_ACTIONS)
    transport.request(
        "PUT",
        f"{base}/actions/permissions/selected-actions",
        DESIRED_SELECTED_ACTIONS,
    )
    current = _ruleset_inventory(base, transport)
    snapshot_ids = {
        row.get("id")
        for row in (_mapping(item, "snapshot_ruleset") for item in _list(snapshot["rulesets"], "snapshot_rulesets"))
    }
    created = [
        row
        for row in current
        if row.get("name") == RULESET_TEMPLATE["name"] and row.get("id") not in snapshot_ids
    ]
    if len(created) > 1:
        raise GovernanceError("duplicate_cutover_ruleset")
    if created:
        ruleset = created[0]
    else:
        ruleset = _mapping(
            transport.request("POST", f"{base}/rulesets", RULESET_TEMPLATE),
            "created_ruleset",
        )
    rule_id = ruleset.get("id")
    if not isinstance(rule_id, int) or rule_id <= 0:
        raise GovernanceError("created_ruleset_id_invalid")
    verify_preflight(repository, snapshot, rule_id, transport)
    return {"passed": True, "ruleset_id": rule_id}


def verify_preflight(
    repository: str,
    snapshot: Mapping[str, object],
    ruleset_id: int,
    transport: Transport,
) -> dict[str, object]:
    _validate_snapshot(snapshot)
    base = _repository(repository)
    repository_state = _repository_snapshot(transport.request("GET", base))
    _assert_subset(repository_state, DESIRED_REPOSITORY, "repository")
    if transport.request("GET", f"{base}/topics") != {"names": DESIRED_TOPICS}:
        raise GovernanceError("topics_mismatch")
    _assert_subset(
        _mapping(
            transport.request("GET", f"{base}/actions/permissions"),
            "actions_permissions",
        ),
        DESIRED_ACTIONS,
        "actions_permissions",
    )
    _assert_subset(
        _mapping(
            transport.request("GET", f"{base}/actions/permissions/selected-actions"),
            "selected_actions",
        ),
        DESIRED_SELECTED_ACTIONS,
        "selected_actions",
    )
    if not _enabled(
        transport.request("GET", f"{base}/vulnerability-alerts"),
        "vulnerability_alerts",
    ):
        raise GovernanceError("vulnerability_alerts_disabled")
    if not _enabled(
        transport.request("GET", f"{base}/private-vulnerability-reporting"),
        "private_vulnerability_reporting",
    ):
        raise GovernanceError("private_vulnerability_reporting_disabled")
    if _enabled(
        transport.request("GET", f"{base}/automated-security-fixes"),
        "automated_security_fixes",
    ):
        raise GovernanceError("automated_security_fixes_enabled")
    _assert_safe_collaborators(
        transport.request("GET", f"{base}/collaborators?affiliation=direct")
    )
    rule = _find_ruleset(_ruleset_inventory(base, transport), ruleset_id)
    expected_rule = dict(RULESET_TEMPLATE)
    _assert_subset(rule, expected_rule, "inactive_ruleset")
    return {"passed": True, "ruleset_id": ruleset_id}


def activate_ruleset(
    repository: str,
    snapshot: Mapping[str, object],
    ruleset_id: int,
    transport: Transport,
) -> dict[str, object]:
    verify_preflight(repository, snapshot, ruleset_id, transport)
    base = _repository(repository)
    payload = dict(RULESET_TEMPLATE)
    payload["enforcement"] = "active"
    transport.request("PUT", f"{base}/rulesets/{ruleset_id}", payload)
    rule = _find_ruleset(_ruleset_inventory(base, transport), ruleset_id)
    _assert_subset(rule, payload, "active_ruleset")
    return rule


def restore_snapshot(
    repository: str, snapshot: Mapping[str, object], transport: Transport
) -> dict[str, object]:
    _validate_snapshot(snapshot)
    base = _repository(repository)
    failures: list[str] = []
    snapshot_rules = [
        _mapping(row, "snapshot_ruleset")
        for row in _list(snapshot["rulesets"], "snapshot_rulesets")
    ]
    snapshot_ids = {row.get("id") for row in snapshot_rules}
    try:
        current_rules = _ruleset_inventory(base, transport)
    except GovernanceError as exc:
        current_rules = []
        failures.append(str(exc))
    for row in reversed(current_rules):
        rule_id = row.get("id")
        if isinstance(rule_id, int) and rule_id not in snapshot_ids:
            try:
                transport.request("DELETE", f"{base}/rulesets/{rule_id}")
            except Exception as exc:  # compensation must continue
                failures.append(f"delete_ruleset:{type(exc).__name__}")
    for row in reversed(snapshot_rules):
        rule_id = row.get("id")
        if isinstance(rule_id, int):
            payload = {key: value for key, value in row.items() if key not in {"id", "node_id", "source", "_links"}}
            try:
                transport.request("PUT", f"{base}/rulesets/{rule_id}", payload)
            except Exception as exc:  # compensation must continue
                failures.append(f"restore_ruleset:{type(exc).__name__}")
    actions_permissions = _mapping(
        snapshot["actions_permissions"], "snapshot_actions_permissions"
    )
    operations: list[tuple[str, Any]] = []
    if actions_permissions.get("allowed_actions") == "selected":
        operations.append(
            (
                "selected_actions",
                lambda: transport.request(
                    "PUT",
                    f"{base}/actions/permissions/selected-actions",
                    snapshot["selected_actions"],
                ),
            )
        )
    operations.extend([
        ("actions_permissions", lambda: transport.request("PUT", f"{base}/actions/permissions", actions_permissions)),
        ("automated_security_fixes", lambda: _set_boolean_feature(base, "automated-security-fixes", _enabled(snapshot["automated_security_fixes"], "snapshot_automated_security_fixes"), transport)),
        ("private_vulnerability_reporting", lambda: _set_boolean_feature(base, "private-vulnerability-reporting", _enabled(snapshot["private_vulnerability_reporting"], "snapshot_private_vulnerability_reporting"), transport)),
        ("vulnerability_alerts", lambda: _set_boolean_feature(base, "vulnerability-alerts", _enabled(snapshot["vulnerability_alerts"], "snapshot_vulnerability_alerts"), transport)),
        ("topics", lambda: transport.request("PUT", f"{base}/topics", snapshot["topics"])),
        ("repository", lambda: transport.request("PATCH", base, snapshot["repository"])),
    ])
    for name, operation in operations:
        try:
            operation()
        except Exception as exc:  # compensation must continue
            failures.append(f"{name}:{type(exc).__name__}")
    try:
        verify_snapshot(repository, snapshot, transport)
    except GovernanceError as exc:
        failures.append(str(exc))
    if failures:
        raise GovernanceError("snapshot_restore_incomplete:" + ",".join(failures))
    return {"passed": True}


def verify_snapshot(
    repository: str, snapshot: Mapping[str, object], transport: Transport
) -> dict[str, object]:
    _validate_snapshot(snapshot)
    current = capture_snapshot(repository, transport)
    if canonical_json(current) != canonical_json(dict(snapshot)):
        raise GovernanceError("github_snapshot_parity_mismatch")
    return {"passed": True}


def verify_final(repository: str, ruleset_id: int, transport: Transport) -> dict[str, object]:
    base = _repository(repository)
    repository_state = _repository_snapshot(transport.request("GET", base))
    _assert_subset(repository_state, DESIRED_REPOSITORY, "repository")
    if repository_state.get("visibility") != "public":
        raise GovernanceError("repository_not_public")
    topics = transport.request("GET", f"{base}/topics")
    if topics != {"names": DESIRED_TOPICS}:
        raise GovernanceError("topics_mismatch")
    _assert_subset(
        _mapping(
            transport.request("GET", f"{base}/actions/permissions"),
            "actions_permissions",
        ),
        DESIRED_ACTIONS,
        "actions_permissions",
    )
    _assert_subset(
        _mapping(
            transport.request("GET", f"{base}/actions/permissions/selected-actions"),
            "selected_actions",
        ),
        DESIRED_SELECTED_ACTIONS,
        "selected_actions",
    )
    for endpoint, context in (
        ("vulnerability-alerts", "vulnerability_alerts"),
        ("private-vulnerability-reporting", "private_vulnerability_reporting"),
    ):
        if not _enabled(transport.request("GET", f"{base}/{endpoint}"), context):
            raise GovernanceError(f"{context}_disabled")
    if _enabled(
        transport.request("GET", f"{base}/automated-security-fixes"),
        "automated_security_fixes",
    ):
        raise GovernanceError("automated_security_fixes_enabled")
    _assert_safe_collaborators(
        transport.request("GET", f"{base}/collaborators?affiliation=direct")
    )
    rule = _find_ruleset(_ruleset_inventory(base, transport), ruleset_id)
    expected_rule = dict(RULESET_TEMPLATE)
    expected_rule["enforcement"] = "active"
    _assert_subset(rule, expected_rule, "active_ruleset")
    profile = _mapping(
        transport.request("GET", f"{base}/community/profile"), "community_profile"
    )
    documentation = profile.get("documentation")
    if documentation is not None and (
        not isinstance(documentation, str) or "/tree/main/" not in documentation
    ):
        raise GovernanceError("community_profile_main_mismatch")
    return {"passed": True, "ruleset_id": ruleset_id}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage verified HSConfig GitHub governance.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "snapshot",
        "preflight",
        "verify-preflight",
        "restore",
        "verify-snapshot",
        "activate",
        "verify-final",
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--repo", required=True)
        child.add_argument("--json", action="store_true")
        if command == "snapshot":
            child.add_argument("--out", required=True, type=Path)
        if command in {"preflight", "verify-preflight", "restore", "verify-snapshot", "activate"}:
            child.add_argument("--snapshot", required=True, type=Path)
        if command == "preflight":
            child.add_argument("--create-inactive-ruleset", action="store_true")
        if command in {"verify-preflight", "activate", "verify-final"}:
            child.add_argument("--ruleset-id", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        transport = GhTransport()
        if args.command == "snapshot":
            snapshot = capture_snapshot(args.repo, transport)
            write_state(args.out, snapshot)
            result: object = {"passed": True, "snapshot": str(args.out.resolve())}
        else:
            snapshot = load_state(args.snapshot) if hasattr(args, "snapshot") else None
            if args.command == "preflight":
                if not args.create_inactive_ruleset:
                    raise GovernanceError("create_inactive_ruleset_required")
                result = ensure_preflight(args.repo, snapshot, transport)
            elif args.command == "verify-preflight":
                result = verify_preflight(args.repo, snapshot, args.ruleset_id, transport)
            elif args.command == "restore":
                result = restore_snapshot(args.repo, snapshot, transport)
            elif args.command == "verify-snapshot":
                result = verify_snapshot(args.repo, snapshot, transport)
            elif args.command == "activate":
                result = activate_ruleset(args.repo, snapshot, args.ruleset_id, transport)
            elif args.command == "verify-final":
                result = verify_final(args.repo, args.ruleset_id, transport)
            else:
                raise GovernanceError("unsupported_command")
        if getattr(args, "json", False):
            sys.stdout.write(canonical_json(result) + "\n")
        return 0
    except (GovernanceError, OSError, TypeError, ValueError) as exc:
        sys.stdout.write(canonical_json({"error": str(exc), "schema_version": 1}) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
