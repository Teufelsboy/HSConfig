from __future__ import annotations

from hsconfig.research_result_validator import (
    validate_fields_yaml_payload,
    validate_research_result_payload,
)


def test_research_result_validator_accepts_complete_partial_result() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "PirateDH",
            "archetype": "Wild Pirate Demon Hunter",
            "current_deck_sources": [
                {
                    "url": "https://hearthstone-decks.net/example",
                    "source_family": "decklist_or_stats_only",
                    "promotes_strong": False,
                }
            ],
            "guide_sources": [],
            "source_strength": "decklist_or_stats_only",
            "lowerable_claim_kinds": [],
            "non_promoting_support": [
                "current list context exists but no full-text mulligan claim"
            ],
            "first_missing_source_action": "add_card_specific_source_claim",
            "notes": "Keep partial until exact guide text exists.",
        }
    )

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["source_status_apply_blocking"] is False


def test_research_result_validator_rejects_unknown_source_strength() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "PirateDH",
            "archetype": "Wild Pirate Demon Hunter",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "strong_enough_because_current",
            "lowerable_claim_kinds": [],
            "non_promoting_support": [],
            "first_missing_source_action": "none",
            "notes": "Invalid strength.",
        }
    )

    assert result["valid"] is False
    assert "invalid_source_strength" in result["errors"]
    assert result["source_status_apply_blocking"] is False


def test_research_result_validator_rejects_strong_without_lowerable_claims() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "ShadowPriest",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [
                {
                    "url": "https://example.test/shadow",
                    "source_family": "exact_full_text_guide",
                    "promotes_strong": True,
                }
            ],
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": [],
            "non_promoting_support": [],
            "first_missing_source_action": "none",
            "notes": "Missing lowerable claims.",
        }
    )

    assert result["valid"] is False
    assert "strong_requires_lowerable_claim_kinds" in result["errors"]


def test_research_result_validator_rejects_strong_without_full_text_visibility() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "ShadowPriest",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "snippet_only",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "first_missing_source_action": "none",
            "notes": "Snippet only is not strong.",
        }
    )

    assert result["valid"] is False
    assert "strong_requires_full_text_visibility" in result["errors"]
    assert result["source_status_apply_blocking"] is False


def test_research_result_validator_rejects_strong_with_default_only_surfaces() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "ShadowPriest",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "default_only_runtime_surfaces": ["mulligan"],
            "first_missing_source_action": "none",
            "notes": "Default-only surfaces cannot be strong.",
        }
    )

    assert result["valid"] is False
    assert "strong_requires_no_default_only_runtime_surfaces" in result["errors"]
    assert result["source_status_apply_blocking"] is False


def test_research_result_validator_rejects_malformed_lowerable_claim_kinds() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "ShadowPriest",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": None,
            "non_promoting_support": [],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "notes": "Malformed claim-kind collection.",
        }
    )

    assert result["valid"] is False
    assert "lowerable_claim_kinds_must_be_list" in result["errors"]
    assert result["source_status_apply_blocking"] is False


def test_research_result_validator_rejects_strong_without_default_only_surfaces() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "ShadowPriest",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "first_missing_source_action": "none",
            "notes": "Strong snapshots must declare clean default-only surfaces.",
        }
    )

    assert result["valid"] is False
    assert "strong_requires_explicit_empty_default_only_runtime_surfaces" in result["errors"]
    assert result["source_status_apply_blocking"] is False


def test_research_result_validator_rejects_strong_with_non_list_default_only_surfaces() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "ShadowPriest",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "default_only_runtime_surfaces": "mulligan",
            "first_missing_source_action": "none",
            "notes": "Default-only surfaces must be a clean list.",
        }
    )

    assert result["valid"] is False
    assert "default_only_runtime_surfaces_must_be_list" in result["errors"]
    assert result["source_status_apply_blocking"] is False


def test_fields_yaml_validator_catches_empty_or_malformed_field_map() -> None:
    result = validate_fields_yaml_payload({"fields": []})

    assert result["valid"] is False
    assert result["field_count"] == 0
    assert "fields_must_be_mapping" in result["errors"]


def test_fields_yaml_validator_accepts_hsconfig_field_contract() -> None:
    result = validate_fields_yaml_payload(
        {
            "fields": {
                "deck_name": {"type": "string"},
                "archetype": {"type": "string"},
                "current_deck_sources": {"type": "array"},
                "guide_sources": {"type": "array"},
                "source_strength": {"type": "string"},
                "lowerable_claim_kinds": {"type": "array"},
                "non_promoting_support": {"type": "array"},
                "first_missing_source_action": {"type": "string"},
                "notes": {"type": "string"},
            }
        }
    )

    assert result["valid"] is True
    assert result["field_count"] == 9
    assert result["errors"] == []
