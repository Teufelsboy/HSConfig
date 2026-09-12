"""Pure schema4 admission policy; no runtime, clock or source-fetch authority."""

from collections import Counter
from collections.abc import Mapping
import re
from types import MappingProxyType

from hsconfig.condition_format import ALLOWED_ATOM_PATTERNS, classify_runtime_condition
from hsconfig.mulligan_selector import normalize_mulligan_selector
from hsconfig.runtime_entity_owner import (
    linked_runtime_entity_semantic_surface,
    runtime_entity_owner_relation_is_authorized,
)
from hsconfig.starter_card_facts import validate_card_facts
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS, runtime_block_support


_COMMON_ATOMS = frozenset({"hand", "opponent_class"})
_SEMANTIC_PHASE_ATOMS = MappingProxyType({
    "Mulligan": _COMMON_ATOMS | {"opening"},
    "GlobalValues": _COMMON_ATOMS,
    "Combo": _COMMON_ATOMS,
    **{block: _COMMON_ATOMS for block in CARD_BEHAVIOR_BLOCKS},
    "BeforePhysicalAttackBonus": _COMMON_ATOMS | {"target"},
    "BeforeBattlecryTargetBonus": _COMMON_ATOMS | {"target"},
    "OnDiscoverCardBonus": _COMMON_ATOMS | {"discover"},
})
_OWNER_TYPES = MappingProxyType({
    "BeforeUseHeroPowerBonus": frozenset({"HERO_POWER"}),
    "BeforePhysicalAttackBonus": frozenset({"MINION", "HERO"}),
    "BeforeOverkilledBonus": frozenset({"MINION"}),
    "OnBoardBonus": frozenset({"MINION", "WEAPON", "HERO_POWER", "HERO"}),
})


def semantic_runtime_policy() -> dict:
    """Return an independent serializable description of the closed policy."""
    return {
        "policy_id": "hsconfig-starter-semantics-v1",
        "runtime_grammar_version": "visionai-runtime-v1",
        "condition_atom_families_by_phase": {
            phase: sorted(atoms) for phase, atoms in sorted(_SEMANTIC_PHASE_ATOMS.items())
        },
        "condition_requirements": [
            "raw_nonempty_canonical_string", "explicit_wildcard_allowed",
            "no_mixed_and_or", "no_coin_and_nocoin", "no_legacy_board_alias",
        ],
        "owner_types_by_block": {
            block: sorted(types) for block, types in sorted(_OWNER_TYPES.items())
        },
        "owner_capabilities_by_block": {
            "BeforeBattlecryTargetBonus": "known_BATTLECRY_and_integer_REQ_TARGET_TO_PLAY",
            "OnDiscoverCardBonus": "physical_self_known_DISCOVER",
            "OnChooseOneCardBonus": "physical_self_known_CHOOSE_ONE",
        },
        "behavior_block_source_backing": {
            block: runtime_block_support(block)["source_backing"]
            for block in sorted(CARD_BEHAVIOR_BLOCKS)
        },
        "ownership": "physical_main_source_and_existing_authorized_runtime_relation",
        "other_blocks": "existing_authorized_owner_without_new_type_or_mechanic_requirement",
        "patch_compatibility": "unknown",
    }


def semantic_atom_family(atom: str) -> str:
    """Classify only exact atoms admitted by the unchanged shared grammar."""
    if not any(pattern.fullmatch(atom) for pattern in ALLOWED_ATOM_PATTERNS):
        raise ValueError("starter_candidate_condition_invalid")
    if atom == "*":
        return "wildcard"
    if atom in {"coin", "nocoin"}:
        return "opening"
    for prefix, family in (
        ("my_hand(", "hand"), ("opp_hero(", "opponent_class"),
        ("my_target(", "target"), ("my_discover(", "discover"),
        ("my_minion(", "legacy_board_alias"),
    ):
        if atom.startswith(prefix):
            return family
    raise ValueError("starter_candidate_condition_invalid")


def validate_semantic_condition(value: object, *, phase: str) -> str:
    """Apply schema4 phase policy without ever coercing a supplied condition."""
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("starter_candidate_condition_invalid")
    lowered = classify_runtime_condition(value)
    if lowered.status != "runtime_safe" or lowered.value != value:
        raise ValueError("starter_candidate_condition_invalid")
    if type(phase) is not str or phase not in _SEMANTIC_PHASE_ATOMS:
        raise ValueError("starter_candidate_condition_phase_invalid")
    if value == "*":
        return value
    if " AND " in value and " OR " in value:
        raise ValueError("starter_candidate_condition_mixed_logic")
    atoms = re.split(r"\s+(?:AND|OR)\s+", value)
    if " AND " in value and {"coin", "nocoin"} <= set(atoms):
        raise ValueError("starter_candidate_condition_contradiction")
    for atom in atoms:
        family = semantic_atom_family(atom)
        if family == "legacy_board_alias" or family not in _SEMANTIC_PHASE_ATOMS[phase]:
            raise ValueError("starter_candidate_condition_context_invalid")
    return value


def validate_semantic_owner(context_value: Mapping, row: Mapping) -> None:
    """Require physical ownership, exact authorization and known surface facts."""
    validate_card_facts({
        key: context_value[key]
        for key in ("cards", "card_metadata", "sideboards", "linked_entities")
    })
    physical = {card["card_id"] for card in context_value["cards"]}
    source = row.get("source_card_id")
    runtime = row.get("runtime_card_id")
    link = row.get("link_kind")
    block = row.get("behavior_block")
    if type(source) is not str or source not in physical:
        raise ValueError("starter_candidate_card_id_unknown")
    if type(block) is not str or block not in CARD_BEHAVIOR_BLOCKS:
        raise ValueError("starter_candidate_behavior_block_invalid")
    if not all(type(value) is str and value for value in (runtime, link)):
        raise ValueError("starter_candidate_runtime_owner_unauthorized")
    if link == "self":
        authorized = source == runtime and not (
            source == "SW_448" and block == "BeforeUseHeroPowerBonus"
        )
    else:
        reason = linked_runtime_entity_semantic_surface(behavior_block=block, link_kind=link)
        authorized = reason is not None and runtime_entity_owner_relation_is_authorized(
            source_card_id=source, runtime_card_id=runtime,
            link_kind=link, semantic_reason=reason,
        ) and any(
            relation == {"source_card_id": source, "card_id": runtime,
                         "link_kind": link, "status": "resolved"}
            for relation in context_value["linked_entities"]
        )
    if not authorized:
        raise ValueError("starter_candidate_runtime_owner_unauthorized")
    owner = context_value["card_metadata"][runtime]
    if block in _OWNER_TYPES and owner["type"] not in _OWNER_TYPES[block]:
        raise ValueError("starter_candidate_surface_owner_unproven")
    mechanics = owner["mechanics"]
    if block == "BeforeBattlecryTargetBonus":
        requirements = owner["play_requirements"]
        proven = (
            mechanics is not None and "BATTLECRY" in mechanics
            and requirements is not None
            and type(requirements.get("REQ_TARGET_TO_PLAY")) is int
        )
    elif block in {"OnDiscoverCardBonus", "OnChooseOneCardBonus"}:
        required = "DISCOVER" if block == "OnDiscoverCardBonus" else "CHOOSE_ONE"
        proven = source == runtime and link == "self" and mechanics is not None and required in mechanics
    else:
        proven = True
    if not proven:
        raise ValueError("starter_candidate_surface_owner_unproven")


def semantic_selector(row, physical_cards):
    """Canonical alternatives or opening-hand conjunction with exact copies."""
    normalized = normalize_mulligan_selector(row)
    kind = normalized.get("selector_kind")
    cards = normalized.get("selector_cards")
    if not normalized.get("supported") or kind not in {"card", "card_list", "plus_combo"}:
        raise ValueError("starter_candidate_mulligan_selector_invalid")
    if not isinstance(cards, list) or not cards or any(card not in physical_cards for card in cards):
        raise ValueError("starter_candidate_mulligan_card_invalid")
    if kind == "card_list" and len(cards) != len(set(cards)):
        raise ValueError("starter_candidate_mulligan_selector_duplicate_member")
    counts = Counter(cards)
    if kind == "plus_combo" and any(count > physical_cards[card] for card, count in counts.items()):
        raise ValueError("starter_candidate_mulligan_copy_count_exceeded")
    members = tuple(sorted(counts.items()))
    expanded = [card for card, count in members for _ in range(count)]
    selector = "+".join(expanded) if kind == "plus_combo" else ",".join(expanded)
    return {
        "selector_kind": kind, "selector": selector,
        "selector_multiset": [{"card_id": card, "count": count} for card, count in members],
        "selector_cards": tuple(card for card, _ in members),
    }


def validate_rule_basis(row, *, assumptions, applicable_refs):
    """Validate one closed evidence/inference basis against explicit authority."""
    if type(row) is not dict or set(row) != {"basis", "evidence_refs", "assumption"}:
        raise ValueError("starter_candidate_rule_justifications_invalid")
    refs = row["evidence_refs"]
    if type(refs) is not list or any(type(ref) is not str or ref not in applicable_refs for ref in refs) or len(refs) != len(set(refs)):
        raise ValueError("starter_candidate_rule_evidence_invalid")
    if row["basis"] == "evidence":
        valid = bool(refs) and row["assumption"] is None
    elif row["basis"] == "inference":
        assumption = row["assumption"]
        valid = type(assumption) is str and bool(assumption.strip()) and assumption == assumption.strip() and assumption in assumptions
    else:
        valid = False
    if not valid:
        raise ValueError("starter_candidate_rule_justifications_invalid")


def semantic_rule_justifications(value, *, physical_rule_ids, context_value, assumptions):
    """Project rule bases; each ref alone must cover every physical source ID.

    Context claims/observations have already passed the context validator. Research
    is reasoning context only and is never promoted to runtime source_claim_ids.
    """
    sources_by_rule = {}
    for card_id, rule_ids in physical_rule_ids.items():
        for rule_id in rule_ids:
            sources_by_rule.setdefault(rule_id, set()).add(card_id)
    if type(value) is not dict or set(value) != set(sources_by_rule):
        raise ValueError("starter_candidate_rule_justifications_invalid")
    claims = context_value.get("existing_claims", [])
    observations = context_value.get("research_evidence", {}).get("observations", [])
    result = {}
    for rule_id, sources in sorted(sources_by_rule.items()):
        applicable_refs = set()
        for claim in claims:
            cards = claim.get("cards")
            if (type(cards) is list and all(type(card) is str for card in cards)
                    and sources <= set(cards)) or claim.get("scope") == "deck":
                if type(claim.get("claim_id")) is str:
                    applicable_refs.add(claim["claim_id"])
        for observation in observations:
            cards = observation.get("card_ids")
            if type(cards) is list and all(type(card) is str for card in cards) and sources <= set(cards):
                if type(observation.get("observation_id")) is str:
                    applicable_refs.add(observation["observation_id"])
        row = value[rule_id]
        validate_rule_basis(row, assumptions=assumptions, applicable_refs=applicable_refs)
        result[rule_id] = {**row, "evidence_refs": list(row["evidence_refs"])}
    return result


__all__ = (
    "semantic_runtime_policy", "validate_semantic_condition", "validate_semantic_owner",
    "semantic_selector", "semantic_rule_justifications", "validate_rule_basis",
)
