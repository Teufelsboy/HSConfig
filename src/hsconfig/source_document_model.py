from __future__ import annotations

SUPPORTED_ATOMIC_CLAIM_KINDS = frozenset(
    {
        "archetype",
        "mulligan_keep",
        "mulligan_discard",
        "card_role",
        "targeting_rule",
        "combo_sequence",
        "gameplan_posture",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "tech_slot",
        "replacement_option",
        "discover_choice",
        "choose_one_choice",
    }
)

REQUIRED_SOURCE_KEYS = ("source_url", "source_title", "source_family", "retrieved_at")
REQUIRED_CLAIM_KEYS = ("claim_kind", "evidence_text_short", "source_confidence")

SUPPORTED_CLAIM_READINESS = frozenset(
    {
        "guide_backed",
        "source_backed_static_semantics",
        "archetype_inferred",
        "explicit_low_confidence",
        "generic_low_confidence",
        "contract_gap",
    }
)

SUPPORTED_SPECIFICITY_STATUSES = frozenset(
    {
        "deck_scoped",
        "card_specific",
        "multi_card_specific",
        "not_card_specific",
    }
)
