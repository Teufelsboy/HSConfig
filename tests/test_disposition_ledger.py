import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from hsconfig.disposition_ledger import build_disposition_ledger
from hsconfig.package_domain import CardDisposition, ClaimDisposition


def _card(
    card_id: str,
    *,
    lane: str = "A",
    zone: str = "main_deck",
    claim_ids: tuple[str, ...] = ("claim-1",),
) -> dict[str, object]:
    return {
        "composite_card_key": f"{zone}:{card_id}",
        "zone": zone,
        "official_semantics_canonical_json": (
            f'{{"GameCardId":"{card_id}"}}'
        ),
        "authority_lane": lane,
        "evidence_ids": ["evidence-1"],
        "claim_ids": list(claim_ids),
        "physical_owner": card_id,
    }


def _claim(
    card_id: str,
    *,
    claim_id: str = "claim-1",
    builder_state: str,
    deck_fingerprint: str = "deck-fingerprint",
    policy_id: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "deck_fingerprint": deck_fingerprint,
        "claim_id": claim_id,
        "claim_kind": "card_play",
        "evidence_id": "evidence-1",
        "composite_card_key": f"main_deck:{card_id}",
        "builder_state": builder_state,
    }
    if policy_id is not None:
        row["policy_id"] = policy_id
    return row


def test_physical_meaningful_row_wins_disposition_precedence():
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [
                {
                    "composite_card_key": "main_deck:CARD_001",
                    "zone": "main_deck",
                    "official_semantics_canonical_json": (
                        '{"GameCardId":"CARD_001"}'
                    ),
                    "authority_lane": "A",
                    "evidence_ids": ["evidence-1"],
                    "claim_ids": ["claim-1"],
                    "physical_owner": "CARD_001",
                }
            ],
        },
        claim_lifecycle_rows=[
            {
                "deck_fingerprint": "deck-fingerprint",
                "claim_id": "claim-1",
                "claim_kind": "card_play",
                "evidence_id": "evidence-1",
                "composite_card_key": "main_deck:CARD_001",
                "builder_state": "bot_delegated",
            }
        ],
        physical_emission_index={
            "main_deck:CARD_001": ["CARD_001.json"],
        },
        runtime_surface_ledger={
            "physical_emissions": [
                {
                    "composite_card_key": "main_deck:CARD_001",
                    "physical_owner": "CARD_001",
                    "relative_path": "CARD_001.json",
                    "meaningful": True,
                }
            ]
        },
    )

    assert len(ledger.cards) == 1
    assert ledger.cards[0].disposition is CardDisposition.RUNTIME_EMITTED
    assert ledger.cards[0].runtime_paths == ("CARD_001.json",)


def test_sideboard_module_is_analysis_only_without_runtime_paths():
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [
                _card(
                    "MODULE_001",
                    zone="sideboard_module",
                    claim_ids=("claim-module",),
                )
            ],
        },
        claim_lifecycle_rows=[
            {
                **_claim(
                    "MODULE_001",
                    claim_id="claim-module",
                    builder_state="suppressed_unsupported_surface",
                ),
                "composite_card_key": "sideboard_module:MODULE_001",
            }
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )

    assert ledger.cards[0].disposition is CardDisposition.ANALYSIS_ONLY_SIDEBOARD
    assert ledger.cards[0].runtime_paths == ()
    assert ledger.claims[0].disposition is ClaimDisposition.CONTRACT_ONLY


@pytest.mark.parametrize(
    ("builder_state", "expected"),
    [
        (
            "suppressed_unsupported_surface",
            CardDisposition.SUPPRESSED_UNSUPPORTED_SURFACE,
        ),
        (
            "suppressed_insufficient_authority",
            CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
        ),
    ],
)
def test_unsupported_and_insufficient_dispositions_remain_distinct(
    builder_state,
    expected,
):
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [_card("CARD_001")],
        },
        claim_lifecycle_rows=[
            _claim("CARD_001", builder_state=builder_state)
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )

    assert ledger.cards[0].disposition is expected
    assert ledger.claims[0].disposition.value == expected.value


@pytest.mark.parametrize(
    ("lane", "policy_id", "expected"),
    [
        ("E", "BOT_NATIVE_PRE_RUN", CardDisposition.BOT_DELEGATED),
        ("A", "BOT_NATIVE_PRE_RUN", CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY),
        ("E", None, CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY),
    ],
)
def test_bot_delegation_requires_intentional_lane_e_policy(
    lane,
    policy_id,
    expected,
):
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [_card("CARD_001", lane=lane)],
        },
        claim_lifecycle_rows=[
            _claim(
                "CARD_001",
                builder_state="bot_delegated",
                policy_id=policy_id,
            )
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )

    assert ledger.cards[0].disposition is expected
    assert ledger.claims[0].disposition.value == expected.value


def test_missing_lifecycle_claim_receives_one_blocking_disposition():
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [
                _card(
                    "CARD_001",
                    claim_ids=("claim-1", "claim-missing"),
                )
            ],
        },
        claim_lifecycle_rows=[
            _claim(
                "CARD_001",
                claim_id="claim-1",
                builder_state="suppressed_unsupported_surface",
            )
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )

    rows = {row.claim_id: row for row in ledger.claims}
    assert set(rows) == {"claim-1", "claim-missing"}
    assert (
        rows["claim-missing"].disposition
        is ClaimDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY
    )
    assert rows["claim-missing"].reason_code == "missing_claim_lifecycle"


def test_duplicate_claim_lifecycle_is_rejected_instead_of_double_counted():
    duplicate = _claim(
        "CARD_001",
        builder_state="suppressed_unsupported_surface",
    )

    with pytest.raises(ValueError, match="claim_disposition_duplicate"):
        build_disposition_ledger(
            evidence_contract={
                "deck_fingerprint": "deck-fingerprint",
                "cards": [_card("CARD_001")],
            },
            claim_lifecycle_rows=[duplicate, dict(duplicate)],
            physical_emission_index={},
            runtime_surface_ledger={"physical_emissions": []},
        )


def test_extra_claim_lifecycle_is_rejected_instead_of_entering_the_ledger():
    with pytest.raises(
        ValueError,
        match="claim_lifecycle_not_in_evidence_contract",
    ):
        build_disposition_ledger(
            evidence_contract={
                "deck_fingerprint": "deck-fingerprint",
                "cards": [_card("CARD_001")],
            },
            claim_lifecycle_rows=[
                _claim(
                    "CARD_001",
                    builder_state="suppressed_unsupported_surface",
                ),
                _claim(
                    "CARD_001",
                    claim_id="claim-extra",
                    builder_state="suppressed_unsupported_surface",
                ),
            ],
            physical_emission_index={},
            runtime_surface_ledger={"physical_emissions": []},
        )


def test_cross_deck_claim_lifecycle_is_rejected():
    with pytest.raises(
        ValueError,
        match="claim_lifecycle_deck_fingerprint_mismatch",
    ):
        build_disposition_ledger(
            evidence_contract={
                "deck_fingerprint": "deck-a",
                "cards": [_card("CARD_001")],
            },
            claim_lifecycle_rows=[
                _claim(
                    "CARD_001",
                    builder_state="suppressed_unsupported_surface",
                    deck_fingerprint="deck-b",
                )
            ],
            physical_emission_index={},
            runtime_surface_ledger={"physical_emissions": []},
        )


def test_raw_claim_ids_are_scoped_by_their_deck_fingerprint():
    ledgers = [
        build_disposition_ledger(
            evidence_contract={
                "deck_fingerprint": deck_fingerprint,
                "cards": [_card("CARD_001")],
            },
            claim_lifecycle_rows=[
                _claim(
                    "CARD_001",
                    builder_state="suppressed_unsupported_surface",
                    deck_fingerprint=deck_fingerprint,
                )
            ],
            physical_emission_index={},
            runtime_surface_ledger={"physical_emissions": []},
        )
        for deck_fingerprint in ("deck-a", "deck-b")
    ]

    claim_identities = {
        (ledger.claims[0].deck_fingerprint, ledger.claims[0].claim_id)
        for ledger in ledgers
    }
    assert claim_identities == {
        ("deck-a", "claim-1"),
        ("deck-b", "claim-1"),
    }


def test_lifecycle_runtime_path_cannot_self_attest_physical_emission():
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [_card("CARD_001")],
        },
        claim_lifecycle_rows=[
            {
                **_claim(
                    "CARD_001",
                    builder_state="runtime_emitted",
                ),
                "runtime_paths": ["FORGED.json"],
            }
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )

    assert ledger.cards[0].disposition is not CardDisposition.RUNTIME_EMITTED
    assert ledger.cards[0].runtime_paths == ()
    assert ledger.claims[0].disposition is not ClaimDisposition.RUNTIME_EMITTED
    assert ledger.claims[0].runtime_paths == ()


def test_wrong_physical_owner_cannot_attest_runtime_emission():
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [_card("CARD_001")],
        },
        claim_lifecycle_rows=[
            _claim(
                "CARD_001",
                builder_state="suppressed_unsupported_surface",
            )
        ],
        physical_emission_index={
            "main_deck:CARD_001": ["CARD_001.json"],
        },
        runtime_surface_ledger={
            "physical_emissions": [
                {
                    "composite_card_key": "main_deck:CARD_001",
                    "physical_owner": "OTHER_CARD",
                    "relative_path": "CARD_001.json",
                    "meaningful": True,
                }
            ]
        },
    )

    assert ledger.cards[0].disposition is not CardDisposition.RUNTIME_EMITTED
    assert ledger.cards[0].runtime_paths == ()
    assert ledger.claims[0].disposition is not ClaimDisposition.RUNTIME_EMITTED
    assert ledger.claims[0].runtime_paths == ()


def test_approved_inventory_has_one_row_per_exact_card_and_claim():
    inventory = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "near100"
            / "current_semantic_inventory.json"
        ).read_text(encoding="utf-8")
    )
    ledgers = []
    for deck in inventory["decks"]:
        inventory_cards = [
            *deck["main_cards"],
            *deck["sideboard_modules"],
        ]
        claims_by_card = {
            card["composite_card_key"]: []
            for card in inventory_cards
        }
        for index, claim in enumerate(deck["claims"]):
            card = inventory_cards[index % len(inventory_cards)]
            claims_by_card[card["composite_card_key"]].append(
                claim["claim_id"]
            )
        evidence_cards = []
        lifecycle_rows = []
        for card in inventory_cards:
            composite_key = card["composite_card_key"]
            zone = (
                "sideboard_module"
                if ":sideboard_module:" in composite_key
                else "main_deck"
            )
            claim_ids = claims_by_card[composite_key]
            evidence_cards.append(
                {
                    "composite_card_key": composite_key,
                    "zone": zone,
                    "official_semantics_canonical_json": (
                        f'{{"GameCardId":"{card["card_id"]}"}}'
                    ),
                    "authority_lane": "A",
                    "evidence_ids": ["inventory"],
                    "claim_ids": claim_ids,
                    "physical_owner": card["card_id"],
                }
            )
            lifecycle_rows.extend(
                {
                    "deck_fingerprint": deck["deck_fingerprint"],
                    "claim_id": claim_id,
                    "claim_kind": "inventory_claim",
                    "evidence_id": "inventory",
                    "composite_card_key": composite_key,
                    "builder_state": "suppressed_unsupported_surface",
                }
                for claim_id in claim_ids
            )
        ledgers.append(
            build_disposition_ledger(
                evidence_contract={
                    "deck_fingerprint": deck["deck_fingerprint"],
                    "cards": evidence_cards,
                },
                claim_lifecycle_rows=lifecycle_rows,
                physical_emission_index={},
                runtime_surface_ledger={"physical_emissions": []},
            )
        )

    card_keys = [
        (ledger.deck_fingerprint, row.composite_card_key)
        for ledger in ledgers
        for row in ledger.cards
    ]
    claim_keys = [
        (ledger.deck_fingerprint, row.claim_id)
        for ledger in ledgers
        for row in ledger.claims
    ]
    assert len(card_keys) == len(set(card_keys)) == 208
    assert len(claim_keys) == len(set(claim_keys)) == 316


def test_ledger_is_deeply_immutable_and_hash_is_order_independent():
    card_a = _card("CARD_A", claim_ids=("claim-a",))
    card_b = _card("CARD_B", claim_ids=("claim-b",))
    claim_a = _claim(
        "CARD_A",
        claim_id="claim-a",
        builder_state="suppressed_unsupported_surface",
    )
    claim_b = _claim(
        "CARD_B",
        claim_id="claim-b",
        builder_state="suppressed_insufficient_authority",
    )
    first = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [card_b, card_a],
        },
        claim_lifecycle_rows=[claim_b, claim_a],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )
    second = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [card_a, card_b],
        },
        claim_lifecycle_rows=[claim_a, claim_b],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )
    card_a["claim_ids"].append("mutated-after-build")

    assert first == second
    assert first.content_sha256 == second.content_sha256
    assert first.cards[0].claim_ids == ("claim-a",)
    with pytest.raises(FrozenInstanceError):
        first.cards[0].reason_code = "mutated"


def test_disposition_ledger_rejects_a_forged_content_hash():
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [_card("CARD_001")],
        },
        claim_lifecycle_rows=[
            _claim(
                "CARD_001",
                builder_state="suppressed_unsupported_surface",
            )
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )

    with pytest.raises(
        ValueError,
        match="disposition_ledger_content_sha256_invalid",
    ):
        replace(ledger, content_sha256=f"sha256:{'0' * 64}")
