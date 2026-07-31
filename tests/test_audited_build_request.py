from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import socket

import pytest

from hsconfig.audited_build_request import (
    render_all_audited_configure_runs,
    resolve_audited_package_request,
    resolve_frozen_audited_package_request,
)
from hsconfig.build_input_catalog import (
    load_packaged_audited_build_inputs,
    load_packaged_audited_build_resource_store,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "operator" / "audited-deck-catalog.json"


def test_audited_build_bridge_has_no_test_only_imports() -> None:
    paths = (
        ROOT / "src" / "hsconfig" / "audited_build_request.py",
        ROOT / "scripts" / "reconcile_outputs.py",
    )
    imported = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        imported.extend(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )

    assert not any(name == "tests" or name.startswith("tests.") for name in imported)


def test_resolve_audited_request_is_bound_to_frozen_production_context() -> None:
    request = resolve_audited_package_request(
        deck_name="ShadowPriest",
        catalog_path=CATALOG,
    )

    assert request.snapshot.strict_build_context is not None
    assert request.snapshot.strict_build_context.inputs.deck_name == "ShadowPriest"
    assert request.invocation.runtime_root == "runtime-write-fence"
    assert request.invocation.cards_json is None
    assert request.invocation.claims_json is None


def test_frozen_core_touches_no_ambient_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audited = load_packaged_audited_build_inputs()
    resources = load_packaged_audited_build_resource_store(
        audited_inputs=audited
    )
    inputs = audited.builds[0]
    deck_code = json.loads(CATALOG.read_text(encoding="utf-8"))["decks"][0][
        "deck_code"
    ]

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ambient authority touched")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    request = resolve_frozen_audited_package_request(
        inputs=inputs,
        resources=resources,
        deck_code=deck_code,
    )

    assert request.snapshot.strict_build_context is not None


def test_all_twelve_frozen_runs_are_deterministic() -> None:
    first = render_all_audited_configure_runs(CATALOG)
    second = render_all_audited_configure_runs(CATALOG)

    assert len(first) == 12
    assert first == second
    assert tuple(name for name, _run in first) == (
        "ShadowPriest",
        "CtAPaladin",
        "PirateRogue",
        "BigShaman",
        "Discolock",
        "TreantDruid",
        "ImbueMage",
        "MechPala",
        "Kingslayer",
        "Boarlock",
        "PirateDH",
        "CuteWarrior",
    )
    assert len({run.content_root_sha256 for _name, run in first}) == 12


def test_all_frozen_packages_match_the_approved_byte_contract() -> None:
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "package-byte-contract-v1.json")
        .read_text(encoding="utf-8")
    )

    for deck_name, run in render_all_audited_configure_runs(CATALOG):
        rows = [
            {
                "relative_path": artifact.relative_path.removeprefix(
                    "04_package/"
                ),
                "size": len(artifact.content),
                "sha256": sha256(artifact.content).hexdigest(),
            }
            for artifact in run.artifacts
            if artifact.relative_path.startswith("04_package/")
        ]
        assert rows == fixture["decks"][deck_name]["artifacts"]
