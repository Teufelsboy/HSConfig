from __future__ import annotations

from copy import deepcopy
import json

import pytest

from tests.test_github_governance import _load_module


DESCRIPTION = (
    "Codex-first HearthRanger start-config generator: deck name and deck code "
    "to a validated, live-matched VisionAI CustomConfig."
)
TOPICS = ["codex", "configuration", "hearthranger", "hearthstone", "python", "visionai"]
BASE = "repos/Teufelsboy/HSConfig"


class ProductTransport:
    """Only the two product endpoints exist in this controlled API boundary."""

    def __init__(self, *, desired: bool = False, ignored_write: str = "") -> None:
        self.repository = {
            "description": DESCRIPTION if desired else "Old product description",
            "visibility": "public",
            "has_issues": True,
            "security_and_analysis": {"secret_scanning": {"status": "enabled"}},
        }
        self.topics = {"names": list(TOPICS) if desired else ["old-topic"]}
        self.ignored_write = ignored_write
        self.calls: list[tuple[str, str, object | None]] = []

    def request(self, method: str, endpoint: str, payload: object | None = None) -> object:
        self.calls.append((method, endpoint, deepcopy(payload)))
        if method == "GET" and endpoint == BASE:
            return deepcopy(self.repository)
        if method == "GET" and endpoint == f"{BASE}/topics":
            return deepcopy(self.topics)
        if method == "PATCH" and endpoint == BASE:
            assert payload == {"description": DESCRIPTION}
            if self.ignored_write != "description":
                self.repository["description"] = DESCRIPTION
            return deepcopy(self.repository)
        if method == "PUT" and endpoint == f"{BASE}/topics":
            assert payload == {"names": TOPICS}
            if self.ignored_write != "topics":
                self.topics = {"names": list(TOPICS)}
            return deepcopy(self.topics)
        raise AssertionError(f"out-of-scope API call: {method} {endpoint}")


def _expected_result() -> dict:
    return {
        "passed": True,
        "repository": "Teufelsboy/HSConfig",
        "description": DESCRIPTION,
        "topics": TOPICS,
    }


def test_product_polish_changes_only_description_and_topics(monkeypatch, capsys):
    module = _load_module()
    transport = ProductTransport()
    original = deepcopy(transport.repository)
    monkeypatch.setattr(module, "GhTransport", lambda: transport)

    assert module.main(["product-polish", "--repo", "Teufelsboy/HSConfig", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == _expected_result()
    assert transport.repository == {**original, "description": DESCRIPTION}
    assert transport.topics == {"names": TOPICS}
    assert transport.calls == [
        ("PATCH", BASE, {"description": DESCRIPTION}),
        ("PUT", f"{BASE}/topics", {"names": TOPICS}),
        ("GET", BASE, None),
        ("GET", f"{BASE}/topics", None),
    ]


def test_verify_product_polish_is_read_only_and_exact(monkeypatch, capsys):
    module = _load_module()
    transport = ProductTransport(desired=True)
    before = deepcopy((transport.repository, transport.topics))
    monkeypatch.setattr(module, "GhTransport", lambda: transport)

    assert module.main(["verify-product-polish", "--repo", "Teufelsboy/HSConfig", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == _expected_result()
    assert (transport.repository, transport.topics) == before
    assert transport.calls == [("GET", BASE, None), ("GET", f"{BASE}/topics", None)]


@pytest.mark.parametrize("field", ["description", "topics"])
def test_product_polish_requires_exact_readback_after_writes(field, monkeypatch, capsys):
    module = _load_module()
    transport = ProductTransport(ignored_write=field)
    monkeypatch.setattr(module, "GhTransport", lambda: transport)

    assert module.main(["product-polish", "--repo", "Teufelsboy/HSConfig", "--json"]) == 2

    assert json.loads(capsys.readouterr().out) == {
        "error": f"product_polish_{field}_mismatch", "schema_version": 1,
    }
    assert [call[:2] for call in transport.calls[:2]] == [
        ("PATCH", BASE), ("PUT", f"{BASE}/topics"),
    ]
    assert all(method == "GET" for method, _, _ in transport.calls[2:])


@pytest.mark.parametrize("changed", ["description", "topics", "duplicate_topics"])
def test_verify_product_polish_rejects_metadata_drift_without_repair(changed, monkeypatch, capsys):
    module = _load_module()
    transport = ProductTransport(desired=True)
    if changed == "description":
        transport.repository["description"] = DESCRIPTION + " Extra claim."
    elif changed == "topics":
        transport.topics["names"] = TOPICS[:-1]
    else:
        transport.topics["names"] = TOPICS + ["codex"]
    before = deepcopy((transport.repository, transport.topics))
    monkeypatch.setattr(module, "GhTransport", lambda: transport)

    assert module.main(["verify-product-polish", "--repo", "Teufelsboy/HSConfig", "--json"]) == 2

    error = "description" if changed == "description" else "topics"
    assert json.loads(capsys.readouterr().out)["error"] == f"product_polish_{error}_mismatch"
    assert (transport.repository, transport.topics) == before
    assert all(method == "GET" for method, _, _ in transport.calls)


@pytest.mark.parametrize("command", ["product-polish", "verify-product-polish"])
def test_product_polish_rejects_invalid_repository_before_api(command, monkeypatch, capsys):
    module = _load_module()
    transport = ProductTransport()
    monkeypatch.setattr(module, "GhTransport", lambda: transport)

    assert module.main([command, "--repo", "owner/repo/actions/permissions", "--json"]) == 2

    assert json.loads(capsys.readouterr().out)["error"] == "repository_invalid"
    assert transport.calls == []
