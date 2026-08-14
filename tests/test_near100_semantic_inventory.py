from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from hsconfig.semantic_inventory import canonical_semantic_claim, validate_semantic_inventory


_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "near100"


def _read_json(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURE_ROOT / name).read_text(encoding="utf-8"))


@pytest.fixture
def inventory() -> dict[str, Any]:
    return _read_json("current_semantic_inventory.json")


@pytest.fixture
def audited_catalog() -> dict[str, Any]:
    return json.loads(
        (Path(__file__).parents[1] / "docs" / "operator" / "audited-deck-catalog.json").read_text(
            encoding="utf-8"
        )
    )


@pytest.fixture
def score_contract() -> dict[str, Any]:
    return _read_json("score_metric_contract.json")


def _refresh_checksum(inventory: dict[str, Any]) -> None:
    content = {
        key: value for key, value in inventory.items() if key != "canonical_content_sha256"
    }
    canonical = json.dumps(content, separators=(",", ":"), sort_keys=True)
    inventory["canonical_content_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def test_near100_inventory_freezes_approved_counts(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    summary = validate_semantic_inventory(
        inventory,
        audited_catalog=audited_catalog["decks"],
    )
    assert summary.deck_count == 12
    assert summary.main_slot_count == 360
    assert summary.main_card_identity_count == 205
    assert summary.sideboard_module_count == 3
    assert summary.disposition_row_count == 208
    assert summary.claim_count == 316
    assert summary.globalvalues_decision_count == 456
    assert len(inventory["semantic_claims"]) == 316
    assert sum(len(deck["claims"]) for deck in inventory["decks"]) == 316
    assert all(
        row == canonical_semantic_claim(row)
        and len(row["claim_key"]) == 64
        and row["claim_key"] == row["claim_key"].lower()
        for row in inventory["semantic_claims"]
    )


def test_canonical_semantic_claim_uses_the_exact_five_field_full_sha_contract() -> None:
    row = canonical_semantic_claim(
        {
            "claim_kind": " mechanic_usage ",
            "evidence_text_short": " Draw   a card. ",
            "cards": ["B", "A", "A"],
            "lowered_surfaces": ["mulligan", "cardid", "cardid"],
            "source_title": " Søurce ",
            "unrelated_audit_field": "ignored",
        }
    )

    assert row == {
        "claim_key": "b6f6d26f63a1b02c659ee18232f89480098b18c5adb3421d39a966c1056e6460",
        "claim_kind": "mechanic_usage",
        "evidence_text_short": "Draw a card.",
        "cards": ["A", "B"],
        "lowered_surfaces": ["cardid", "mulligan"],
        "source_title": "Søurce",
    }


def test_inventory_rejects_semantic_substitution_after_embedded_checksum_rewrite(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    changed = copy.deepcopy(inventory)
    claim = changed["semantic_claims"][0]
    claim["evidence_text_short"] += " changed"
    claim.pop("claim_key")
    changed["semantic_claims"][0] = canonical_semantic_claim(claim)
    _refresh_checksum(changed)

    with pytest.raises(
        ValueError, match="semantic_inventory_approved_content_sha256_invalid"
    ):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])


def test_inventory_rejects_noncanonical_or_duplicate_semantic_claims(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    changed = copy.deepcopy(inventory)
    changed["semantic_claims"][0]["evidence_text_short"] += "  "
    _refresh_checksum(changed)
    with pytest.raises(ValueError, match="semantic_claim"):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])

    duplicated = copy.deepcopy(inventory)
    duplicated["semantic_claims"][1] = copy.deepcopy(duplicated["semantic_claims"][0])
    _refresh_checksum(duplicated)
    with pytest.raises(ValueError, match="semantic_claim_identity"):
        validate_semantic_inventory(duplicated, audited_catalog=audited_catalog["decks"])


@pytest.mark.parametrize("delta", [-1, 1])
def test_inventory_rejects_wrong_semantic_claim_count(
    inventory: dict[str, Any], audited_catalog: dict[str, Any], delta: int
) -> None:
    changed = copy.deepcopy(inventory)
    if delta < 0:
        changed["semantic_claims"].pop()
    else:
        changed["semantic_claims"].append(copy.deepcopy(changed["semantic_claims"][-1]))
    _refresh_checksum(changed)

    with pytest.raises(ValueError, match="semantic_claim_count"):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_inventory_rejects_open_semantic_claim_rows(
    inventory: dict[str, Any], audited_catalog: dict[str, Any], mutation: str
) -> None:
    changed = copy.deepcopy(inventory)
    if mutation == "missing":
        changed["semantic_claims"][0].pop("source_title")
    else:
        changed["semantic_claims"][0]["unexpected"] = True
    _refresh_checksum(changed)

    with pytest.raises(ValueError, match="semantic_claim_invalid"):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])


def test_score_contract_freezes_all_hard_minimums(
    score_contract: dict[str, Any],
) -> None:
    assert score_contract["metric_ids"] == [
        "static_contract_safety",
        "safe_visionai_lowering",
        "testability_and_assurance",
        "semantic_disposition_closure",
        "layered_pre_run_source_coverage",
        "architecture_and_maintainability",
        "slimness_and_coherence",
        "github_repository_polish",
        "workspace_hygiene",
    ]
    assert score_contract["minimums"] == [99, 99, 98, 100, 98, 96, 98, 98, 100]
    assert score_contract["overall_minimum"] == 98
    assert score_contract["gameplay_quality"] == "not_applicable"
    assert score_contract["open_p0_maximum"] == 0
    assert score_contract["open_p1_maximum"] == 0


def test_inventory_rejects_changed_canonical_content(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    inventory["decks"][0]["main_cards"][0]["count"] = 99

    with pytest.raises(ValueError, match="semantic_inventory_content_sha256_invalid"):
        validate_semantic_inventory(inventory, audited_catalog=audited_catalog["decks"])


def test_inventory_rejects_claim_substitution_after_embedded_checksum_rewrite(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    changed = copy.deepcopy(inventory)
    claim = changed["decks"][0]["claims"][0]
    substituted_claim_id = "claim_substituted_after_approval"
    claim["claim_id"] = substituted_claim_id
    claim["claim_key"] = (
        f"{changed['decks'][0]['deck_fingerprint']}:{substituted_claim_id}"
    )
    _refresh_checksum(changed)

    with pytest.raises(
        ValueError, match="semantic_inventory_approved_content_sha256_invalid"
    ):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])


def test_inventory_rejects_duplicate_card_identity_after_valid_checksum(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    changed = copy.deepcopy(inventory)
    changed["decks"][0]["main_cards"][1]["card_id"] = changed["decks"][0][
        "main_cards"
    ][0]["card_id"]
    _refresh_checksum(changed)

    with pytest.raises(ValueError, match="semantic_inventory_main_cards_invalid"):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])


def test_inventory_rejects_sideboard_owner_mismatch_after_valid_checksum(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    changed = copy.deepcopy(inventory)
    changed["decks"][7]["sideboard_modules"][0]["owner_card_id"] = "NOT_TOY_330"
    _refresh_checksum(changed)

    with pytest.raises(ValueError, match="semantic_inventory_sideboard_owner_invalid"):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])


def test_inventory_rejects_duplicate_claim_id_within_a_deck_after_valid_checksum(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    changed = copy.deepcopy(inventory)
    deck = changed["decks"][0]
    duplicate_claim_id = deck["claims"][0]["claim_id"]
    deck["claims"][1]["claim_id"] = duplicate_claim_id
    deck["claims"][1]["claim_key"] = (
        f"{deck['deck_fingerprint']}:{duplicate_claim_id}"
    )
    _refresh_checksum(changed)

    with pytest.raises(ValueError, match="semantic_inventory_claim_identity_invalid"):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])


def test_inventory_rejects_duplicate_global_claim_key_after_valid_checksum(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    changed = copy.deepcopy(inventory)
    changed["decks"][1]["claims"][0]["claim_key"] = changed["decks"][0]["claims"][0][
        "claim_key"
    ]
    _refresh_checksum(changed)

    with pytest.raises(ValueError, match="semantic_inventory_claim_key_invalid"):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])


def test_inventory_rejects_globalvalues_key_order_after_valid_checksum(
    inventory: dict[str, Any], audited_catalog: dict[str, Any]
) -> None:
    changed = copy.deepcopy(inventory)
    keys = changed["decks"][0]["globalvalues_decisions"]
    keys[0], keys[1] = keys[1], keys[0]
    _refresh_checksum(changed)

    with pytest.raises(ValueError, match="semantic_inventory_globalvalues_keys_invalid"):
        validate_semantic_inventory(changed, audited_catalog=audited_catalog["decks"])
