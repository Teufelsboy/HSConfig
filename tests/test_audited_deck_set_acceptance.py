from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.cli import main
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import write_json
from hsconfig.strict_package_validation import validate_complete_package
from tests.helpers.fixture_prepare import prepare_fixture_deck, read_json


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
SUPPLEMENTAL_PATH = Path("docs/operator/supplemental-proof-decks.json")
AUDITED_CARD_DB_PATH = Path("tests/fixtures/audited_deck_card_db.json")
DIAGNOSTIC_APPLY_REASON = "diagnostic_source_not_apply_eligible"
CARD_METADATA_KEYS = {"ConfigComment", "GameCardId"}


def _audited_card_db() -> dict[int, SimpleNamespace]:
    payload = read_json(AUDITED_CARD_DB_PATH)
    assert payload["schema"] == 1
    cards: dict[int, SimpleNamespace] = {}
    for row in payload["cards"]:
        (
            dbf_id,
            card_id,
            name,
            cost,
            card_type,
            card_class,
            text,
            mechanics,
        ) = row
        card = SimpleNamespace(
            card_class=card_class,
            card_id=card_id,
            cost=cost,
            english_description=text,
            english_name=name,
            name=name,
            type=card_type,
        )
        for mechanic in mechanics:
            setattr(card, str(mechanic), True)
        cards[int(dbf_id)] = card
    return cards


@pytest.fixture
def read_only_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict[str, list[str]]]:
    attempts: dict[str, list[str]] = {
        "external_network": [],
        "runtime_write": [],
    }

    def deny_external_network(*args: Any, **kwargs: Any) -> None:
        del kwargs
        attempts["external_network"].append(str(args[0]) if args else "unknown")
        raise AssertionError("external network access is forbidden in acceptance tests")

    def no_cardfeed(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        del args, kwargs
        return []

    def deny_runtime_write(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        attempts["runtime_write"].append("apply_package")
        raise AssertionError("runtime writes are forbidden in acceptance tests")

    monkeypatch.setattr("hsconfig.hearthstonejson.urlopen", deny_external_network)
    monkeypatch.setattr("socket.create_connection", deny_external_network)
    monkeypatch.setattr("socket.getaddrinfo", deny_external_network)
    audited_card_db = _audited_card_db()
    monkeypatch.setattr(
        "hsconfig.deckstring_decode.cardxml.load_dbf",
        lambda: (audited_card_db, None),
    )
    monkeypatch.setattr("hsconfig.hearthstonejson.fetch_latest_cards", no_cardfeed)
    monkeypatch.setattr(
        "hsconfig.hearthstonejson.fetch_latest_collectible_cards",
        no_cardfeed,
    )
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", no_cardfeed)
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        no_cardfeed,
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        no_cardfeed,
    )
    monkeypatch.setattr("hsconfig.runtime_apply.apply_package", deny_runtime_write)
    monkeypatch.setattr(
        "hsconfig.commands.apply.apply_package",
        deny_runtime_write,
    )

    yield attempts

    assert attempts == {
        "external_network": [],
        "runtime_write": [],
    }


def _catalog_payloads() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        deepcopy(read_json(MATRIX_PATH)["decks"]),
        deepcopy(read_json(SUPPLEMENTAL_PATH)["decks"]),
    )


def test_audited_catalog_requires_exact_manifest_membership() -> None:
    matrix, supplemental = _catalog_payloads()

    audited = _validate_audited_deck_catalog(matrix, supplemental)

    assert len(matrix) == 11
    assert sum(row["deck_name"] == "CuteWarrior" for row in supplemental) == 1
    assert len(audited) == 12
    assert len({row["deck_name"] for row in audited}) == 12
    assert len({row["deck_code"] for row in audited}) == 12


def test_audited_catalog_rejects_missing_matrix_deck_or_cute_warrior() -> None:
    matrix, supplemental = _catalog_payloads()

    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(matrix[:-1], supplemental)
    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(
            matrix,
            [row for row in supplemental if row["deck_name"] != "CuteWarrior"],
        )


def test_audited_catalog_rejects_duplicate_cute_name_or_deck_code() -> None:
    matrix, supplemental = _catalog_payloads()
    cute = next(row for row in supplemental if row["deck_name"] == "CuteWarrior")

    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(matrix, [*supplemental, deepcopy(cute)])

    duplicate_name = deepcopy(matrix)
    duplicate_name[-1]["deck_name"] = duplicate_name[0]["deck_name"]
    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(duplicate_name, supplemental)

    duplicate_code = deepcopy(matrix)
    duplicate_code[-1]["deck_code"] = duplicate_code[0]["deck_code"]
    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(duplicate_code, supplemental)


def _synthetic_cardid_contract(
    *,
    behavior_block: str = "OnBoardBonus",
    source_type: str = "MINION",
    linked_runtime_owner: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    source_card_id = "SOURCE_001"
    runtime_card_id = "RUNTIME_001" if linked_runtime_owner else source_card_id
    linked_entities = (
        [
            {
                "card_id": runtime_card_id,
                "link_kind": "starting_hero_power",
                "type": "HERO_POWER",
            }
        ]
        if linked_runtime_owner
        else []
    )
    semantic = {
        "cards": [
            {
                "card_id": source_card_id,
                "linked_entities": linked_entities,
                "type": source_type,
            }
        ]
    }
    behavior = {
        "rows": [
            {
                "behavior_block": behavior_block,
                "card_id": source_card_id,
                "condition": "friendly",
                "link_kind": (
                    "starting_hero_power" if linked_runtime_owner else "self"
                ),
                "meaningful_runtime_surface": True,
                "runtime_card_id": runtime_card_id,
                "source_card_id": source_card_id,
                "source_claim_ids": ["claim:1"],
                "source_refs": ["source:1"],
                "value": 5,
            }
        ]
    }
    payloads = {
        runtime_card_id: {
            "ConfigComment": "synthetic acceptance payload",
            "GameCardId": runtime_card_id,
            behavior_block: {
                "values": [{"condition": "friendly", "value": 5}],
            },
        }
    }
    return semantic, behavior, payloads


@pytest.mark.parametrize(
    "behavior_block",
    ["OnBoardBonus", "BeforeBattlecryTargetBonus"],
)
def test_spell_cannot_own_board_or_battlecry_target_runtime_surface(
    behavior_block: str,
) -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract(
        behavior_block=behavior_block,
        source_type="SPELL",
    )

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


def test_linked_runtime_owner_uses_source_and_runtime_semantic_types() -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract(
        linked_runtime_owner=True,
    )

    _assert_cardid_report_contract(semantic, behavior, payloads)


def test_unlinked_runtime_owner_fails_even_when_both_card_types_are_known() -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract()
    semantic["cards"].append(
        {
            "card_id": "UNRELATED_001",
            "linked_entities": [],
            "type": "HERO_POWER",
        }
    )
    behavior["rows"][0]["runtime_card_id"] = "UNRELATED_001"
    payloads["UNRELATED_001"] = payloads.pop("SOURCE_001")
    payloads["UNRELATED_001"]["GameCardId"] = "UNRELATED_001"

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


def test_cardid_parity_rejects_phantom_report_row() -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract()
    phantom = deepcopy(behavior["rows"][0])
    phantom["value"] = 6
    behavior["rows"].append(phantom)

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


@pytest.mark.parametrize("duplicate_side", ["physical", "report"])
def test_cardid_parity_preserves_duplicate_rows(duplicate_side: str) -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract()
    if duplicate_side == "physical":
        payloads["SOURCE_001"]["OnBoardBonus"]["values"].append(
            {"condition": "friendly", "value": 5}
        )
    else:
        behavior["rows"].append(deepcopy(behavior["rows"][0]))

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    [("condition", True), ("value", "5")],
)
def test_cardid_parity_rejects_condition_or_value_type_drift(
    field: str,
    drifted_value: Any,
) -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract()
    behavior["rows"][0][field] = drifted_value

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


def _validate_audited_deck_catalog(
    matrix: list[dict[str, Any]],
    supplemental: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(matrix) != 11:
        raise ValueError("audited matrix must contain exactly 11 decks")
    cute_warriors = [
        row for row in supplemental if row.get("deck_name") == "CuteWarrior"
    ]
    if len(cute_warriors) != 1:
        raise ValueError("supplemental catalog must contain CuteWarrior exactly once")
    audited = [*matrix, cute_warriors[0]]
    if len(audited) != 12:
        raise ValueError("audited catalog must contain exactly 12 decks")
    deck_names = [str(row.get("deck_name", "")) for row in audited]
    deck_codes = [str(row.get("deck_code", "")) for row in audited]
    if "" in deck_names or len(set(deck_names)) != len(deck_names):
        raise ValueError("audited deck names must be non-empty and unique")
    if "" in deck_codes or len(set(deck_codes)) != len(deck_codes):
        raise ValueError("audited deck codes must be non-empty and unique")
    return audited


def audited_decks() -> list[dict[str, Any]]:
    matrix = read_json(MATRIX_PATH)["decks"]
    supplemental = read_json(SUPPLEMENTAL_PATH)["decks"]
    return _validate_audited_deck_catalog(matrix, supplemental)


def _captured_source_documents(deck: Mapping[str, Any]) -> dict[str, Any]:
    fixture_bytes = f"{deck['deck_name']}:diagnostic-fixture".encode()
    return {
        "source_documents": [
            {
                "source_url": "https://example.invalid/diagnostic-fixture",
                "source_title": f"{deck['deck_name']} diagnostic fixture",
                "source_family": "guide",
                "retrieved_at": "2026-07-27T00:00:00Z",
                "acquisition_provenance": {
                    "mode": "captured_record",
                    "authority": "captured_unverified",
                    "content_sha256": f"sha256:{sha256(fixture_bytes).hexdigest()}",
                },
                "source_visibility": "full_text",
                "source_lane": "archetype_matched_public_guide",
                "deck_name": str(deck["deck_name"]),
                "archetype": "diagnostic_fixture",
                "deck_match_scope": "archetype_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 0,
                        "decoded_candidate_count": 0,
                        "matched": False,
                        "matched_deck_fingerprint": "",
                        "candidate_deck_code_hashes": [],
                    }
                },
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "scope": "deck",
                        "cards": [],
                        "stance": "diagnostic_fixture",
                        "evidence_text_short": (
                            "Diagnostic captured source used for read-only acceptance."
                        ),
                        "source_confidence": "medium",
                        "promotion_eligible": False,
                    }
                ],
            }
        ]
    }


def _prepare_audited_deck(
    tmp_path: Path,
    deck: dict[str, Any],
) -> dict[str, Any]:
    runtime_root = tmp_path / "runtime"
    if deck["deck_name"] != "CuteWarrior":
        return {
            **prepare_fixture_deck(tmp_path, deck),
            "runtime_root": runtime_root,
        }

    source_path = tmp_path / "cutewarrior-diagnostic-source.json"
    write_json(source_path, _captured_source_documents(deck))
    out = tmp_path / "CuteWarrior"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            str(deck["deck_name"]),
            "--deck-code",
            str(deck["deck_code"]),
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_path),
            "--json",
        ]
    )
    return {
        "exit_code": exit_code,
        "out": out,
        "operator": read_json(out / "reports" / "operator_summary.json"),
        "runtime_root": runtime_root,
    }


def _deck_dir(package: Mapping[str, Any]) -> Path:
    directories = [
        path
        for path in (Path(package["out"]) / "CustomConfig").iterdir()
        if path.is_dir()
    ]
    assert len(directories) == 1
    return directories[0]


def _card_payloads(package: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        path.stem: read_json(path)
        for path in _deck_dir(package).glob("*.json")
        if path.name not in {"GlobalValues.json", "Mulligan.json", "Combo.json"}
    }


def _physical_card_rows(
    payloads: Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, str, tuple[Any, ...], tuple[Any, ...]]]:
    rows: list[tuple[str, str, tuple[Any, ...], tuple[Any, ...]]] = []
    for card_id, payload in payloads.items():
        for block, block_payload in payload.items():
            if block in CARD_METADATA_KEYS or not isinstance(block_payload, Mapping):
                continue
            values = block_payload.get("values", [])
            assert isinstance(values, list)
            for row in values:
                assert isinstance(row, Mapping)
                rows.append(
                    (
                        card_id,
                        block,
                        _canonical_json_value(row.get("condition")),
                        _canonical_json_value(row.get("value")),
                    )
                )
    return rows


def _canonical_json_value(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, list):
        return (
            "list",
            tuple(_canonical_json_value(item) for item in value),
        )
    if isinstance(value, Mapping):
        return (
            "object",
            tuple(
                sorted(
                    (
                        str(key),
                        _canonical_json_value(item),
                    )
                    for key, item in value.items()
                )
            ),
        )
    raise AssertionError(f"unsupported runtime JSON value type: {type(value).__name__}")


def _semantic_card_types_and_links(
    semantic: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    card_types: dict[str, str] = {}
    linked_runtime_ids: dict[str, set[str]] = {}

    def add_card_type(card_id: str, card_type: str) -> None:
        assert card_id
        normalized_type = card_type.strip().upper()
        assert normalized_type
        previous = card_types.get(card_id)
        assert previous in {None, normalized_type}
        card_types[card_id] = normalized_type

    for card in semantic.get("cards", []):
        assert isinstance(card, Mapping)
        source_card_id = str(card.get("card_id", ""))
        add_card_type(source_card_id, str(card.get("type", "")))
        for linked in card.get("linked_entities", []):
            assert isinstance(linked, Mapping)
            runtime_card_id = str(linked.get("card_id", ""))
            add_card_type(runtime_card_id, str(linked.get("type", "")))
            linked_runtime_ids.setdefault(source_card_id, set()).add(runtime_card_id)

    for effect in semantic.get("deckwide_effects", []):
        assert isinstance(effect, Mapping)
        source_card_id = str(effect.get("source_card_id", ""))
        runtime_card_id = str(effect.get("target_card_id", ""))
        add_card_type(runtime_card_id, str(effect.get("target_type", "")))
        linked_runtime_ids.setdefault(source_card_id, set()).add(runtime_card_id)

    return card_types, linked_runtime_ids


def _assert_cardid_report_contract(
    semantic: Mapping[str, Any],
    behavior: Mapping[str, Any],
    payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    card_types, linked_runtime_ids = _semantic_card_types_and_links(semantic)
    report_rows = [
        row
        for row in behavior.get("rows", [])
        if isinstance(row, Mapping)
        and row.get("meaningful_runtime_surface") is True
    ]

    report_counter = Counter(
        (
            str(row.get("runtime_card_id", row.get("card_id", ""))),
            str(row.get("behavior_block", "")),
            _canonical_json_value(row.get("condition")),
            _canonical_json_value(row.get("value")),
        )
        for row in report_rows
    )
    physical_counter = Counter(_physical_card_rows(payloads))
    assert physical_counter == report_counter

    for row in report_rows:
        source_card_id = str(row.get("source_card_id", row.get("card_id", "")))
        runtime_card_id = str(row.get("runtime_card_id", row.get("card_id", "")))
        assert str(row.get("card_id", "")) == source_card_id
        assert source_card_id in card_types
        assert runtime_card_id in card_types
        if runtime_card_id != source_card_id:
            assert runtime_card_id in linked_runtime_ids.get(source_card_id, set())
        if row.get("behavior_block") in {
            "OnBoardBonus",
            "BeforeBattlecryTargetBonus",
        }:
            assert card_types[source_card_id] != "SPELL"
            assert card_types[runtime_card_id] != "SPELL"
        assert row.get("source_claim_ids")
        assert row.get("source_refs")


def _mulligan_hold_cards(package: Mapping[str, Any]) -> set[str]:
    mulligan = read_json(_deck_dir(package) / "Mulligan.json")
    return {
        str(row["mulligan"])
        for row in mulligan["Mulligan"]["values"]
        if row.get("value") == "hold"
    }


def _assert_global_semantic_invariants(package: Mapping[str, Any]) -> None:
    out = Path(package["out"])
    reports = out / "reports"
    semantic = read_json(reports / "semantic_enrichment_report.json")
    behavior = read_json(reports / "card_behavior_plan_report.json")
    mulligan_plan = read_json(reports / "mulligan_plan_report.json")
    payloads = _card_payloads(package)
    _assert_cardid_report_contract(semantic, behavior, payloads)

    card_condition_suppressions = {
        str(row["claim_id"])
        for row in behavior["suppressed"]
        if "condition" in str(row.get("reason", ""))
        and (
            str(row.get("reason", "")).endswith("_not_encoded")
            or "unsupported" in str(row.get("reason", ""))
        )
    }
    emitted_card_claims = {
        str(claim_id)
        for row in behavior["rows"]
        for claim_id in row.get("source_claim_ids", [])
    }
    assert card_condition_suppressions.isdisjoint(emitted_card_claims)

    mulligan_condition_suppressions = {
        str(row["claim_id"])
        for row in mulligan_plan["suppressed_rules"]
        if row.get("reason") == "unsupported_mulligan_condition"
    }
    emitted_mulligan_claims = {
        str(claim_id)
        for row in mulligan_plan["rules"]
        for claim_id in row.get("source_claim_ids", [])
    }
    assert mulligan_condition_suppressions.isdisjoint(emitted_mulligan_claims)


def _assert_deck_specific_invariants(
    deck_name: str,
    package: Mapping[str, Any],
) -> None:
    out = Path(package["out"])
    reports = out / "reports"
    payloads = _card_payloads(package)
    holds = _mulligan_hold_cards(package)

    if deck_name == "ShadowPriest":
        assert "BeforeUseHeroPowerBonus" not in payloads["SW_448"]
        assert len(payloads["EX1_625t"]["BeforeUseHeroPowerBonus"]["values"]) == 1
        behavior = read_json(reports / "card_behavior_plan_report.json")
        reciprocal = [
            row
            for row in behavior["suppressed"]
            if row.get("reason") == "reciprocal_burn_report_only"
        ]
        assert reciprocal
        assert "GVG_009" in {
            card for row in reciprocal for card in row["cards"]
        }
        reciprocal_claims = {
            str(claim_id)
            for row in reciprocal
            for claim_id in row["source_claim_ids"]
        }
        emitted_claims = {
            str(claim_id)
            for row in behavior["rows"]
            for claim_id in row.get("source_claim_ids", [])
        }
        assert reciprocal_claims.isdisjoint(emitted_claims)
        for card_id in ("TOY_518", "WON_065"):
            assert len(payloads[card_id]["OnBoardBonus"]["values"]) == 1
        return

    if deck_name == "MechPala":
        module_ids = {"TOY_330t95", "TOY_330t98", "TOY_330t11"}
        metadata = read_json(reports / "semantic_enrichment_report.json")
        readiness = read_json(reports / "per_card_config_readiness_report.json")
        metadata_by_card = {row["card_id"]: row for row in metadata["cards"]}
        assert module_ids <= set(metadata_by_card)
        assert module_ids <= set(readiness["cards"])
        for card_id in module_ids:
            assert metadata_by_card[card_id]["deck_zone"] == "sideboard"
            assert metadata_by_card[card_id]["sideboard_owner_card_id"] == "TOY_330"
            assert readiness["cards"][card_id]["deck_zone"] == "sideboard"
            assert readiness["cards"][card_id]["runtime_surfaces"] == []
        assert "TOY_330" not in holds
        return

    if deck_name == "Kingslayer":
        assert "DEEP_014" not in holds
        for card_id in ("VAC_938", "VAC_701"):
            assert "BeforePhysicalAttackBonus" not in payloads[card_id]
        return

    if deck_name == "Boarlock":
        assert "WW_092" not in holds
        assert not (_deck_dir(package) / "Combo.json").exists()
        globalvalues = read_json(_deck_dir(package) / "GlobalValues.json")
        assert "MyHeroPowerValue" not in globalvalues
        return

    if deck_name == "Discolock":
        assert all(
            "InHandPlayPriority" not in payload for payload in payloads.values()
        )
        profile = read_json(reports / "globalvalues_profile.json")
        assert profile["authority_parity"] == {
            "authorized_overlay_keys": [],
            "emitted_overlay_keys": [],
            "status": "matched",
        }
        return

    if deck_name == "ImbueMage":
        readiness = read_json(reports / "per_card_config_readiness_report.json")
        readiness_mulligan_cards = {
            card_id
            for card_id, row in readiness["cards"].items()
            if "Mulligan.json" in row["runtime_surfaces"]
        }
        mulligan = read_json(_deck_dir(package) / "Mulligan.json")
        physical_mulligan_cards = {
            str(row["mulligan"])
            for row in mulligan["Mulligan"]["values"]
            if row.get("mulligan") != "*"
        }
        assert physical_mulligan_cards == readiness_mulligan_cards
        assert "FIR_911" in physical_mulligan_cards


@pytest.mark.parametrize(
    "deck",
    audited_decks(),
    ids=lambda row: row["deck_name"],
)
def test_audited_deck_contract_is_current(
    deck: dict[str, Any],
    tmp_path: Path,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    decoded = decode_deck_code(str(deck["deck_code"]))
    assert decoded["card_count"] == 30
    assert decoded["unresolved_card_count"] == 0
    assert deck["fixture_expected_load_safe"] is True
    assert deck["fixture_runtime_apply_authority"] == "diagnostic_only"

    runtime_root = tmp_path / "runtime"
    assert not runtime_root.exists()
    package = _prepare_audited_deck(tmp_path, deck)

    assert package["exit_code"] == 0
    assert package["runtime_root"] == runtime_root
    assert not runtime_root.exists()
    summary = package["operator"]
    assert (Path(package["out"]) / "package_derivation_receipt.json").is_file()
    assert summary["package_derivation"]["verified"] is True
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_load_safe"] is True
    assert summary["fixture_classification"] == "load_safe_fixture"
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["runtime_apply_allowed"] is False
    assert summary["runtime_apply_reason"] == DIAGNOSTIC_APPLY_REASON
    assert summary["runtime_apply_contract"] == {
        "apply_authority": "reports/operator_summary.json",
        "authority_scope": "current_package_operator_gate",
    }
    assert summary["no_block_failure_mode_summary"]["hard_block"] is False
    assert summary["no_block_failure_mode_summary"]["runtime_apply_reason"] == (
        DIAGNOSTIC_APPLY_REASON
    )
    assert not (
        Path(package["out"]) / "reports" / "runtime_apply_receipt.json"
    ).exists()

    _assert_global_semantic_invariants(package)
    _assert_deck_specific_invariants(str(deck["deck_name"]), package)


def test_exact_live_verified_fixture_requires_strict_validation_for_eligibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    deck = next(
        row for row in audited_decks() if row["deck_name"] == "ShadowPriest"
    )
    html = f"""
    <html>
      <head><title>ShadowPriest exact deck guide</title></head>
      <body><main>
        <time datetime="2026-07-27"></time>
        <h1>ShadowPriest guide</h1>
        <p>Deck code: {deck["deck_code"]}</p>
        <h2>Mulligan</h2>
        <p>Keep Voidtouched Attendant in the opening hand.</p>
        <p>Darkbishop Benedictus establishes Shadowform.</p>
      </main></body>
    </html>
    """.encode()
    monkeypatch.setattr(
        "hsconfig.source_acquisition._default_resolver",
        lambda _hostname: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "hsconfig.source_acquisition._fetch_with_validated_address",
        lambda _url, _timeout, _address: (200, "text/html", html),
    )
    out = tmp_path / "live-verified"
    runtime_root = tmp_path / "runtime"
    assert not runtime_root.exists()

    exit_code = main(
        [
            "configure",
            "--deck-name",
            str(deck["deck_name"]),
            "--deck-code",
            str(deck["deck_code"]),
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--online-source",
            "--auto-source",
            "--source-url",
            "https://example.test/exact-guide",
            "--current-date",
            "2026-07-27",
            "--json",
        ]
    )
    package = out / "04_package"
    summary = read_json(package / "reports" / "operator_summary.json")
    bundle = read_json(package / "reports" / "guide_claim_bundle.json")
    validation = validate_complete_package(package)
    gate = evaluate_apply_gate(package)

    assert exit_code == 0
    assert bundle["canonical_source_receipts"]
    assert all(
        receipt["acquisition_provenance"]["mode"] == "live_http"
        and receipt["acquisition_provenance"]["authority"] == "live_verified"
        for receipt in bundle["canonical_source_receipts"]
    )
    assert validation["status"] == "passed"
    assert validation["errors"] == []
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["source_apply_eligible"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert not runtime_root.exists()
    assert not (package / "reports" / "runtime_apply_receipt.json").exists()

    (package / "reports" / "globalvalues_profile.json").unlink()
    invalid_validation = validate_complete_package(package)
    invalid_gate = evaluate_apply_gate(package)

    assert invalid_validation["status"] == "failed"
    assert invalid_gate["status"] == "blocked"
    assert invalid_gate["allowed"] is False
    assert invalid_gate["reasons"][0]["reason"] == "strict_package_validation_failed"
