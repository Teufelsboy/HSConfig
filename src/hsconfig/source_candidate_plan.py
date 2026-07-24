from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any
from urllib.parse import urlparse

from hsconfig.source_candidate_registry import (
    SourceCandidate,
    candidate_urls,
    source_candidates_for_deck,
)
from hsconfig.source_research_manifest import DECK_ALIASES, MECHANIC_REQUIRED_CLAIMS
from hsconfig.static_semantics import infer_static_semantics


_CARD_TARGET_CLAIM_KINDS = {
    "card_role",
    "combo_sequence",
    "gameplan_posture",
    "hero_power_transform",
    "mechanic_usage",
    "mulligan_discard",
    "mulligan_keep",
    "targeting_rule",
}
_EXPLICIT_SOURCE_ONLY_CLAIM_KINDS = {
    "card_role",
    "combo_sequence",
    "gameplan_posture",
    "mulligan_discard",
    "mulligan_keep",
    "targeting_rule",
}
_NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"


def build_source_candidate_plan(
    *,
    deck_name: str,
    deck_code: str,
    deck_identity: Mapping[str, Any],
    candidate_archetypes: Mapping[str, Any],
    explicit_source_urls: Sequence[str] = (),
    current_date: str | date | None = None,
) -> dict[str, Any]:
    candidates = source_candidates_for_deck(deck_name, deck_code)
    registry_urls = dedupe_acquisition_urls(candidate_urls(candidates))
    explicit_urls = dedupe_acquisition_urls(explicit_source_urls)
    source_urls = dedupe_acquisition_urls([*explicit_urls, *registry_urls])
    aliases = _search_aliases(deck_name)
    primary_archetype = str(candidate_archetypes.get("primary_archetype", "") or "")
    plan_claim_kinds = _plan_claim_kinds(primary_archetype, candidates)
    card_targets = _card_targets(deck_identity, plan_claim_kinds)
    queries = _queries(
        aliases=aliases,
        primary_archetype=primary_archetype,
        deck_identity=deck_identity,
        current_date=current_date,
    )

    return {
        "schema_version": 1,
        "authority": "diagnostic_source_candidate_plan",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "source_status_apply_blocking": False,
        "deck_name": deck_name,
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "primary_archetype": primary_archetype,
        "search_aliases": aliases,
        "explicit_source_urls": explicit_urls,
        "candidate_urls": registry_urls,
        "candidate_url_rows": [_candidate_url_row(candidate) for candidate in candidates],
        "source_urls": source_urls,
        "explicit_source_url_count": len(explicit_urls),
        "candidate_registry_url_count": len(registry_urls),
        "query_count": len(queries),
        "queries": queries,
        "card_targets": card_targets,
        "target_summary": _target_summary(card_targets),
        "first_missing_source_action": _first_missing_source_action(
            candidates,
            explicit_urls,
        ),
        "promotion_boundaries": {
            "candidate_plan_can_promote": False,
            "candidate_plan_can_block_apply": False,
            "normal_apply_authority": _NORMAL_APPLY_AUTHORITY,
            "source_status_apply_blocking": False,
        },
    }


def _candidate_url_row(candidate: SourceCandidate) -> dict[str, Any]:
    return {
        "url": candidate.url,
        "source_family": candidate.source_family,
        "archetype": candidate.archetype,
        "priority": candidate.priority,
        "expected_strength": candidate.expected_strength,
        "strength_ceiling": candidate.strength_ceiling,
        "expected_claim_kinds": list(candidate.expected_claim_kinds),
        "first_missing_source_action": candidate.first_missing_source_action,
        "evergreen_wild_archetype": candidate.evergreen_wild_archetype,
    }


def _search_aliases(deck_name: str) -> list[str]:
    if deck_name in DECK_ALIASES:
        return _dedupe_text(DECK_ALIASES[deck_name])
    deck_slug = _slug(deck_name)
    for known_name, aliases in DECK_ALIASES.items():
        if _slug(known_name) == deck_slug:
            return _dedupe_text(aliases)
    return _dedupe_text([deck_name])


def _plan_claim_kinds(
    primary_archetype: str,
    candidates: Sequence[SourceCandidate],
) -> set[str]:
    claim_kinds = {"card_role"}
    claim_kinds.update(_archetype_claim_kinds(primary_archetype))
    for candidate in candidates:
        if candidate.strength_ceiling == "context_only":
            continue
        claim_kinds.update(candidate.expected_claim_kinds)
    return claim_kinds & _CARD_TARGET_CLAIM_KINDS


def _archetype_claim_kinds(primary_archetype: str) -> set[str]:
    lowered = primary_archetype.lower()
    mechanics = [
        mechanic
        for mechanic in MECHANIC_REQUIRED_CLAIMS
        if mechanic in lowered
    ]
    return {
        claim_kind
        for mechanic in _dedupe_covered_mechanics(mechanics)
        for claim_kind in MECHANIC_REQUIRED_CLAIMS.get(mechanic, ["card_role"])
    }


def _dedupe_covered_mechanics(mechanics: Sequence[str]) -> list[str]:
    output: list[str] = []
    for mechanic in mechanics:
        if any(mechanic != other and mechanic in other for other in mechanics):
            continue
        output.append(mechanic)
    return output


def _card_targets(
    deck_identity: Mapping[str, Any],
    plan_claim_kinds: set[str],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in deck_identity.get("cards", []) or []:
        if not isinstance(card, Mapping):
            continue
        card_id = str(card.get("card_id") or card.get("id") or card.get("cardId") or "")
        card_id = card_id.strip()
        if not card_id or card_id in seen:
            continue
        seen.add(card_id)
        supported_static = _supported_static_claim_kinds(card_id, card)
        required = _required_claim_kinds(plan_claim_kinds, supported_static)
        requires_explicit = _requires_explicit_source_claim_kinds(
            plan_claim_kinds,
            supported_static,
        )
        targets.append(
            {
                "card_id": card_id,
                "name": str(card.get("name") or card_id),
                "required_claim_kinds": required,
                "supported_static_claim_kinds": supported_static,
                "requires_explicit_source_claim_kinds": requires_explicit,
                "effect_semantics_not_mulligan_keep": (
                    "hero_power_transform" in supported_static
                    and "mulligan_keep" in requires_explicit
                    and "mulligan_keep" not in supported_static
                ),
            }
        )
    return targets


def _supported_static_claim_kinds(card_id: str, card: Mapping[str, Any]) -> list[str]:
    families = set(infer_static_semantics(card).get("families", []))
    if card_id == "SW_448":
        families.add("hero_power_transform")
    supported: list[str] = []
    if "hero_power_transform" in families:
        supported.append("hero_power_transform")
    return supported


def _required_claim_kinds(
    plan_claim_kinds: set[str],
    supported_static_claim_kinds: Sequence[str],
) -> list[str]:
    required = {"card_role"}
    required.update(
        claim_kind
        for claim_kind in plan_claim_kinds
        if claim_kind not in {"mulligan_keep", "mulligan_discard"}
    )
    required.update(supported_static_claim_kinds)
    return sorted(required)


def _requires_explicit_source_claim_kinds(
    plan_claim_kinds: set[str],
    supported_static_claim_kinds: Sequence[str],
) -> list[str]:
    supported_static = set(supported_static_claim_kinds)
    requires_explicit = set(plan_claim_kinds & _EXPLICIT_SOURCE_ONLY_CLAIM_KINDS)
    requires_explicit.add("mulligan_keep")
    return sorted(requires_explicit - supported_static)


def _target_summary(card_targets: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "card_targets": len(card_targets),
        "card_role_targets": sum(
            1
            for row in card_targets
            if "card_role" in set(row.get("required_claim_kinds", []))
        ),
        "mulligan_keep_source_targets": sum(
            1
            for row in card_targets
            if "mulligan_keep" in set(row.get("requires_explicit_source_claim_kinds", []))
        ),
        "static_semantics_targets": sum(
            1 for row in card_targets if row.get("supported_static_claim_kinds")
        ),
        "effect_semantics_not_mulligan_keep_targets": sum(
            1 for row in card_targets if row.get("effect_semantics_not_mulligan_keep")
        ),
    }


def _queries(
    *,
    aliases: Sequence[str],
    primary_archetype: str,
    deck_identity: Mapping[str, Any],
    current_date: str | date | None,
) -> list[dict[str, Any]]:
    query_texts: list[str] = []
    year = _current_year(current_date)
    year_prefix = f"{year} " if year is not None else ""
    for alias in aliases:
        query_texts.append(f"{year_prefix}Wild {alias} guide mulligan")
        query_texts.append(f"{year_prefix}Wild {alias} card roles")
    if primary_archetype:
        query_texts.append(f"{year_prefix}Wild {primary_archetype} mulligan guide")
    top_names = _top_card_names(deck_identity)
    if top_names:
        alias = aliases[0] if aliases else str(deck_identity.get("deck_name") or "Deck")
        query_texts.append(f"Wild {alias} {' '.join(top_names)} keep mulligan")

    return [
        {
            "query": query,
            "priority": 10,
            "target_claim_kinds": ["mulligan_keep", "card_role"],
            "reason": "find_public_guide_or_mulligan_source",
        }
        for query in _dedupe_text(query_texts)
    ]


def _top_card_names(deck_identity: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for card in deck_identity.get("cards", []) or []:
        if not isinstance(card, Mapping):
            continue
        name = str(card.get("name") or "").strip()
        if name:
            names.append(name)
        if len(names) == 3:
            break
    return names


def _first_missing_source_action(
    candidates: Sequence[SourceCandidate],
    explicit_urls: Sequence[str],
) -> str:
    non_context_candidates = [
        candidate for candidate in candidates if candidate.strength_ceiling != "context_only"
    ]
    top_candidate = non_context_candidates[0] if non_context_candidates else None
    if top_candidate and top_candidate.first_missing_source_action == "none":
        return "none"
    for candidate in [*non_context_candidates, *candidates]:
        action = candidate.first_missing_source_action
        if action and action != "none":
            return action
    if explicit_urls:
        return "fetch_and_validate_explicit_source_urls"
    return "add_public_guide_url_or_use_static_semantics"


def _current_year(current_date: str | date | None) -> int | None:
    if isinstance(current_date, date):
        return current_date.year
    match = re.search(r"\b(19\d{2}|20\d{2})\b", str(current_date or ""))
    if not match:
        return None
    return int(match.group(1))


def _dedupe_text(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def dedupe_acquisition_urls(values: Sequence[Any]) -> list[str]:
    return [
        url
        for url in _dedupe_text(values)
        if is_acquisition_url(url)
    ]


def is_acquisition_url(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or any(ch.isspace() for ch in text):
        return False
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _slug(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())
