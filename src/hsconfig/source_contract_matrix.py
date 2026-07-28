from __future__ import annotations

from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS
from hsconfig.visionai_registry import CLAIM_SURFACE_REGISTRY


OPERATOR_GATE_IMPACT = "diagnostic_only"
COMMON_CLAIM_FIELDS = ("claim_kind", "claim_readiness", "trust_ceiling")
CARD_CLAIM_FIELDS = (*COMMON_CLAIM_FIELDS, "cards")
SEMANTIC_QUALIFIER_USAGE_BY_CLAIM_KIND = {
    "mulligan_keep": "timing and zone qualifiers may suppress start-of-game non-hand effects",
    "targeting_rule": "target_scope is diagnostic metadata for supported CardID targeting claims",
    "combo_sequence": "timing and state requirements are diagnostic metadata for Combo.json claims",
}

_OPERATOR_MEANING_BY_CLAIM_KIND = {
    "archetype": "Archetype context may inform reports, not runtime rows.",
    "mulligan_keep": (
            "Exact opening-hand keep authority, subject to start-of-game "
            "non-hand suppression."
    ),
    "mulligan_discard": "Exact opening-hand discard authority.",
    "card_role": (
        "Can lower only when the role maps to a documented card behavior block."
    ),
    "targeting_rule": (
        "Can lower to card behavior when target and block identity are supported."
    ),
    "combo_sequence": (
        "Can lower only as an explicit ordered Combo.json sequence."
    ),
    "gameplan_posture": (
            "Can lower only through source-backed Step 1 posture overlays."
    ),
    "hero_power_transform": (
            "Preserve hero-power-transform semantics; it is not a mulligan keep by itself."
    ),
    "mechanic_usage": (
            "Can lower only when the mechanic maps to a documented CardID surface."
    ),
    "known_bad_pattern": (
            "Can lower only when the bad pattern maps to a documented negative "
            "behavior row."
    ),
    "tech_slot": "Deck construction advice; not a pre-run runtime JSON row.",
    "replacement_option": (
        "Deck replacement advice; not a pre-run runtime JSON row."
    ),
    "discover_choice": (
            "Can lower only when exact Discover option identity is source-backed."
    ),
    "choose_one_choice": (
            "Can lower only when exact Choose One option identity is source-backed."
    ),
    "globalvalue_numeric_tuning": (
        "Valid evidence, but Step 1 must wait for runtime evidence before "
        "numeric tuning."
    ),
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
    missing = set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(CLAIM_SURFACE_REGISTRY)
    extra = set(CLAIM_SURFACE_REGISTRY) - set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    missing_meanings = set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(
        _OPERATOR_MEANING_BY_CLAIM_KIND
    )
    extra_meanings = set(_OPERATOR_MEANING_BY_CLAIM_KIND) - set(
        SUPPORTED_ATOMIC_CLAIM_KINDS
    )
    missing_details = set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(_POLICY_DETAILS)
    extra_details = set(_POLICY_DETAILS) - set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    ambiguous_lanes = sorted(
        claim_kind
        for claim_kind, rule in CLAIM_SURFACE_REGISTRY.items()
        if len(rule.required_authority_lanes) != 1
    )
    if (
        missing
        or extra
        or missing_meanings
        or extra_meanings
        or missing_details
        or extra_details
        or ambiguous_lanes
    ):
        raise RuntimeError(
            "source contract policy mismatch: "
            f"missing={sorted(missing)} extra={sorted(extra)} "
            f"missing_meanings={sorted(missing_meanings)} "
            f"extra_meanings={sorted(extra_meanings)} "
            f"missing_details={sorted(missing_details)} "
            f"extra_details={sorted(extra_details)} "
            f"ambiguous_lanes={ambiguous_lanes}"
        )
    return {
        claim_kind: _with_contract_metadata(claim_kind)
        for claim_kind in sorted(CLAIM_SURFACE_REGISTRY)
    }


def _with_contract_metadata(claim_kind: str) -> dict[str, object]:
    rule = CLAIM_SURFACE_REGISTRY[claim_kind]
    lane = rule.required_authority_lanes[0]
    required_fields, runtime_lowerable, default_suppression_reason = _POLICY_DETAILS[
        claim_kind
    ]
    return {
        "lane": lane,
        "allowed_surfaces": tuple(
            surface.removesuffix(".json").lower()
            for surface in rule.allowed_surfaces
        ),
        "operator_meaning": _OPERATOR_MEANING_BY_CLAIM_KIND[claim_kind],
        "semantic_lane": lane,
        "required_fields": tuple(required_fields),
        "runtime_lowerable": bool(runtime_lowerable),
        "default_suppression_reason": default_suppression_reason,
        "operator_gate_impact": OPERATOR_GATE_IMPACT,
        "semantic_qualifier_usage": (
            SEMANTIC_QUALIFIER_USAGE_BY_CLAIM_KIND.get(
                claim_kind, "diagnostic context only"
            )
        ),
    }


def source_contract_vocabulary_rows() -> tuple[dict[str, object], ...]:
    """Return a stable diagnostic projection of the source-contract policy."""
    rows: list[dict[str, object]] = []
    for claim_kind, policy in source_contract_policy_by_claim_kind().items():
        allowed_surfaces = tuple(str(surface) for surface in policy["allowed_surfaces"])
        rows.append(
            {
                "claim_kind": claim_kind,
                "semantic_lane": str(policy["semantic_lane"]),
                "allowed_surfaces": allowed_surfaces,
                "runtime_files": CLAIM_SURFACE_REGISTRY[
                    claim_kind
                ].allowed_surfaces,
                "runtime_lowerable": bool(policy["runtime_lowerable"]),
                "default_suppression_reason": str(policy["default_suppression_reason"]),
                "operator_gate_impact": str(policy["operator_gate_impact"]),
                "semantic_qualifier_usage": str(policy["semantic_qualifier_usage"]),
            }
        )
    return tuple(rows)
