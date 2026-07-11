from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json
from hsconfig.source_document_model import runtime_claim_kind

LEGACY_CLAIMS_RETRIEVED_AT = "1970-01-01T00:00:00Z"


def load_cards(
    cards_json: str | None,
    *,
    deck_name: str,
    deck_code: str,
    allow_placeholder: bool = False,
) -> dict[str, Any]:
    if cards_json is None and not allow_placeholder:
        decoded = decode_deck_code(deck_code)
        return {
            "cards": decoded["cards"],
            "hero_dbf_id": decoded["hero_dbf_id"],
            "format": decoded["format"],
            "sideboards": decoded.get("sideboards", []),
            "deckstring_decode_receipt": decoded["deckstring_decode_receipt"],
            "card_id_map": decoded["card_id_map"],
            "card_source": "deckstring",
        }
    if cards_json is None:
        return {
            "cards": _placeholder_cards(deck_name=deck_name, deck_code=deck_code),
            "hero_dbf_id": None,
            "format": None,
            "sideboards": [],
            "deckstring_decode_receipt": None,
            "card_id_map": None,
            "card_source": "placeholder",
        }
    payload = read_json(cards_json)
    if isinstance(payload, dict):
        payload = payload.get("cards")
    if not isinstance(payload, list):
        raise ValueError("--cards-json must contain a list or an object with a cards list")
    cards = [_normalize_card_input(card) for card in payload]
    if not cards:
        raise ValueError("--cards-json did not contain any cards")
    return {
        "cards": cards,
        "hero_dbf_id": None,
        "format": None,
        "sideboards": [],
        "deckstring_decode_receipt": None,
        "card_id_map": None,
        "card_source": "cards_json",
    }


def load_claims(claims_json: str | None) -> list[dict[str, Any]]:
    if claims_json is None:
        return []
    payload = read_json(claims_json)
    if isinstance(payload, dict):
        payload = payload.get("claims")
    if not isinstance(payload, list):
        raise ValueError("--claims-json must contain a list or an object with a claims list")
    claims = []
    for claim in payload:
        if not isinstance(claim, dict):
            raise ValueError("Every claim row must be an object")
        claims.append(dict(claim))
    return claims


def load_guide_sources(guide_sources_json: str | None) -> list[dict[str, Any]]:
    if guide_sources_json is None:
        return []
    payload = read_json(guide_sources_json)
    if isinstance(payload, dict):
        payload = payload.get("sources", payload.get("documents", payload.get("guide_sources")))
    if not isinstance(payload, list):
        raise ValueError("--guide-sources-json must contain a list or an object with a sources list")
    sources = []
    for source in payload:
        if not isinstance(source, dict):
            raise ValueError("Every guide source row must be an object")
        sources.append(dict(source))
    return sources


def load_source_documents(source_documents_json: str | None) -> list[dict[str, Any]]:
    if source_documents_json is None:
        return []
    payload = read_json(source_documents_json)
    if isinstance(payload, dict):
        payload = payload.get("source_documents", payload.get("documents", payload.get("sources")))
    if not isinstance(payload, list):
        raise ValueError(
            "--source-documents-json must contain a list or an object with a source_documents list"
        )
    documents = []
    for document in payload:
        if not isinstance(document, dict):
            raise ValueError("Every source document row must be an object")
        documents.append(dict(document))
    return documents


def load_source_evidence(source_evidence_json: str | None) -> list[dict[str, Any]]:
    if source_evidence_json is None:
        return []
    payload = read_json(source_evidence_json)
    if isinstance(payload, dict):
        payload = payload.get("evidence_rows", payload.get("rows", payload.get("source_evidence")))
    if not isinstance(payload, list):
        raise ValueError(
            "--source-evidence-json must contain a list or an object with an evidence_rows list"
        )
    rows = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Every source evidence row must be an object")
        rows.append(dict(row))
    return rows


def fixture_row_for(deck_name: str) -> dict[str, Any] | None:
    matrix_path = Path(__file__).resolve().parents[2] / "docs" / "operator" / "archetype-fixture-matrix.json"
    if not matrix_path.exists():
        return None
    payload = read_json(matrix_path)
    rows = payload.get("decks", []) if isinstance(payload, dict) else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("deck_name", "")) == deck_name:
            return dict(row)
    return None


def guide_documents_from_legacy_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not claims:
        return []
    documents: dict[tuple[str, str], dict[str, Any]] = {}
    for claim in claims:
        source_url = str(claim.get("url", ""))
        source_title = str(claim.get("source_title", claim.get("source", "legacy claims")))
        key = (source_url, source_title)
        document = documents.setdefault(
            key,
            {
                "source_url": source_url,
                "source_title": source_title,
                "source_family": str(claim.get("source", "legacy_claims")),
                "retrieved_at": _legacy_claim_retrieved_at(claim),
                "claims": [],
            },
        )
        document["claims"].append(_legacy_claim_to_guide_claim(claim))
    return list(documents.values())


def _legacy_claim_retrieved_at(claim: dict[str, Any]) -> str:
    retrieved_at = str(claim.get("retrieved_at", "")).strip()
    return retrieved_at or LEGACY_CLAIMS_RETRIEVED_AT


def _legacy_claim_to_guide_claim(claim: dict[str, Any]) -> dict[str, Any]:
    text = str(claim.get("claim", ""))
    cards = [str(card) for card in claim.get("cards", [])]
    lowered = text.lower()
    claim_kind = runtime_claim_kind(claim)
    if not claim_kind:
        if any(marker in lowered for marker in ("face", "target", "enemy hero")):
            claim_kind = "targeting_rule"
        elif any(marker in lowered for marker in ("pressure", "aggressive", "aggro", "burn")):
            claim_kind = "gameplan_posture"
        else:
            claim_kind = "card_role"
    converted = {
        "claim_kind": claim_kind,
        "cards": cards,
        "stance": _legacy_stance(claim_kind, text),
        "evidence_text_short": text,
        "source_confidence": _legacy_claim_confidence(claim),
    }
    if str(claim.get("claim_confidence", "")).strip():
        converted["claim_confidence"] = str(claim["claim_confidence"]).strip()
    if claim_kind == "combo_sequence":
        converted["sequence"] = cards
        for optional_key in ("values", "operator", "timing_kind"):
            if optional_key in claim:
                converted[optional_key] = claim[optional_key]
    for optional_key in ("condition", "conditions"):
        if optional_key in claim:
            converted[optional_key] = claim[optional_key]
    return converted


def _legacy_claim_confidence(claim: dict[str, Any]) -> str:
    for key in ("source_confidence", "claim_confidence", "confidence"):
        value = str(claim.get(key, "")).strip()
        if value:
            return value
    return "high" if claim.get("source") == "guide" else "medium"


def _legacy_stance(claim_kind: str, text: str) -> str:
    lowered = text.lower()
    if claim_kind == "mulligan_keep":
        return "keep"
    if claim_kind == "combo_sequence":
        return "ordered_combo"
    if claim_kind == "targeting_rule" and ("face" in lowered or "enemy hero" in lowered):
        return "prefer_enemy_hero"
    if claim_kind == "gameplan_posture":
        return "aggressive"
    if "pressure" in lowered:
        return "pressure"
    return "deck_card"


def _placeholder_cards(*, deck_name: str, deck_code: str) -> list[dict[str, Any]]:
    seed = hashlib.sha256(f"{deck_name}\0{deck_code}".encode("utf-8")).hexdigest().upper()
    cards: list[dict[str, Any]] = []
    for index, count in enumerate((2, 2, 1), start=1):
        chunk = seed[(index - 1) * 6 : index * 6]
        cards.append(
            {
                "card_id": f"HSC_{chunk}_{index}",
                "dbf_id": int(seed[index * 6 : index * 6 + 6], 16),
                "count": count,
                "name": f"Preview Placeholder {index}",
                "type": "MINION",
                "text": "Generated preview placeholder for deterministic package validation.",
                "mechanics": [],
            }
        )
    return cards


def _normalize_card_input(card: Any) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError("Every card row must be an object")
    if not card.get("card_id"):
        raise ValueError("Every card row must include card_id")
    normalized = {
        "card_id": str(card["card_id"]),
        "dbf_id": int(card["dbf_id"]) if card.get("dbf_id") is not None else None,
        "count": int(card.get("count", 1)),
    }
    for optional_key in ("name", "cost", "type", "text", "mechanics", "card_class", "class"):
        if optional_key in card:
            normalized[optional_key] = card[optional_key]
    return normalized


def source_records_from_cards(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    metadata_keys = {"name", "cost", "type", "text", "mechanics", "card_class", "class"}
    for card in cards:
        source = {key: card[key] for key in metadata_keys if key in card}
        if source:
            records[str(card["card_id"])] = source
    return records
