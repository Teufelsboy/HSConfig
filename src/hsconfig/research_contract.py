from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.guide_research import normalize_source_claims
from hsconfig.io import write_json


NEGATIVE_KEEP_MARKERS = (
    "never keep",
    "do not keep",
    "don't keep",
    "dont keep",
    "avoid keeping",
    "avoid keep",
)


def build_research_contract_bundle(
    deck_identity: dict[str, Any],
    card_metadata: dict[str, Any] | list[dict[str, Any]],
    source_claims: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, Any]:
    cards = _deck_cards(deck_identity)
    metadata_by_card = _metadata_by_card(card_metadata)
    claims_payload = _coerce_source_claims(source_claims)
    claims = claims_payload["claims"]
    claims_by_card = _claims_by_card(claims)

    card_role_map: dict[str, dict[str, Any]] = {}
    mulligan_anchor_map: dict[str, dict[str, Any]] = {}
    card_usage_expectations: dict[str, dict[str, Any]] = {}
    known_bad_patterns: list[dict[str, Any]] = []

    for card in cards:
        card_id = str(card["card_id"])
        metadata = metadata_by_card.get(card_id, {})
        related_claims = claims_by_card.get(card_id, [])
        semantic_families = _semantic_families(card, metadata)
        roles = _roles_from_claims_and_semantics(semantic_families, related_claims)
        confidence = _confidence_for_card(related_claims, semantic_families)
        source_claim_ids = [str(claim["claim_id"]) for claim in related_claims]
        linked_entities = list(metadata.get("linked_entities", []))

        card_role_map[card_id] = {
            "card_id": card_id,
            "name": metadata.get("name", card.get("name", card_id)),
            "count": int(card.get("count", metadata.get("count", 1))),
            "roles": roles,
            "semantic_families": semantic_families,
            "linked_entities": linked_entities,
            "confidence": confidence,
            "source_claim_ids": source_claim_ids,
        }
        mulligan_anchor_map[card_id] = _mulligan_intent(
            card_id, related_claims, roles, confidence
        )
        card_usage_expectations[card_id] = {
            "card_id": card_id,
            "expected_use": _expected_use(roles, related_claims),
            "confidence": confidence,
            "source_claim_ids": source_claim_ids,
        }
        for claim in related_claims:
            if _is_bad_pattern(claim):
                known_bad_patterns.append(
                    {
                        "card_id": card_id,
                        "claim_id": claim["claim_id"],
                        "pattern": str(claim.get("claim", "")),
                        "source_claim_ids": [claim["claim_id"]],
                    }
                )

    globalvalue_intent = _globalvalue_intent(card_role_map)
    coverage_summary = _coverage_summary(card_role_map)
    archetype_research = {
        "deck_name": str(deck_identity.get("deck_name", "Deck")),
        "deck_slug": str(deck_identity.get("deck_slug", "")),
        "archetype": _archetype(card_role_map),
        "confidence": _deck_confidence(coverage_summary),
        "source_claim_count": len(claims),
        "source_claim_ids": [str(claim["claim_id"]) for claim in claims],
    }

    return {
        "archetype_research": archetype_research,
        "claims": claims,
        "card_role_map": dict(sorted(card_role_map.items())),
        "mulligan_anchor_map": dict(sorted(mulligan_anchor_map.items())),
        "card_usage_expectations": dict(sorted(card_usage_expectations.items())),
        "known_bad_patterns": sorted(
            known_bad_patterns, key=lambda row: (row["card_id"], row["claim_id"])
        ),
        "globalvalue_intent": globalvalue_intent,
        "coverage_summary": coverage_summary,
    }


def write_research_contract_bundle(bundle: dict[str, Any], reports_dir: Path) -> None:
    research_dir = reports_dir / "research"
    write_research_contract_bundle_to_dir(bundle, research_dir)


def write_research_contract_bundle_to_dir(bundle: dict[str, Any], output_dir: Path) -> None:
    write_json(output_dir / "archetype_research.json", bundle["archetype_research"])
    write_json(output_dir / "claims.json", {"claims": bundle["claims"]})
    write_json(output_dir / "card_role_map.json", bundle["card_role_map"])
    write_json(output_dir / "mulligan_anchor_map.json", bundle["mulligan_anchor_map"])
    write_json(output_dir / "card_usage_expectations.json", bundle["card_usage_expectations"])
    write_json(output_dir / "known_bad_patterns.json", bundle["known_bad_patterns"])
    write_json(output_dir / "globalvalue_intent.json", bundle["globalvalue_intent"])
    write_json(output_dir / "coverage_summary.json", bundle["coverage_summary"])


def _deck_cards(deck_identity: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (dict(card) for card in deck_identity.get("cards", [])),
        key=lambda card: str(card["card_id"]),
    )


def _metadata_by_card(
    card_metadata: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    rows = card_metadata.get("cards", []) if isinstance(card_metadata, dict) else card_metadata
    return {str(row["card_id"]): dict(row) for row in rows}


def _coerce_source_claims(
    source_claims: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if source_claims is None:
        return {"claims": [], "claim_count": 0}
    if isinstance(source_claims, list):
        return normalize_source_claims(source_claims)
    claims = [dict(claim) for claim in source_claims.get("claims", [])]
    if not all("claim_id" in claim for claim in claims):
        return normalize_source_claims(claims)
    for claim in claims:
        claim.setdefault("cards", [])
        claim["cards"] = list(dict.fromkeys(str(card) for card in claim.get("cards", [])))
        claim.setdefault("claim_type", "general")
        claim.setdefault("confidence", "source_backed")
        claim.setdefault("source_refs", [])
    return {
        "claims": sorted(claims, key=lambda claim: str(claim["claim_id"])),
        "claim_count": len(claims),
    }


def _claims_by_card(claims: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_card: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        for card_id in claim.get("cards", []):
            by_card.setdefault(str(card_id), []).append(claim)
    return by_card


def _semantic_families(card: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    values = {
        str(item)
        for item in [
            *metadata.get("mechanic_families", card.get("mechanic_families", [])),
            *metadata.get("semantic_families", card.get("semantic_families", [])),
        ]
    }
    return sorted(item for item in values if item)


def _roles_from_claims_and_semantics(
    semantic_families: list[str],
    claims: list[dict[str, Any]],
) -> list[str]:
    text = _claim_text(claims)
    claim_types = {str(claim.get("claim_type", "")).lower() for claim in claims}
    roles = set(semantic_families)
    if "keep" in text and not _has_negative_keep(text):
        roles.add("mulligan_anchor")
    if any(marker in text for marker in ("face", "damage", "pressure", "push", "burst")):
        roles.add("pressure")
    if "combo" in claim_types or "combo" in text:
        roles.add("combo_piece")
    if "hero_power_transform" in roles or "hero_power_pressure" in roles:
        roles.add("pressure")
    return sorted(roles) or ["deck_card"]


def _confidence_for_card(claims: list[dict[str, Any]], semantic_families: list[str]) -> str:
    if claims:
        if any(_is_guide_claim(claim) for claim in claims):
            return "guide_backed"
        return "source_backed"
    if {"hero_power_transform", "hero_power_pressure", "start_of_game", "shadowform"} & set(
        semantic_families
    ):
        return "source_backed_static_semantics"
    if semantic_families:
        return "archetype_inferred"
    return "generic_low_confidence"


def _is_guide_claim(claim: dict[str, Any]) -> bool:
    if str(claim.get("confidence")) == "guide_backed":
        return True
    source = str(claim.get("source", "")).lower()
    url = str(claim.get("url", "")).lower()
    source_title = str(claim.get("source_title", "")).lower()
    return "guide" in source or "guide" in url or "guide" in source_title


def _mulligan_intent(
    card_id: str,
    claims: list[dict[str, Any]],
    roles: list[str],
    confidence: str,
) -> dict[str, Any]:
    text = _claim_text(claims)
    if _has_negative_keep(text):
        intent = "avoid"
    elif "mulligan_anchor" in roles:
        intent = "hold"
    else:
        intent = "neutral"
    return {
        "card_id": card_id,
        "intent": intent,
        "condition": "*",
        "confidence": confidence,
        "source_claim_ids": [str(claim["claim_id"]) for claim in claims],
    }


def _expected_use(roles: list[str], claims: list[dict[str, Any]]) -> str:
    text = _claim_text(claims)
    if "hero_power_transform" in roles and "hero_power_pressure" in roles:
        return "start_of_game_shadowform_enables_hero_power_pressure"
    if "combo_piece" in roles and "pressure" in roles:
        return "combo_burst_piece"
    if "mulligan_anchor" in roles and "pressure" in roles:
        return "keep_and_pressure"
    if "mulligan_anchor" in roles:
        return "keep_and_play_on_plan"
    if _has_negative_keep(text):
        return "avoid_low_value_timing"
    if "pressure" in roles:
        return "prioritize_for_pressure"
    return "follow_archetype_plan"


def _globalvalue_intent(card_role_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    all_roles = {role for row in card_role_map.values() for role in row.get("roles", [])}
    overlays: dict[str, str] = {}
    overlay_reasons: dict[str, str] = {}
    if {"pressure", "damage", "combo_piece"} & all_roles:
        overlays.update(
            {
                "GlobalMinionAttack": "increase",
                "GlobalMinionIntrinsicValue": "increase",
                "OppGlobalHeroHealth": "increase",
                "OppGlobalMinionAttack": "decrease",
                "OppGlobalMinionHealth": "decrease",
                "OppGlobalMinionIntrinsicValue": "decrease",
            }
        )
    if "hero_power_transform" in all_roles or "hero_power_pressure" in all_roles:
        overlays["MyHeroPowerValue"] = "increase"
        overlay_reasons["MyHeroPowerValue"] = _hero_power_reason(card_role_map)
    return {
        "pressure_bias": "high" if overlays else "baseline",
        "overlays": dict(sorted(overlays.items())),
        "overlay_reasons": dict(sorted(overlay_reasons.items())),
    }


def _hero_power_reason(card_role_map: dict[str, dict[str, Any]]) -> str:
    for row in card_role_map.values():
        for linked in row.get("linked_entities", []):
            if linked.get("card_id") == "EX1_625t" or linked.get("name") == "Mind Spike":
                return f"{row.get('name', row['card_id'])} enables Mind Spike as pressure damage."
    return "Hero Power pressure is part of this deck plan."


def _coverage_summary(card_role_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "guide_backed": 0,
        "source_backed": 0,
        "source_backed_static_semantics": 0,
        "archetype_inferred": 0,
        "generic_low_confidence": 0,
    }
    for row in card_role_map.values():
        counts[str(row["confidence"])] += 1
    return {
        "deck_card_count": len(card_role_map),
        "guide_backed_card_count": counts["guide_backed"],
        "source_backed_card_count": counts["source_backed"],
        "source_backed_static_semantics_card_count": counts[
            "source_backed_static_semantics"
        ],
        "archetype_inferred_card_count": counts["archetype_inferred"],
        "generic_low_confidence_card_count": counts["generic_low_confidence"],
    }


def _deck_confidence(summary: dict[str, Any]) -> str:
    if summary["deck_card_count"] == summary["guide_backed_card_count"]:
        return "guide_backed"
    backed_count = summary["guide_backed_card_count"] + summary["source_backed_card_count"]
    if backed_count == summary["deck_card_count"]:
        return "source_backed"
    if backed_count > 0:
        return "mixed"
    if summary["source_backed_static_semantics_card_count"] > 0:
        return "source_backed_static_semantics"
    if summary["archetype_inferred_card_count"] > 0:
        return "archetype_inferred"
    return "generic_low_confidence"


def _archetype(card_role_map: dict[str, dict[str, Any]]) -> str:
    roles = {role for row in card_role_map.values() for role in row.get("roles", [])}
    if "pressure" in roles or "damage" in roles or "combo_piece" in roles:
        return "aggressive_gameplan"
    return "unknown_archetype"


def _is_bad_pattern(claim: dict[str, Any]) -> bool:
    claim_type = str(claim.get("claim_type", "")).lower()
    text = str(claim.get("claim", "")).lower()
    return claim_type in {"bad_pattern", "known_bad_pattern"} or any(
        marker in text for marker in ("never", "avoid", "do not", "don't", "dont")
    )


def _claim_text(claims: list[dict[str, Any]]) -> str:
    return " ".join(str(claim.get("claim", "")) for claim in claims).lower()


def _has_negative_keep(text: str) -> bool:
    return any(marker in text for marker in NEGATIVE_KEEP_MARKERS)
