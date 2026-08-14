from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "github_governance.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("github_governance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object | None]] = []
        self.state: dict[str, object] = {
            "repository": {
                "visibility": "public",
                "description": "HSConfig",
                "homepage": "",
                "has_issues": True,
                "has_projects": True,
                "has_wiki": False,
                "has_discussions": False,
                "security_and_analysis": {
                    "secret_scanning": {"status": "enabled"},
                    "secret_scanning_push_protection": {"status": "enabled"},
                },
            },
            "topics": {"names": ["hearthstone", "hearthranger"]},
            "actions_permissions": {"enabled": True, "allowed_actions": "selected"},
            "selected_actions": {
                "github_owned_allowed": True,
                "verified_allowed": False,
                "patterns_allowed": [],
            },
            "vulnerability_alerts": {"enabled": True},
            "private_vulnerability_reporting": {"enabled": True},
            "automated_security_fixes": {"enabled": False},
            "rulesets": [],
            "collaborators": [{"login": "Teufelsboy", "permissions": {"admin": True}}],
            "community_profile": {"documentation": "https://github.com/Teufelsboy/HSConfig/tree/main/docs"},
        }

    def request(self, method: str, endpoint: str, payload: object | None = None) -> object:
        self.calls.append((method, endpoint, payload))
        key = endpoint.split("?")[0]
        mapping = {
            "repos/Teufelsboy/HSConfig": "repository",
            "repos/Teufelsboy/HSConfig/topics": "topics",
            "repos/Teufelsboy/HSConfig/actions/permissions": "actions_permissions",
            "repos/Teufelsboy/HSConfig/actions/permissions/selected-actions": "selected_actions",
            "repos/Teufelsboy/HSConfig/vulnerability-alerts": "vulnerability_alerts",
            "repos/Teufelsboy/HSConfig/private-vulnerability-reporting": "private_vulnerability_reporting",
            "repos/Teufelsboy/HSConfig/automated-security-fixes": "automated_security_fixes",
            "repos/Teufelsboy/HSConfig/rulesets": "rulesets",
            "repos/Teufelsboy/HSConfig/collaborators": "collaborators",
            "repos/Teufelsboy/HSConfig/community/profile": "community_profile",
        }
        if method == "GET":
            return json.loads(json.dumps(self.state[mapping[key]]))
        if method == "POST" and key.endswith("/rulesets"):
            row = dict(payload or {})
            row["id"] = 77
            cast = self.state["rulesets"]
            assert isinstance(cast, list)
            cast.append(row)
            return json.loads(json.dumps(row))
        if method == "PUT" and "/rulesets/" in key:
            rulesets = self.state["rulesets"]
            assert isinstance(rulesets, list)
            for row in rulesets:
                if isinstance(row, dict) and row.get("id") == int(key.rsplit("/", 1)[1]):
                    row.update(dict(payload or {}))
                    return json.loads(json.dumps(row))
            raise AssertionError("missing ruleset")
        if method == "DELETE" and "/rulesets/" in key:
            rule_id = int(key.rsplit("/", 1)[1])
            rulesets = self.state["rulesets"]
            assert isinstance(rulesets, list)
            self.state["rulesets"] = [row for row in rulesets if row.get("id") != rule_id]
            return {}
        if method in {"PATCH", "PUT", "DELETE"}:
            state_key = mapping[key]
            if method == "DELETE":
                self.state[state_key] = {"enabled": False}
            elif payload is None and state_key in {
                "vulnerability_alerts",
                "private_vulnerability_reporting",
                "automated_security_fixes",
            }:
                self.state[state_key] = {"enabled": True}
            elif isinstance(self.state[state_key], dict):
                cast = self.state[state_key]
                assert isinstance(cast, dict)
                cast.update(dict(payload or {}))
            return json.loads(json.dumps(self.state[state_key]))
        raise AssertionError((method, endpoint, payload))


def test_snapshot_is_complete_canonical_digest_bound_and_duplicate_aware(tmp_path: Path) -> None:
    module = _load_module()
    transport = FakeTransport()
    snapshot = module.capture_snapshot("Teufelsboy/HSConfig", transport)
    assert set(snapshot) == {
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
    path = tmp_path / "snapshot.json"
    module.write_state(path, snapshot)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    payload = envelope["payload"].encode("utf-8")
    assert envelope["payload_sha256"] == hashlib.sha256(payload).hexdigest()
    assert module.load_state(path) == snapshot

    path.write_text('{"payload":"{}","payload":"{}","payload_sha256":"x"}', encoding="utf-8")
    with pytest.raises(module.GovernanceError, match="duplicate"):
        module.load_state(path)


def test_preflight_creates_one_exact_inactive_ruleset_and_reads_it_back() -> None:
    module = _load_module()
    transport = FakeTransport()
    snapshot = module.capture_snapshot("Teufelsboy/HSConfig", transport)
    result = module.ensure_preflight("Teufelsboy/HSConfig", snapshot, transport)
    assert result["ruleset_id"] == 77
    rulesets = transport.state["rulesets"]
    assert isinstance(rulesets, list) and len(rulesets) == 1
    rule = rulesets[0]
    assert rule["enforcement"] == "disabled"
    assert rule["target"] == "branch"
    assert rule["conditions"] == {"ref_name": {"include": ["refs/heads/main"], "exclude": []}}
    assert [entry["type"] for entry in rule["rules"]] == [
        "deletion",
        "non_fast_forward",
        "required_linear_history",
        "required_signatures",
    ]
    assert rule["bypass_actors"] == []
    assert transport.calls[-1][0:2] == ("GET", "repos/Teufelsboy/HSConfig/rulesets")


def test_activation_requires_safe_collaborators_and_verifies_active_readback() -> None:
    module = _load_module()
    transport = FakeTransport()
    snapshot = module.capture_snapshot("Teufelsboy/HSConfig", transport)
    preflight = module.ensure_preflight("Teufelsboy/HSConfig", snapshot, transport)
    active = module.activate_ruleset(
        "Teufelsboy/HSConfig", snapshot, int(preflight["ruleset_id"]), transport
    )
    assert active["enforcement"] == "active"
    transport.state["collaborators"] = [
        {"login": "Teufelsboy", "permissions": {"admin": True}},
        {"login": "writer", "permissions": {"push": True}},
    ]
    with pytest.raises(module.GovernanceError, match="unexpected_write_collaborator"):
        module.activate_ruleset("Teufelsboy/HSConfig", snapshot, 77, transport)


def test_restore_removes_created_ruleset_then_restores_every_mutable_surface() -> None:
    module = _load_module()
    transport = FakeTransport()
    snapshot = module.capture_snapshot("Teufelsboy/HSConfig", transport)
    module.ensure_preflight("Teufelsboy/HSConfig", snapshot, transport)
    repository = transport.state["repository"]
    assert isinstance(repository, dict)
    repository["has_projects"] = False
    transport.state["topics"] = {"names": ["changed"]}
    transport.calls.clear()
    module.restore_snapshot("Teufelsboy/HSConfig", snapshot, transport)
    module.verify_snapshot("Teufelsboy/HSConfig", snapshot, transport)
    mutation_calls = [call for call in transport.calls if call[0] != "GET"]
    assert mutation_calls[0][0:2] == ("DELETE", "repos/Teufelsboy/HSConfig/rulesets/77")
    assert transport.state["rulesets"] == []
    assert transport.state["topics"] == snapshot["topics"]
    restored_repository = transport.state["repository"]
    assert isinstance(restored_repository, dict)
    assert restored_repository["has_projects"] is True


def test_final_verification_requires_security_actions_presentation_and_active_ruleset() -> None:
    module = _load_module()
    transport = FakeTransport()
    snapshot = module.capture_snapshot("Teufelsboy/HSConfig", transport)
    preflight = module.ensure_preflight("Teufelsboy/HSConfig", snapshot, transport)
    repository = transport.state["repository"]
    assert isinstance(repository, dict)
    repository["has_projects"] = False
    transport.state["community_profile"] = {
        "documentation": "https://github.com/Teufelsboy/HSConfig/tree/main/docs"
    }
    module.activate_ruleset(
        "Teufelsboy/HSConfig", snapshot, int(preflight["ruleset_id"]), transport
    )
    result = module.verify_final("Teufelsboy/HSConfig", 77, transport)
    assert result["passed"] is True
    selected = transport.state["selected_actions"]
    assert isinstance(selected, dict)
    selected["verified_allowed"] = True
    with pytest.raises(module.GovernanceError, match="selected_actions_mismatch"):
        module.verify_final("Teufelsboy/HSConfig", 77, transport)
