from __future__ import annotations

from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


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


def source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]:
    """Return the explicit source-claim policy matrix used by tests and docs."""
    missing = set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(_POLICY)
    extra = set(_POLICY) - set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    if missing or extra:
        raise RuntimeError(
            "source contract policy mismatch: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
    return {claim_kind: dict(row) for claim_kind, row in sorted(_POLICY.items())}

