from __future__ import annotations

from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


OPERATOR_GATE_IMPACT = "diagnostic_only"
COMMON_CLAIM_FIELDS = ("claim_kind", "claim_readiness", "trust_ceiling")
CARD_CLAIM_FIELDS = (*COMMON_CLAIM_FIELDS, "cards")
SEMANTIC_QUALIFIER_USAGE_BY_CLAIM_KIND = {
    "mulligan_keep": "timing and zone qualifiers may suppress start-of-game non-hand effects",
    "targeting_rule": "target_scope is diagnostic metadata for supported CardID targeting claims",
    "combo_sequence": "timing and state requirements are diagnostic metadata for Combo.json claims",
}

_POLICY: dict[str, dict[str, object]] = {
    "archetype": {
        "lane": "report_only",
        "allowed_surfaces": (),
        "operator_meaning": "Archetype context may inform reports, not runtime rows.",
    },
    "mulligan_keep": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("mulligan",),
        "operator_meaning": (
            "Exact opening-hand keep authority, subject to start-of-game "
            "non-hand suppression."
        ),
    },
    "mulligan_discard": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("mulligan",),
        "operator_meaning": "Exact opening-hand discard authority.",
    },
    "card_role": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": (
            "Can lower only when the role maps to a documented card behavior block."
        ),
    },
    "targeting_rule": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": (
            "Can lower to card behavior when target and block identity are supported."
        ),
    },
    "combo_sequence": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("combo",),
        "operator_meaning": "Can lower only as an explicit ordered Combo.json sequence.",
    },
    "gameplan_posture": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("globalvalues",),
        "operator_meaning": (
            "Can lower only through source-backed Step 1 posture overlays."
        ),
    },
    "hero_power_transform": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": (
            "Preserve hero-power-transform semantics; it is not a mulligan keep by itself."
        ),
    },
    "mechanic_usage": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": (
            "Can lower only when the mechanic maps to a documented CardID surface."
        ),
    },
    "known_bad_pattern": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": (
            "Can lower only when the bad pattern maps to a documented negative "
            "behavior row."
        ),
    },
    "tech_slot": {
        "lane": "report_only",
        "allowed_surfaces": (),
        "operator_meaning": "Deck construction advice; not a pre-run runtime JSON row.",
    },
    "replacement_option": {
        "lane": "report_only",
        "allowed_surfaces": (),
        "operator_meaning": "Deck replacement advice; not a pre-run runtime JSON row.",
    },
    "discover_choice": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": (
            "Can lower only when exact Discover option identity is source-backed."
        ),
    },
    "choose_one_choice": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": (
            "Can lower only when exact Choose One option identity is source-backed."
        ),
    },
    "globalvalue_numeric_tuning": {
        "lane": "runtime_evidence_required",
        "allowed_surfaces": (),
        "operator_meaning": (
            "Valid evidence, but Step 1 must wait for runtime evidence before "
            "numeric tuning."
        ),
    },
}


_POLICY_DETAILS: dict[str, tuple[tuple[str, ...], bool, str]] = {
    "archetype": (COMMON_CLAIM_FIELDS, False, "report_only"),
    "mulligan_keep": (CARD_CLAIM_FIELDS, True, "claim_kind_not_mulligan_surface"),
    "mulligan_discard": (CARD_CLAIM_FIELDS, True, "claim_kind_not_mulligan_surface"),
    "card_role": (CARD_CLAIM_FIELDS, True, "requires_supported_cardid_surface"),
    "targeting_rule": (CARD_CLAIM_FIELDS, True, "requires_supported_cardid_surface"),
    "combo_sequence": (
        (*CARD_CLAIM_FIELDS, "sequence"),
        True,
        "requires_complete_combo_sequence",
    ),
    "gameplan_posture": (
        COMMON_CLAIM_FIELDS,
        True,
        "claim_kind_not_globalvalues_surface",
    ),
    "hero_power_transform": (
        CARD_CLAIM_FIELDS,
        True,
        "requires_supported_cardid_surface",
    ),
    "mechanic_usage": (
        (*CARD_CLAIM_FIELDS, "mechanic"),
        True,
        "requires_supported_cardid_surface",
    ),
    "known_bad_pattern": (
        CARD_CLAIM_FIELDS,
        True,
        "requires_supported_cardid_surface",
    ),
    "tech_slot": (CARD_CLAIM_FIELDS, False, "report_only"),
    "replacement_option": (CARD_CLAIM_FIELDS, False, "report_only"),
    "discover_choice": (
        (*CARD_CLAIM_FIELDS, "option_card_id"),
        True,
        "requires_exact_option_identity",
    ),
    "choose_one_choice": (
        (*CARD_CLAIM_FIELDS, "option_card_id"),
        True,
        "requires_exact_option_identity",
    ),
    "globalvalue_numeric_tuning": (
        (*COMMON_CLAIM_FIELDS, "key"),
        False,
        "requires_runtime_evidence",
    ),
}


def source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]:
    """Return the explicit source-claim policy matrix used by tests and docs."""
    missing = set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(_POLICY)
    extra = set(_POLICY) - set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    missing_details = set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(_POLICY_DETAILS)
    extra_details = set(_POLICY_DETAILS) - set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    if missing or extra or missing_details or extra_details:
        raise RuntimeError(
            "source contract policy mismatch: "
            f"missing={sorted(missing)} extra={sorted(extra)} "
            f"missing_details={sorted(missing_details)} "
            f"extra_details={sorted(extra_details)}"
        )
    return {
        claim_kind: _with_contract_metadata(claim_kind, row)
        for claim_kind, row in sorted(_POLICY.items())
    }


def _with_contract_metadata(
    claim_kind: str, row: dict[str, object]
) -> dict[str, object]:
    required_fields, runtime_lowerable, default_suppression_reason = _POLICY_DETAILS[
        claim_kind
    ]
    enriched = dict(row)
    enriched["semantic_lane"] = str(row["lane"])
    enriched["required_fields"] = tuple(required_fields)
    enriched["runtime_lowerable"] = bool(runtime_lowerable)
    enriched["default_suppression_reason"] = default_suppression_reason
    enriched["operator_gate_impact"] = OPERATOR_GATE_IMPACT
    enriched["semantic_qualifier_usage"] = SEMANTIC_QUALIFIER_USAGE_BY_CLAIM_KIND.get(
        claim_kind, "diagnostic context only"
    )
    return enriched
