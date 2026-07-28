from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from hsconfig.audited_deck_catalog import load_audited_role_manifest
from hsconfig.deck_input_verification import verify_deck_input
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json
from hsconfig.source_acquisition_provenance import (
    CAPTURED_RECORD,
    LEGACY_CLAIMS_JSON,
    MANUAL_EVIDENCE,
    acquisition_provenance_is_canonical,
    build_acquisition_provenance,
)
from hsconfig.source_document_model import runtime_claim_kind

LEGACY_CLAIMS_RETRIEVED_AT = "1970-01-01T00:00:00Z"
LEGACY_TARGETING_MARKERS = ("face", "enemy hero")
LEGACY_ENEMY_HERO_TARGETING_MARKERS = ("face", "enemy hero")
LEGACY_TARGETING_SCOPE_TOKENS = ("hero", "minion", "enemy", "friendly", "own")


def load_cards(
    cards_json: str | None,
    *,
    deck_name: str,
    deck_code: str,
    allow_placeholder: bool = False,
) -> dict[str, Any]:
    if cards_json is None and not allow_placeholder:
        decoded = decode_deck_code(deck_code)
        return _with_deck_input_verification({
            "cards": decoded["cards"],
            "hero_dbf_id": decoded["hero_dbf_id"],
            "format": decoded["format"],
            "sideboards": decoded.get("sideboards", []),
            "deckstring_decode_receipt": decoded["deckstring_decode_receipt"],
            "card_id_map": decoded["card_id_map"],
            "card_source": "deckstring",
        }, deck_code=deck_code)
    if cards_json is None:
        return _with_deck_input_verification({
            "cards": _placeholder_cards(deck_name=deck_name, deck_code=deck_code),
            "hero_dbf_id": None,
            "format": None,
            "sideboards": [],
            "deckstring_decode_receipt": None,
            "card_id_map": None,
            "card_source": "placeholder",
        }, deck_code=deck_code)
    payload = read_json(cards_json)
    if isinstance(payload, dict):
        payload = payload.get("cards")
    if not isinstance(payload, list):
        raise ValueError("--cards-json must contain a list or an object with a cards list")
    cards = [_normalize_card_input(card) for card in payload]
    if not cards:
        raise ValueError("--cards-json did not contain any cards")
    return _with_deck_input_verification({
        "cards": cards,
        "hero_dbf_id": None,
        "format": None,
        "sideboards": [],
        "deckstring_decode_receipt": None,
        "card_id_map": None,
        "card_source": "cards_json",
    }, deck_code=deck_code)


def load_claims(claims_json: str | None) -> list[dict[str, Any]]:
    if claims_json is None:
        return []
    payload = read_json(claims_json)
    if isinstance(payload, dict):
        payload = payload.get("claims")
    if not isinstance(payload, list):
        raise ValueError("--claims-json must contain a list or an object with a claims list")
    provenance = _file_acquisition_provenance(
        claims_json,
        mode=LEGACY_CLAIMS_JSON,
    )
    claims = []
    for claim in payload:
        if not isinstance(claim, dict):
            raise ValueError("Every claim row must be an object")
        claims.append(_with_acquisition_provenance(claim, provenance))
    return claims


def load_guide_sources(guide_sources_json: str | None) -> list[dict[str, Any]]:
    if guide_sources_json is None:
        return []
    payload = read_json(guide_sources_json)
    if isinstance(payload, dict):
        payload = payload.get("sources", payload.get("documents", payload.get("guide_sources")))
    if not isinstance(payload, list):
        raise ValueError("--guide-sources-json must contain a list or an object with a sources list")
    provenance = _file_acquisition_provenance(
        guide_sources_json,
        mode=MANUAL_EVIDENCE,
    )
    sources = []
    for source in payload:
        if not isinstance(source, dict):
            raise ValueError("Every guide source row must be an object")
        sources.append(_with_acquisition_provenance(source, provenance))
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
    provenance = _file_acquisition_provenance(
        source_documents_json,
        mode=CAPTURED_RECORD,
    )
    documents = []
    for document in payload:
        if not isinstance(document, dict):
            raise ValueError("Every source document row must be an object")
        documents.append(_with_acquisition_provenance(document, provenance))
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
    provenance = _file_acquisition_provenance(
        source_evidence_json,
        mode=MANUAL_EVIDENCE,
    )
    rows = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Every source evidence row must be an object")
        rows.append(_with_acquisition_provenance(row, provenance))
    return rows


def load_source_search_records(
    source_search_results_json: str,
) -> list[dict[str, Any]]:
    payload = read_json(source_search_results_json)
    if isinstance(payload, dict):
        payload = payload.get("records", payload)
    if not isinstance(payload, list):
        raise ValueError(
            "--source-search-results-json must contain a list or an object with a records list"
        )
    provenance = _file_acquisition_provenance(
        source_search_results_json,
        mode=CAPTURED_RECORD,
    )
    records = []
    for record in payload:
        if not isinstance(record, dict):
            raise ValueError("Every source search record must be an object")
        records.append(_with_acquisition_provenance(record, provenance))
    return records


def fixture_row_for(deck_name: str) -> dict[str, Any] | None:
    matrix_path = Path(__file__).resolve().parents[2] / "docs" / "operator" / "archetype-fixture-matrix.json"
    if not matrix_path.exists():
        return None
    for row in load_audited_role_manifest(matrix_path):
        if str(row.get("deck_name", "")) == deck_name:
            return dict(row)
    return None


def guide_documents_from_legacy_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not claims:
        return []
    fallback_provenance = build_acquisition_provenance(
        mode=LEGACY_CLAIMS_JSON,
        content=json.dumps(
            claims,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    documents: dict[tuple[str, str, str], dict[str, Any]] = {}
    for claim in claims:
        acquisition_provenance = _trusted_unverified_provenance(
            claim.get("acquisition_provenance"),
            mode=LEGACY_CLAIMS_JSON,
        ) or fallback_provenance
        source_url = str(claim.get("url", ""))
        source_title = str(claim.get("source_title", claim.get("source", "legacy claims")))
        legacy_claim_kind = _effective_legacy_claim_kind(claim)
        authority_partition = (
            "posture_without_legacy_authority"
            if legacy_claim_kind == "gameplan_posture"
            else "legacy_document_authority"
        )
        key = (source_url, source_title, authority_partition)
        document = documents.setdefault(
            key,
            {
                "source_url": source_url,
                "source_title": source_title,
                "source_family": str(claim.get("source", "legacy_claims")),
                "retrieved_at": _legacy_claim_retrieved_at(claim),
                "source_document_origin": "legacy_claims_json",
                "acquisition_provenance": acquisition_provenance,
                "claims": [],
            },
        )
        if legacy_claim_kind != "gameplan_posture":
            for field in (
                "source_visibility",
                "source_lane",
                "deck_match_scope",
                "deck_match",
                "deck_name",
                "source_type",
                "provenance",
                "source_type_family",
            ):
                if field in claim and field not in document:
                    document[field] = claim[field]
        document["claims"].append(
            _legacy_claim_to_guide_claim(
                claim,
                acquisition_provenance=acquisition_provenance,
            )
        )
    return list(documents.values())


def _legacy_claim_retrieved_at(claim: dict[str, Any]) -> str:
    retrieved_at = str(claim.get("retrieved_at", "")).strip()
    return retrieved_at or LEGACY_CLAIMS_RETRIEVED_AT


def _legacy_claim_to_guide_claim(
    claim: dict[str, Any],
    *,
    acquisition_provenance: Mapping[str, str],
) -> dict[str, Any]:
    text = str(claim.get("claim", ""))
    cards = [str(card) for card in claim.get("cards", [])]
    claim_kind = _effective_legacy_claim_kind(claim)
    converted = {
        "claim_kind": claim_kind,
        "cards": cards,
        "stance": _legacy_stance(claim_kind, text),
        "evidence_text_short": text,
        "source_confidence": _legacy_claim_confidence(claim),
        "acquisition_provenance": acquisition_provenance,
    }
    if str(claim.get("claim_confidence", "")).strip():
        converted["claim_confidence"] = str(claim["claim_confidence"]).strip()
    if "promotion_eligible" in claim and claim_kind != "gameplan_posture":
        converted["promotion_eligible"] = claim["promotion_eligible"]
    if claim_kind != "gameplan_posture":
        for field in ("source_type", "provenance", "source_type_family"):
            if field in claim:
                converted[field] = claim[field]
    if claim_kind == "combo_sequence":
        converted["sequence"] = cards
        for optional_key in ("values", "operator", "timing_kind"):
            if optional_key in claim:
                converted[optional_key] = claim[optional_key]
    for optional_key in ("condition", "conditions"):
        if optional_key in claim:
            converted[optional_key] = claim[optional_key]
    return converted


def _file_acquisition_provenance(
    path_value: str,
    *,
    mode: str,
) -> dict[str, str]:
    return build_acquisition_provenance(
        mode=mode,
        content=Path(path_value).read_bytes(),
    )


def _with_acquisition_provenance(
    row: Mapping[str, Any],
    provenance: dict[str, str],
) -> dict[str, Any]:
    return {
        **dict(row),
        "acquisition_provenance": provenance,
    }


def _trusted_unverified_provenance(
    value: Any,
    *,
    mode: str,
) -> Mapping[str, str] | None:
    if acquisition_provenance_is_canonical(value, mode=mode):
        return value
    return None


def _effective_legacy_claim_kind(claim: dict[str, Any]) -> str:
    claim_kind = runtime_claim_kind(claim)
    if claim_kind:
        return claim_kind
    legacy_claim_type = str(claim.get("claim_type", "")).strip().lower()
    if legacy_claim_type == "gameplan_posture":
        return legacy_claim_type
    lowered = str(claim.get("claim", "")).lower()
    if _has_legacy_targeting_signal(lowered):
        return "targeting_rule"
    if any(marker in lowered for marker in ("pressure", "aggressive", "aggro", "burn")):
        return "gameplan_posture"
    return "card_role"


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
    if claim_kind == "targeting_rule" and any(
        _has_legacy_phrase_or_token(lowered, marker)
        for marker in LEGACY_ENEMY_HERO_TARGETING_MARKERS
    ):
        return "prefer_enemy_hero"
    if claim_kind == "gameplan_posture":
        return "aggressive"
    if "pressure" in lowered:
        return "pressure"
    return "deck_card"


def _has_legacy_phrase_or_token(text: str, marker: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", text) is not None


def _has_legacy_targeting_signal(lowered: str) -> bool:
    if any(_has_legacy_phrase_or_token(lowered, marker) for marker in LEGACY_TARGETING_MARKERS):
        return True
    if not _has_legacy_phrase_or_token(lowered, "target"):
        return False
    return any(
        _has_legacy_phrase_or_token(lowered, token)
        for token in LEGACY_TARGETING_SCOPE_TOKENS
    )


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
        raise ValueError("deck_input_card_row_invalid")
    if not card.get("card_id"):
        raise ValueError("deck_input_card_id_missing")
    raw_count = card.get("count", 1)
    if isinstance(raw_count, bool) or not isinstance(raw_count, (int, str)):
        raise ValueError("deck_input_count_invalid")
    try:
        count = int(raw_count)
    except (TypeError, ValueError) as error:
        raise ValueError("deck_input_count_invalid") from error
    if count <= 0:
        raise ValueError("deck_input_count_non_positive")
    normalized = {
        "card_id": str(card["card_id"]),
        "dbf_id": int(card["dbf_id"]) if card.get("dbf_id") is not None else None,
        "count": count,
    }
    for optional_key in ("name", "cost", "type", "text", "mechanics", "card_class", "class"):
        if optional_key in card:
            normalized[optional_key] = card[optional_key]
    return normalized


def _with_deck_input_verification(
    payload: dict[str, Any],
    *,
    deck_code: str,
) -> dict[str, Any]:
    return {
        **payload,
        "deck_input_verification": verify_deck_input(
            deck_code=deck_code,
            cards=payload["cards"],
            source=str(payload["card_source"]),
        ),
    }


def source_records_from_cards(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    metadata_keys = {"name", "cost", "type", "text", "mechanics", "card_class", "class"}
    for card in cards:
        if card.get("deckstring_identity_only") is True:
            continue
        source = {key: card[key] for key in metadata_keys if key in card}
        if source:
            records[str(card["card_id"])] = source
    return records
