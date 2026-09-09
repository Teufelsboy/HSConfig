"""Bounded discovery contracts and context projections, not a source authority."""

from __future__ import annotations

from hashlib import sha256
import math
import re
from typing import Any
from urllib.parse import urlparse

from hsconfig.internal_source_authority import (
    InternalSourceAuthorityHandoff,
    _consume_acquired_search_records_handoff,
    _issue_acquired_search_records_handoff,
    _issue_generated_source_documents_handoff,
)
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.source_acquisition import validate_public_source_url
from hsconfig.source_acquisition_provenance import (
    strategic_source_provenance_is_verified,
)
from hsconfig.source_autopilot import build_source_autopilot_bundle
from hsconfig.source_candidate_plan import build_source_candidate_plan
from hsconfig.source_claim_compiler import compile_source_search_records
from hsconfig.source_claim_conflicts import build_claim_conflict_report


_OUTCOMES = {"completed", "unavailable", "budget_exhausted"}
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RETAINED_FIELDS = (
    "evidence_id",
    "source_id",
    "source_identity",
    "as_of_date",
    "content_sha256",
    "acquisition_provenance",
    "source_updated_at",
)


def _digest(value: Any) -> str:
    return (
        "sha256:"
        + sha256(FrozenJsonDocument.from_value(value).canonical_json).hexdigest()
    )


def _seal(value: dict) -> FrozenJsonDocument:
    return FrozenJsonDocument.from_value({**value, "content_sha256": _digest(value)})


def _public_url(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("research_url_invalid")
    # Structural admission only. Real DNS is checked by the collector inside the
    # acquisition deadline, never during orchestration-draft validation.
    if validate_public_source_url(value, resolver=lambda hostname: ["93.184.216.34"]):
        raise ValueError("research_url_invalid")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = host if parsed.port in {None, 443} else f"{host}:{parsed.port}"
    return parsed._replace(netloc=netloc, fragment="", path=parsed.path or "/").geturl()


def build_research_request(
    *,
    run_id: str,
    deck_identity: dict,
    captured_input_sha256: str,
    queries: tuple[str, ...],
) -> FrozenJsonDocument:
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or not _SHA256.fullmatch(captured_input_sha256)
    ):
        raise ValueError("research_request_invalid")
    if type(deck_identity) is not dict or not re.fullmatch(
        r"(?:sha256:)?[0-9a-f]{64}", str(deck_identity.get("deck_fingerprint", ""))
    ):
        raise ValueError("research_request_identity_invalid")
    if type(queries) is not tuple or any(
        not isinstance(query, str) or not query.strip() for query in queries
    ):
        raise ValueError("research_queries_invalid")
    cards = deck_identity.get("cards", [])
    names = [str(card.get("name", "")).strip() for card in cards if card.get("name")][
        :3
    ]
    classes = sorted(
        {str(card.get("card_class", "")) for card in cards if card.get("card_class")}
    )
    card_class = str(
        deck_identity.get("class")
        or deck_identity.get("card_class")
        or " ".join(classes)
    )
    format_name = {
        1: "Wild",
        2: "Standard",
        3: "Classic",
        4: "Twist",
        "FT_WILD": "Wild",
        "FT_STANDARD": "Standard",
        "FT_CLASSIC": "Classic",
        "FT_TWIST": "Twist",
    }.get(
        deck_identity.get("format"),
        str(deck_identity.get("format") or "Hearthstone"),
    )
    if not names:
        raise ValueError("research_request_signature_cards_missing")
    factual_query = " ".join(
        [format_name, card_class, *names, "guide mulligan"]
    ).strip()
    candidate = build_source_candidate_plan(
        deck_name=str(deck_identity.get("deck_name", "")),
        deck_identity=deck_identity,
        candidate_archetypes={},
    )
    choices = [factual_query, *queries, *(row["query"] for row in candidate["queries"])]
    selected = list(dict.fromkeys(" ".join(query.split()) for query in choices))[:2]
    return _seal(
        {
            "schema_version": 1,
            "run_id": run_id,
            "deck_identity": deck_identity,
            "captured_input_sha256": captured_input_sha256,
            "queries": selected,
            "limits": {
                "search_calls": 2,
                "pages": 3,
                "total_seconds": 30,
                "request_seconds": 10,
            },
        }
    )


def validate_research_draft(
    value: dict, *, request_sha256: str
) -> tuple[tuple[str, ...], str]:
    if (
        type(value) is not dict
        or set(value)
        != {
            "acquisition_request_sha256",
            "urls",
            "discovery_outcome",
        }
        or not isinstance(request_sha256, str)
        or not _SHA256.fullmatch(request_sha256)
        or value["acquisition_request_sha256"] != request_sha256
        or not isinstance(value["discovery_outcome"], str)
        or value["discovery_outcome"] not in _OUTCOMES
        or type(value["urls"]) is not list
        or len(value["urls"]) > 3
    ):
        raise ValueError("research_draft_invalid")
    urls = tuple(_public_url(url) for url in value["urls"])
    if len(set(urls)) != len(urls):
        raise ValueError("research_duplicate_url")
    return urls, value["discovery_outcome"]


def research_timeout(*, deadline_utc: float, now_utc: float) -> float:
    if not math.isfinite(deadline_utc) or not math.isfinite(now_utc):
        raise ValueError("research_deadline_invalid")
    return max(0.0, min(10.0, deadline_utc - now_utc))


def compile_research_sources(
    *,
    acquired: dict,
    deck_identity: dict,
    current_date: str | None = None,
) -> tuple[FrozenJsonDocument, InternalSourceAuthorityHandoff]:
    """Internal collector output -> canonical compiler/autopilot capability chain.

    This is not an ingestion API for caller drafts or rehydrated source claims.
    The controller must supply only its own validated acquisition records.
    """
    deck_name = str(deck_identity["deck_name"])
    records = acquired["source_records"]
    if len(records) > 3:
        raise ValueError("research_page_limit_exceeded")
    compiled = compile_source_search_records(
        deck_name=deck_name,
        deck_identity=deck_identity,
        acquired_records=records,
        current_date=current_date,
    )
    for original, record in zip(records, compiled["records"], strict=True):
        for key in _RETAINED_FIELDS:
            if key in original:
                record[key] = original[key]
    incoming = _issue_acquired_search_records_handoff(compiled["records"])
    search_records, lineage = _consume_acquired_search_records_handoff(incoming)
    bundle = build_source_autopilot_bundle(
        deck_name=deck_name,
        deck_identity=deck_identity,
        source_search_records=search_records,
        current_date=current_date,
    )
    handoff = _issue_generated_source_documents_handoff(
        lineage,
        bundle["source_documents_payload"]["source_documents"],
    )
    projection = _seal(
        {
            "source_records": records,
            "compiled": compiled,
            "autopilot": bundle,
            "claim_conflicts": build_claim_conflict_report(
                bundle["source_evidence_rows"]
            ),
            "source_acquisition_report": acquired.get("source_acquisition_report", {}),
        }
    )
    return projection, handoff


def _mentioned_cards(text: str, metadata: dict) -> list[str]:
    return sorted(
        card_id
        for card_id, card in metadata.items()
        if any(
            re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", text, re.IGNORECASE)
            for token in (card_id, str(card.get("name") or ""))
            if token
        )
    )


def _observations(acquired: dict, metadata: dict) -> list[dict]:
    rows: list[dict] = []
    ranked = {
        row["evidence_id"]: row
        for row in acquired.get("autopilot", {}).get("ranked_sources", [])
    }
    for record in acquired.get("source_records", [])[:3]:
        evidence_id = record["evidence_id"]
        source = ranked.get(evidence_id, record)
        scope = source.get("deck_match_scope")
        exact = (
            evidence_id in ranked
            and scope == "exact_deck_matched"
            and strategic_source_provenance_is_verified(
                record.get("acquisition_provenance"),
            )
            and record.get("deck_match", {})
            .get("exact_deck_evidence", {})
            .get("matched")
            is True
        )
        applicability = (
            "exact_list"
            if exact
            else "archetype_only"
            if scope == "archetype_matched"
            else "card_only"
        )
        text = record.get("normalized_text", "")
        # Select relevant windows rather than truncating the start of a page.
        snippets: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            for match in re.finditer(r"\S(?:.{0,598}\S)?", sentence):
                snippet = match.group().strip()
                if _mentioned_cards(snippet, metadata) and snippet not in snippets:
                    snippets.append(snippet)
        for snippet in snippets[:4]:
            limitations = [
                "context_only_not_runtime_authority",
                "strategic_conflicts_require_review",
            ]
            if not strategic_source_provenance_is_verified(
                record.get("acquisition_provenance")
            ):
                limitations.append("strategic_provenance_not_live_verified")
            if record.get("source_updated_at") is None:
                limitations.append("source_update_date_unknown")
            rows.append(
                {
                    "observation_id": _digest([evidence_id, snippet]),
                    "evidence_id": evidence_id,
                    "source_url": record["source_url"],
                    "content_sha256": record["content_sha256"],
                    "retrieved_at": record["retrieved_at"],
                    "source_updated_at": record.get("source_updated_at"),
                    "supporting_text": snippet,
                    "card_ids": _mentioned_cards(snippet, metadata),
                    "applicability": applicability,
                    "limitations": limitations,
                    "conflicts": [
                        *source.get("conflicts", []),
                        *[
                            conflict
                            for conflict in acquired.get("claim_conflicts", {}).get(
                                "conflicts", []
                            )
                            if conflict.get("card_id")
                            in _mentioned_cards(snippet, metadata)
                            or not conflict.get("card_id")
                        ],
                    ],
                }
            )
    return rows[:12]


def build_research_result(
    *,
    acquired: dict,
    discovery_outcome: str,
    attempts: list[dict],
    deadline_utc: float | None,
    card_metadata: dict,
) -> FrozenJsonDocument:
    if (
        discovery_outcome not in _OUTCOMES
        or type(attempts) is not list
        or len(attempts) > 3
    ):
        raise ValueError("research_result_invalid")
    if deadline_utc is None and attempts:
        raise ValueError("research_deadline_missing")
    if deadline_utc is not None and (
        isinstance(deadline_utc, bool) or not math.isfinite(deadline_utc)
    ):
        raise ValueError("research_deadline_invalid")
    seen: set[str] = set()
    records = acquired.get("source_records", [])
    if len(records) > 3:
        raise ValueError("research_page_limit_exceeded")
    by_url = {_public_url(row["source_url"]): row for row in records}
    for attempt in attempts:
        if type(attempt) is not dict or set(attempt) != {
            "url",
            "state",
            "record_sha256",
            "error",
        }:
            raise ValueError("research_attempt_invalid")
        url = _public_url(attempt["url"])
        state = attempt["state"]
        if url in seen or state not in {
            "started",
            "completed",
            "failed",
            "interrupted",
        }:
            raise ValueError("research_attempt_invalid")
        seen.add(url)
        if state == "completed":
            if (
                url not in by_url
                or attempt["record_sha256"] != _digest(by_url[url])
                or attempt["error"] is not None
            ):
                raise ValueError("research_attempt_record_mismatch")
        elif attempt["record_sha256"] is not None or (
            attempt["error"] is not None and not isinstance(attempt["error"], str)
        ):
            raise ValueError("research_attempt_invalid")
    if set(by_url) != {
        _public_url(row["url"]) for row in attempts if row["state"] == "completed"
    }:
        raise ValueError("research_attempt_record_mismatch")
    observations = _observations(acquired, card_metadata)
    limitations = []
    if discovery_outcome != "completed":
        limitations.append("discovery_" + discovery_outcome)
    if not observations:
        limitations.append("no_useful_observations")
    if not any(row["applicability"] == "exact_list" for row in observations):
        limitations.append("no_verified_exact_guide_observations")
    limitations.extend(
        "acquisition_" + str(row["error"] or row["state"])
        for row in attempts
        if row["state"] != "completed"
    )
    return _seal(
        {
            "schema_version": 1,
            "discovery_outcome": discovery_outcome,
            "attempts": attempts,
            "deadline_utc": deadline_utc,
            "observations": observations,
            "limitations": sorted(set(limitations)),
        }
    )
