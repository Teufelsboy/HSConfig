from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Mapping, Sequence


GUIDE_FAMILIES = {"guide", "mulligan_guide", "matchup_guide", "guide_fixture"}
DECKLIST_FAMILIES = {"decklist", "deck_snapshot", "deck_code"}
STATIC_FAMILIES = {
    "hearthstonejson_static_semantics",
    "static_semantics",
    "metadata",
    "card_text",
}


def compile_source_search_records(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    acquired_records: Sequence[Mapping[str, Any]],
    current_date: str | date | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    unsupported_claims: list[dict[str, Any]] = []

    for index, acquired in enumerate(acquired_records):
        text = _text(acquired.get("normalized_text", ""))
        source_family = _text(acquired.get("source_family", "public_page")).lower()
        compiled = {
            "source_url": acquired.get("source_url"),
            "source_title": acquired.get("source_title"),
            "source_family": source_family or "public_page",
            "retrieved_at": _text(acquired.get("retrieved_at", "")) or _iso_datetime(current_date),
            "deck_match": _deck_match(deck_name, acquired),
            "deck_match_scope": _text(acquired.get("deck_match_scope", "")) or "unknown",
            "mulligan": {"keep_card_ids": []},
            "claims": [],
            "source_claim_compiler_index": index,
        }
        for key in (
            "source_type",
            "provenance",
            "source_visibility",
            "source_lane_hint",
            "source_category",
            "source_document_kind",
            "source_strength",
            "source_record_strength",
            "first_missing_source_action",
        ):
            if _text(acquired.get(key, "")):
                compiled[key] = _text(acquired[key])
        for key in ("promotion_eligible", "strong_promotion_eligible"):
            if acquired.get(key) is not None:
                compiled[key] = bool(acquired[key])
        if isinstance(acquired.get("promotion_blockers"), list):
            compiled["promotion_blockers"] = list(acquired["promotion_blockers"])
        if "source_strength" not in compiled and _text(compiled.get("source_record_strength", "")):
            compiled["source_strength"] = _text(compiled["source_record_strength"])
        if acquired.get("publication_year") is not None:
            compiled["publication_year"] = acquired["publication_year"]
        for key in ("published_at", "publication_date", "published_date"):
            if _text(acquired.get(key, "")):
                compiled[key] = _text(acquired[key])

        unsupported_reason: str | None = None
        if source_family in GUIDE_FAMILIES:
            if _text(compiled.get("source_visibility", "")).lower() == "snippet_only":
                unsupported_reason = "snippet_only_source_not_lowerable"
            else:
                _compile_guide_claims(compiled, deck_identity, text)
                if compiled.get("promotion_eligible") is False:
                    for claim in compiled["claims"]:
                        claim["promotion_eligible"] = False
        elif source_family in DECKLIST_FAMILIES or source_family in STATIC_FAMILIES:
            _compile_non_promoting_card_roles(compiled, acquired)

        if source_family in GUIDE_FAMILIES and not compiled["claims"]:
            unsupported_claims.append(
                {
                    "source_url": compiled["source_url"],
                    "source_title": compiled["source_title"],
                    "source_family": compiled["source_family"],
                    "reason": unsupported_reason or "unsupported_or_non_runtime_claim",
                    "evidence_text_short": _short_evidence(text),
                }
            )

        records.append(compiled)

    claim_kind_counts = Counter(
        claim["claim_kind"] for record in records for claim in record.get("claims", [])
    )
    promotion_candidates = [
        record
        for record in records
        if _is_promoting_guide_record(record)
    ]
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "records": records,
        "source_claim_compiler_report": {
            "schema_version": 1,
            "deck_name": deck_name,
            "record_count": len(records),
            "claim_kind_counts": dict(sorted(claim_kind_counts.items())),
            "promotion_candidate_count": len(promotion_candidates),
            "unsupported_claims": unsupported_claims,
        },
    }


def _compile_guide_claims(
    compiled: dict[str, Any],
    deck_identity: Mapping[str, Any],
    text: str,
) -> None:
    keep_rows = _explicit_keep_rows(deck_identity, text)
    if keep_rows:
        keep_ids = [row["card_id"] for row in keep_rows]
        compiled["mulligan"] = {
            "keep_card_ids": keep_ids,
            "evidence_text_short": keep_rows[0]["evidence_text_short"],
        }
        for row in keep_rows:
            compiled["claims"].append(
                _claim(
                    "mulligan_keep",
                    [row["card_id"]],
                    "keep",
                    row["evidence_text_short"],
                    "high",
                    scope="card",
                    timing="mulligan",
                )
            )

    discard_cost_min = _discard_cost_min(text)
    if discard_cost_min is not None:
        compiled.setdefault("mulligan", {"keep_card_ids": []})
        compiled["mulligan"]["discard_cost_min"] = discard_cost_min
        evidence = _short_evidence(text, marker=f"{discard_cost_min} cost")
        for card in _deck_cards(deck_identity):
            if _is_non_opening_hand_effect_card(card):
                continue
            card_id = _text(card.get("card_id", ""))
            cost = _int_or_none(card.get("cost"))
            if card_id and cost is not None and cost >= discard_cost_min:
                compiled["claims"].append(
                    _claim(
                        "mulligan_discard",
                        [card_id],
                        f"discard_cost_{discard_cost_min}_or_more",
                        evidence,
                        "high",
                        scope="card",
                        timing="mulligan",
                    )
                )

    if _mentions_any(text, ["darkbishop", "shadow hero power", "shadowform"]):
        card_ids = _card_ids_by_names(deck_identity, ["Darkbishop Benedictus"])
        compiled["claims"].append(
            _claim(
                "hero_power_transform",
                card_ids,
                "enable_shadow_hero_power",
                _short_evidence(text, marker="shadow hero power"),
                "high",
                scope="card" if card_ids else "deck",
                timing="start_of_game",
                promotion_eligible=True,
            )
        )

    if _mentions_any(text, ["mind spike", "go face", "clear the enemy board"]):
        compiled["claims"].append(
            _claim(
                "gameplan_posture",
                [],
                "hero_power_board_or_face_pressure",
                _short_evidence(text, marker="mind spike"),
                "high",
                scope="deck",
            )
        )


def _compile_non_promoting_card_roles(
    compiled: dict[str, Any],
    acquired: Mapping[str, Any],
) -> None:
    match = acquired.get("deck_match", {})
    if not isinstance(match, Mapping):
        match = {}
    for card_id in _as_list(match.get("matched_card_ids", [])):
        clean_card_id = _text(card_id)
        if clean_card_id:
            compiled["claims"].append(
                _claim(
                    "card_role",
                    [clean_card_id],
                    "listed_card",
                    "Public decklist or static page contains this card.",
                    "medium",
                    scope="card",
                    promotion_eligible=False,
                )
            )


def _explicit_keep_rows(deck_identity: Mapping[str, Any], text: str) -> list[dict[str, str]]:
    keep_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for keep_sentence in _positive_keep_sentences(text):
        lowered_sentence = keep_sentence.lower()
        for card in _deck_cards(deck_identity):
            name = _text(card.get("name", ""))
            card_id = _text(card.get("card_id", ""))
            if (
                name
                and card_id
                and name.lower() in lowered_sentence
                and not _is_non_opening_hand_effect_card(card)
                and card_id not in seen
            ):
                seen.add(card_id)
                keep_rows.append(
                    {
                        "card_id": card_id,
                        "evidence_text_short": keep_sentence[:220],
                    }
                )
    return keep_rows


def _discard_cost_min(text: str) -> int | None:
    lowered = text.lower()
    for cost in range(1, 16):
        phrases = (
            f"do not keep any {cost} cost or higher",
            f"don't keep any {cost} cost or higher",
            f"do not keep {cost} cost or higher",
            f"don't keep {cost} cost or higher",
        )
        if any(phrase in lowered for phrase in phrases):
            return cost
    return None


def _is_promoting_guide_record(record: Mapping[str, Any]) -> bool:
    family = _text(record.get("source_family", "")).lower()
    if family not in GUIDE_FAMILIES:
        return False
    return any(
        claim.get("source_confidence") == "high"
        and claim.get("promotion_eligible", True) is not False
        and claim.get("claim_kind")
        in {
            "mulligan_keep",
            "mulligan_discard",
            "hero_power_transform",
            "targeting_rule",
            "combo_sequence",
            "discover_choice",
            "choose_one_choice",
            "mechanic_usage",
        }
        for claim in _as_list(record.get("claims", []))
        if isinstance(claim, Mapping)
    )


def _card_ids_by_names(
    deck_identity: Mapping[str, Any],
    names: Sequence[str],
) -> list[str]:
    accepted_names = {name.lower() for name in names}
    result: list[str] = []
    for card in _deck_cards(deck_identity):
        name = _text(card.get("name", ""))
        card_id = _text(card.get("card_id", ""))
        if card_id and name and name.lower() in accepted_names:
            result.append(card_id)
    return result


def _claim(
    claim_kind: str,
    cards: list[str],
    stance: str,
    evidence_text_short: str,
    source_confidence: str,
    *,
    scope: str,
    timing: str | None = None,
    promotion_eligible: bool = True,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "claim_kind": claim_kind,
        "claim_family": _claim_family(claim_kind),
        "stance": stance,
        "scope": scope,
        "evidence_text_short": evidence_text_short,
        "source_confidence": source_confidence,
        "promotion_eligible": promotion_eligible,
    }
    if cards:
        row["cards"] = cards
    if timing:
        row["timing"] = timing
    return row


def _claim_family(claim_kind: str) -> str:
    if claim_kind.startswith("mulligan_"):
        return "mulligan"
    if claim_kind in {"hero_power_transform", "mechanic_usage"}:
        return "card_effect"
    if claim_kind in {"gameplan_posture", "targeting_rule"}:
        return "gameplan"
    if claim_kind in {"card_role"}:
        return "card_role"
    if claim_kind in {"combo_sequence"}:
        return "combo"
    if claim_kind in {"discover_choice", "choose_one_choice"}:
        return "choice"
    return "source_claim"


def _deck_match(deck_name: str, acquired: Mapping[str, Any]) -> dict[str, Any]:
    match = acquired.get("deck_match", {})
    if isinstance(match, Mapping):
        return dict(match)
    return {"deck_name": deck_name, "archetype": _slug(deck_name), "matched_card_ids": []}


def _deck_cards(deck_identity: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [card for card in deck_identity.get("cards", []) if isinstance(card, Mapping)]


def _is_non_opening_hand_effect_card(card: Mapping[str, Any]) -> bool:
    name = _norm(card.get("name", ""))
    if name == "darkbishopbenedictus":
        return True
    text = _text(card.get("text", "")).lower()
    if "start of game" in text:
        return True
    roles = {_text(role).lower() for role in _as_list(card.get("roles", []))}
    return bool(roles & {"start_of_game", "hero_power_transform", "deckbuilding_effect"})


def _sentence_containing(text: str, marker: str) -> str:
    marker_lower = marker.lower()
    for sentence in _sentences(text):
        if marker_lower in sentence.lower():
            return sentence
    return ""


def _positive_keep_sentences(text: str) -> list[str]:
    result: list[str] = []
    for sentence in _sentences(text):
        lowered = sentence.lower()
        if "keep" not in lowered or not _has_explicit_mulligan_context(lowered):
            continue
        if _is_negative_keep_sentence(lowered):
            continue
        result.append(sentence)
    return result


def _has_explicit_mulligan_context(lowered_sentence: str) -> bool:
    return any(
        marker in lowered_sentence
        for marker in ("mulligan", "opening hand", "opening-hand")
    )


def _is_negative_keep_sentence(lowered_sentence: str) -> bool:
    negative_markers = (
        "do not keep",
        "don't keep",
        "dont keep",
        "never keep",
        "not keep",
    )
    return any(marker in lowered_sentence for marker in negative_markers)


def _short_evidence(text: str, marker: str | None = None) -> str:
    if marker:
        sentence = _sentence_containing(text, marker)
        if sentence:
            return sentence[:220]
    stripped = text.strip()
    if stripped and len(stripped) <= 220:
        return stripped
    sentences = _sentences(text)
    return sentences[0][:220] if sentences else "Public source evidence."


def _sentences(text: str) -> list[str]:
    normalized = text.replace("!", ".").replace("?", ".")
    return [part.strip() for part in normalized.split(".") if part.strip()]


def _mentions_any(text: str, needles: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso_datetime(current_date: str | date | None) -> str:
    if current_date is None:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    if isinstance(current_date, date):
        return f"{current_date.isoformat()}T00:00:00Z"
    text = _text(current_date)
    return text if "T" in text else f"{text}T00:00:00Z"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return "".join(ch for ch in _text(value).lower() if ch.isalnum())


def _slug(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())
