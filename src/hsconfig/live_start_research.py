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
from hsconfig.source_claim_compiler import compile_source_search_records
from hsconfig.source_claim_conflicts import build_claim_conflict_report


_OUTCOMES = {"completed", "unavailable", "budget_exhausted"}
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OPENING_HINT = re.compile(
    r"(?<!\w)(?:mulligan|opening\s+hand|starting\s+hand)(?!\w)", re.IGNORECASE
)
_DECISION_HINT = re.compile(
    r"(?<!\w)(?:keep|kept|discard|throw\s+back|save|target|prioriti[sz]e|avoid|trade)(?!\w)",
    re.IGNORECASE,
)
_QUALIFICATION_HINT = re.compile(
    r"(?<!\w)(?:exception|except|unless|however|instead|only\s+if|never|do\s+not|don't)(?!\w)",
    re.IGNORECASE,
)
_STRATEGIC_CONTEXT_HINT = re.compile(
    r"(?<!\w)(?:matchup|against|aggro|control|resource|removal|game\s+plan)(?!\w)",
    re.IGNORECASE,
)
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


def _research_format(raw: object) -> str:
    numeric = {1: "Wild", 2: "Standard", 3: "Classic", 4: "Twist"}
    if type(raw) is int:
        return numeric.get(raw, "Hearthstone")
    if type(raw) is str:
        token = raw.strip().upper()
        if token.startswith("FT_"):
            token = token[3:]
        return {
            "WILD": "Wild",
            "STANDARD": "Standard",
            "CLASSIC": "Classic",
            "TWIST": "Twist",
        }.get(token, "Hearthstone")
    return "Hearthstone"


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
    classes = sorted(
        {str(card.get("card_class", "")) for card in cards if card.get("card_class")}
    )
    card_class = str(
        deck_identity.get("class")
        or deck_identity.get("card_class")
        or " ".join(classes)
    )
    # Query relevance only: neither inferred archetype nor strategic authority.
    label = str(deck_identity.get("deck_name") or "Deck").strip() or "Deck"
    token_label = re.sub(r"([a-z])([A-Z])|([A-Z])(?=[A-Z][a-z])", r"\1\3 \2", label)
    label_tokens = set(re.findall(r"[a-z]{3,}", token_label.casefold())) - {
        "deck", "standard", "wild", "classic", "twist", "hearthstone",
        "death", "knight", "demon", "hunter", "druid", "mage", "paladin",
        "priest", "rogue", "shaman", "warlock", "warrior",
    }
    named_cards = [
        card for card in cards
        if isinstance(card.get("name"), str) and card["name"].strip()
    ]
    named_cards.sort(key=lambda card: (
        not bool(label_tokens & set(re.findall(r"[a-z]{3,}", str(card["name"]).casefold()))),
        not (str(card.get("card_class", "")).upper() == card_class.upper()
             and card_class.upper() not in {"", "NEUTRAL"}),
        str(card.get("card_id", "")),
        str(card["name"]).casefold(),
        str(card["name"]),
    ))
    names = []
    seen_names = set()
    for card in named_cards:
        name = " ".join(str(card["name"]).split())
        if name.casefold() not in seen_names:
            names.append(name)
            seen_names.add(name.casefold())
        if len(names) == 3:
            break
    format_name = _research_format(deck_identity.get("format"))
    query_prefix = format_name if format_name == "Hearthstone" else f"{format_name} Hearthstone"
    if not names:
        raise ValueError("research_request_signature_cards_missing")
    factual_query = " ".join(
        [query_prefix, card_class, *names, "guide mulligan"]
    ).strip()
    label_query = " ".join(
        [query_prefix, card_class, label, "guide strategy"]
    ).strip()
    choices = [*queries, factual_query, label_query]
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


def validate_research_request(
    value: object,
    *,
    run_id: str,
    deck_identity: dict,
    captured_input_sha256: str,
) -> FrozenJsonDocument:
    error = "research_request_invalid"
    fields = {
        "schema_version",
        "run_id",
        "deck_identity",
        "captured_input_sha256",
        "queries",
        "limits",
        "content_sha256",
    }
    if type(value) is not dict or set(value) != fields:
        raise ValueError(error)
    queries = value["queries"]
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["run_id"] != run_id
        or value["captured_input_sha256"] != captured_input_sha256
        or not isinstance(run_id, str)
        or not run_id.strip()
        or type(value["deck_identity"]) is not dict
        or type(deck_identity) is not dict
        or not re.fullmatch(
            r"(?:sha256:)?[0-9a-f]{64}",
            str(deck_identity.get("deck_fingerprint", "")),
        )
        or not isinstance(captured_input_sha256, str)
        or _SHA256.fullmatch(captured_input_sha256) is None
        or type(queries) is not list
        or len(queries) != 2
        or any(
            type(query) is not str
            or not query
            or query != " ".join(query.split())
            for query in queries
        )
        or len(set(queries)) != 2
        or type(value["limits"]) is not dict
        or value["limits"]
        != {
            "search_calls": 2,
            "pages": 3,
            "total_seconds": 30,
            "request_seconds": 10,
        }
        or any(type(limit) is not int for limit in value["limits"].values())
    ):
        raise ValueError(error)
    cards = deck_identity.get("cards", [])
    if type(cards) is not list or not any(
        isinstance(card, dict) and str(card.get("name", "")).strip()
        for card in cards
    ):
        raise ValueError("research_request_signature_cards_missing")
    if (
        FrozenJsonDocument.from_value(value["deck_identity"]).canonical_json
        != FrozenJsonDocument.from_value(deck_identity).canonical_json
    ):
        raise ValueError(error)
    unsigned = {key: item for key, item in value.items() if key != "content_sha256"}
    sealed = _seal(unsigned)
    if sealed.to_value() != value:
        raise ValueError(error)
    return sealed


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


def _observation_windows(text: str, metadata: dict) -> list[tuple[str, bool]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    boundaries: list[re.Match[str] | None] = [
        *re.finditer(r"(?<=[.!?])\s+|\n+", text),
        None,
    ]
    for boundary in boundaries:
        end = len(text) if boundary is None else boundary.start()
        start = cursor
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append((start, end))
        cursor = len(text) if boundary is None else boundary.end()

    matches: set[tuple[int, int]] = set()
    for card_id, card in metadata.items():
        for token in (card_id, str(card.get("name") or "")):
            if not token:
                continue
            for match in re.finditer(
                r"(?<!\w)" + re.escape(token) + r"(?!\w)",
                text,
                re.IGNORECASE,
            ):
                matches.add(match.span())

    windows: list[tuple[int, int, str, bool]] = []
    span_index = 0
    for match_start, match_end in sorted(matches):
        while span_index < len(spans) and spans[span_index][1] <= match_start:
            span_index += 1
        if (
            span_index == len(spans)
            or match_start < spans[span_index][0]
            or match_end - match_start > 600
        ):
            continue
        last_span = span_index
        while last_span + 1 < len(spans) and spans[last_span][1] < match_end:
            last_span += 1
        if match_end > spans[last_span][1]:
            continue
        left_index = max(0, span_index - 1)
        right_index = min(len(spans) - 1, last_span + 1)
        # Keep nearby cardless qualifications attached to a real card mention.
        # Extend by at most two sentences total; never join distant passages.
        remaining = 2
        candidates = sorted(
            (distance, side, index)
            for distance in (1, 2)
            for side, index in (("left", left_index - distance), ("right", right_index + distance))
            if 0 <= index < len(spans)
        )
        for _distance, side, index in candidates:
            sentence = text[spans[index][0]:spans[index][1]]
            added = left_index - index if side == "left" else index - right_index
            if (
                0 < added <= remaining
                and not _mentioned_cards(sentence, metadata)
                and (_OPENING_HINT.search(sentence) or _STRATEGIC_CONTEXT_HINT.search(sentence))
                and (_DECISION_HINT.search(sentence) or _QUALIFICATION_HINT.search(sentence))
            ):
                if side == "left":
                    left_index = index
                else:
                    right_index = index
                remaining -= added
        left = spans[left_index][0]
        right = spans[right_index][1]
        start, end = left, right
        if right - left > 600:
            before = (600 - (match_end - match_start)) // 2
            start = max(left, min(match_start - before, right - 600))
            end = start + 600
        while (
            start < match_start
            and start > 0
            and re.match(r"\w", text[start - 1])
        ):
            start += 1
        while (
            end > match_end
            and end < len(text)
            and re.match(r"\w", text[end])
        ):
            end -= 1
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if not (start <= match_start < match_end <= end):
            continue
        snippet = text[start:end]
        if snippet and _mentioned_cards(snippet, metadata):
            windows.append((start, end, snippet, start > left or end < right))

    unique: dict[str, bool] = {}
    for _start, _end, snippet, incomplete in sorted(
        windows, key=lambda item: (item[0], item[1])
    ):
        unique[snippet] = unique.get(snippet, False) or incomplete
    return list(unique.items())


def _select_observation_snippets(snippets: list[str]) -> list[str]:
    def rank(index: int) -> tuple[int, int]:
        decision = bool(_DECISION_HINT.search(snippets[index]))
        opening = bool(_OPENING_HINT.search(snippets[index]))
        qualification = bool(_QUALIFICATION_HINT.search(snippets[index]))
        score = (
            4
            if qualification
            else 3
            if decision and opening
            else 2
            if decision
            else 1
            if opening
            else 0
        )
        return -score, index

    selected = sorted(range(len(snippets)), key=rank)[:4]
    return [snippets[index] for index in sorted(selected)]


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
        windows = _observation_windows(text, metadata)
        incomplete_by_text = dict(windows)
        for snippet in _select_observation_snippets([item[0] for item in windows]):
            limitations = [
                "context_only_not_runtime_authority",
                "strategic_conflicts_require_review",
            ]
            if incomplete_by_text[snippet]:
                limitations.append("source_context_incomplete")
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


def validate_research_attempts(
    *,
    acquired: dict,
    discovery_outcome: str,
    attempts: list[dict],
    deadline_utc: float | None,
    acquisition_budget_exhausted: bool = False,
) -> None:
    """Validate persisted attempts without extracting observations or sealing a result."""
    if (
        discovery_outcome not in _OUTCOMES
        or type(attempts) is not list
        or len(attempts) > 3
        or type(acquisition_budget_exhausted) is not bool
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
    # Preserve record-only, empty-metadata validation from the old extractor.
    # Sparse records remain valid; these checks grant no source authority.
    for record in records[:3]:
        hash(record["evidence_id"])
        if not isinstance(record.get("normalized_text", ""), str):
            raise TypeError("research_source_normalized_text_invalid")


def build_research_result(
    *,
    acquired: dict,
    discovery_outcome: str,
    attempts: list[dict],
    deadline_utc: float | None,
    card_metadata: dict,
    acquisition_budget_exhausted: bool = False,
) -> FrozenJsonDocument:
    validate_research_attempts(
        acquired=acquired, discovery_outcome=discovery_outcome, attempts=attempts,
        deadline_utc=deadline_utc, acquisition_budget_exhausted=acquisition_budget_exhausted,
    )
    observations = _observations(acquired, card_metadata)
    limitations = []
    if discovery_outcome != "completed":
        limitations.append("discovery_" + discovery_outcome)
    if not observations:
        limitations.append("no_useful_observations")
    if any(
        "source_context_incomplete" in row["limitations"] for row in observations
    ):
        limitations.append("source_context_incomplete")
    if not any(row["applicability"] == "exact_list" for row in observations):
        limitations.append("no_verified_exact_guide_observations")
    limitations.extend(
        "acquisition_" + str(row["error"] or row["state"])
        for row in attempts
        if row["state"] != "completed"
    )
    if acquisition_budget_exhausted:
        limitations.append("acquisition_research_budget_exhausted")
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
