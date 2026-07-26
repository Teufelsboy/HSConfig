from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
from http.client import HTTPSConnection
from ipaddress import ip_address
import re
from socket import create_connection, gaierror, getaddrinfo
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

from hsconfig.source_evidence_policy import classify_source_evidence


Fetcher = Callable[[str, float], tuple[int, str, bytes]]
HostResolver = Callable[[str], Sequence[str]]


class _VisibleTextParser(HTMLParser):
    PRIMARY_CONTENT_TAGS = {"main", "article"}
    EXCLUDED_CONTENT_TAGS = {
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "script",
        "style",
        "noscript",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.primary_text_parts: list[str] = []
        self.fallback_text_parts: list[str] = []
        self.publication_values: list[str] = []
        self._primary_depth = 0
        self._excluded_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        if normalized_tag == "meta":
            marker = (attributes.get("property") or attributes.get("name") or "").lower()
            if marker in {
                "article:published_time",
                "article:modified_time",
                "date",
                "datepublished",
                "datemodified",
            }:
                content = attributes.get("content", "").strip()
                if content:
                    self.publication_values.append(content)
        if normalized_tag == "time":
            value = attributes.get("datetime", "").strip()
            if value:
                self.publication_values.append(value)
        if normalized_tag in self.EXCLUDED_CONTENT_TAGS:
            self._excluded_depth += 1
        if normalized_tag in self.PRIMARY_CONTENT_TAGS:
            self._primary_depth += 1
        if normalized_tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "title":
            self._in_title = False
        if normalized_tag in self.PRIMARY_CONTENT_TAGS and self._primary_depth:
            self._primary_depth -= 1
        if normalized_tag in self.EXCLUDED_CONTENT_TAGS and self._excluded_depth:
            self._excluded_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._excluded_depth:
            return
        self.fallback_text_parts.append(text)
        if self._primary_depth:
            self.primary_text_parts.append(text)


def extract_visible_text(html: str) -> dict[str, Any]:
    parser = _VisibleTextParser()
    parser.feed(html)
    primary = " ".join(parser.primary_text_parts).strip()
    fallback = " ".join(parser.fallback_text_parts).strip()
    return {
        "title": " ".join(parser.title_parts).strip(),
        "text": primary or fallback,
        "publication_values": parser.publication_values,
        "content_scope": "main_or_article" if primary else "visible_body_fallback",
    }


def collect_public_source_records(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_urls: Sequence[str],
    current_date: str | date | None = None,
    fetcher: Fetcher | None = None,
    resolver: HostResolver | None = None,
    timeout_seconds: float = 6.0,
    candidate_registry_url_count: int = 0,
) -> dict[str, Any]:
    resolve = resolver or _default_resolver
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    deduped_urls = _dedupe_urls(source_urls)
    retrieved_at = _iso_datetime(current_date)

    for url in deduped_urls:
        fetch_url = fetchable_source_url(url)
        validation_error, validated_addresses = _public_source_url_validation(
            fetch_url,
            resolver=resolve,
        )
        if validation_error:
            failures.append({"url": url, "error": validation_error})
            continue

        try:
            if fetcher is None:
                status, content_type, body = _default_fetcher(
                    fetch_url,
                    timeout_seconds,
                    validated_addresses=validated_addresses,
                )
            else:
                status, content_type, body = fetcher(fetch_url, timeout_seconds)
        except Exception as exc:
            failures.append({"url": url, "error": type(exc).__name__})
            continue

        if 300 <= status < 400:
            redirect_error = _redirect_validation_error(content_type, resolver=resolve)
            failures.append({"url": url, "error": redirect_error or f"http_status_{status}"})
            continue

        if status < 200 or status >= 300:
            failures.append({"url": url, "error": f"http_status_{status}"})
            continue

        if "html" not in content_type.lower() and "text" not in content_type.lower():
            failures.append({"url": url, "error": f"unsupported_content_type:{content_type}"})
            continue

        parsed = extract_visible_text(body.decode("utf-8", errors="replace"))
        deck_match, deck_match_scope = _deck_match_evidence(
            deck_name,
            deck_identity,
            parsed["title"],
            parsed["text"],
        )
        source_family = _infer_source_family(url, parsed["text"])
        visibility = _source_visibility(source_family, parsed["text"])
        publication_year = _publication_year_from_metadata(
            parsed["publication_values"],
            current_date=current_date,
        )
        lane_hint = _source_lane_hint(source_family, visibility)
        strength = _source_record_strength(
            source_family=source_family,
            visibility=visibility,
            deck_match_scope=deck_match_scope,
            publication_year=publication_year,
            current_date=current_date,
        )
        record = {
            "source_url": url,
            "source_title": parsed["title"] or url,
            "source_family": source_family,
            "source_visibility": visibility,
            "source_lane_hint": lane_hint,
            "source_category": _source_category(source_family, visibility, lane_hint),
            "source_document_kind": _source_document_kind(source_family, visibility),
            "publication_year": publication_year,
            "source_record_strength": strength,
            "source_strength": strength,
            "retrieved_at": retrieved_at,
            "deck_match": deck_match,
            "deck_match_scope": deck_match_scope,
            "normalized_text": parsed["text"],
        }
        if fetch_url != url:
            record["source_fetch_url"] = fetch_url
        policy = classify_source_evidence(
            record,
            deck_name=deck_name,
            current_date=current_date,
        )
        records.append({**record, **_record_policy_fields(policy)})

    report = {
        "schema_version": 1,
        "deck_name": deck_name,
        "attempted_url_count": len(deduped_urls),
        "candidate_registry_url_count": min(
            max(0, int(candidate_registry_url_count)),
            len(deduped_urls),
        ),
        "explicit_source_url_count": max(
            0,
            len(deduped_urls)
            - min(max(0, int(candidate_registry_url_count)), len(deduped_urls)),
        ),
        "source_record_count": len(records),
        "failed_fetch_count": len(failures),
        "failures": failures,
        "first_missing_source_action": _report_first_missing_source_action(records),
    }
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "status": "OK",
        "source_records": records,
        "source_acquisition_report": report,
    }


def _report_first_missing_source_action(records: Sequence[Mapping[str, Any]]) -> str:
    if not records:
        return "add_public_guide_url_or_use_static_semantics"
    for record in records:
        action = str(record.get("first_missing_source_action") or "").strip()
        if action and action != "none":
            return action
    return "none"


def _default_fetcher(
    url: str,
    timeout_seconds: float,
    *,
    validated_addresses: Sequence[str] | None = None,
) -> tuple[int, str, bytes]:
    addresses = tuple(validated_addresses or ())
    if not addresses:
        validation_error, addresses = _public_source_url_validation(
            url,
            resolver=_default_resolver,
        )
        if validation_error:
            raise ValueError(validation_error)
    return _fetch_with_validated_address(url, timeout_seconds, addresses[0])


class _ValidatedAddressHTTPSConnection(HTTPSConnection):
    def __init__(
        self,
        hostname: str,
        port: int,
        validated_address: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout_seconds)
        self._validated_address = validated_address

    def connect(self) -> None:
        sock = create_connection(
            (self._validated_address, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _fetch_with_validated_address(
    url: str,
    timeout_seconds: float,
    validated_address: str,
) -> tuple[int, str, bytes]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("non_public_https_url")
    hostname = parsed.hostname.lower()
    port = parsed.port or 443
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    host_header = hostname if port == 443 else f"{hostname}:{port}"
    connection = _ValidatedAddressHTTPSConnection(
        hostname,
        port,
        validated_address,
        timeout_seconds,
    )
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Host": host_header,
                "User-Agent": "HSConfig/1.0 source acquisition",
            },
        )
        response = connection.getresponse()
        content_type = str(response.getheader("Content-Type", ""))
        location = str(response.getheader("Location", ""))
        if location:
            content_type = f"{content_type}; location={location}".strip("; ")
        return int(response.status), content_type, response.read(400_000)
    finally:
        connection.close()


def _matched_card_ids(deck_identity: Mapping[str, Any], text: str) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for card in deck_identity.get("cards", []):
        if not isinstance(card, Mapping):
            continue
        name = str(card.get("name", "")).strip()
        card_id = str(card.get("card_id", "")).strip()
        if name and card_id and name.lower() in lowered:
            matches.append(card_id)
    return matches


def _deck_match_evidence(
    deck_name: str,
    deck_identity: Mapping[str, Any],
    title: str,
    text: str,
) -> tuple[dict[str, Any], str]:
    matched_card_ids = _matched_card_ids(deck_identity, text)
    unique_deck_card_ids = {
        str(card.get("card_id", ""))
        for card in deck_identity.get("cards", [])
        if isinstance(card, Mapping) and str(card.get("card_id", ""))
    }
    matched_unique = sorted(set(matched_card_ids))
    overlap_ratio = (
        len(matched_unique) / len(unique_deck_card_ids)
        if unique_deck_card_ids
        else 0.0
    )
    deck_name_evidenced = bool(_norm(deck_name)) and _norm(deck_name) in _norm(
        f"{title} {text}"
    )
    if deck_name_evidenced and overlap_ratio >= 0.80:
        scope = "deck_matched"
    elif deck_name_evidenced and len(matched_unique) >= 2:
        scope = "archetype_matched"
    elif matched_unique:
        scope = "card_overlap"
    else:
        scope = "unknown"
    return (
        {
            "deck_name": deck_name if scope != "unknown" else "unknown",
            "archetype": _slug(deck_name) if deck_name_evidenced else "unknown",
            "matched_card_ids": matched_card_ids,
            "matched_card_count": len(matched_unique),
            "unique_deck_card_count": len(unique_deck_card_ids),
            "card_overlap_ratio": overlap_ratio,
        },
        scope,
    )


def _infer_source_family(url: str, text: str) -> str:
    url_lower = url.lower()
    text_lower = text.lower()
    lowered = f"{url_lower} {text_lower}"
    if any(
        marker in url_lower
        for marker in ("hsguru", "hs-guru", "hs" + "replay", "hs" + "-replay")
    ):
        return "stats"
    if "decklist" in url_lower:
        return "decklist"
    guide_word_is_negated = "no full-text guide" in text_lower or "not a guide" in text_lower
    has_guide_signal = (
        "mulligan" in text_lower
        or "keep " in text_lower
        or "/guide" in url_lower
        or ("guide" in lowered and not guide_word_is_negated)
    )
    if has_guide_signal:
        return "guide"
    if any(
        marker in lowered
        for marker in (
            "hsguru",
            "hs-guru",
            "hs" + "replay",
            "hs" + "-replay",
            "aggregate statistics",
            "statistical data",
            "deck statistics",
            "popularity",
            "performance table",
        )
    ):
        return "stats"
    if "deck code" in lowered or "decklist" in lowered:
        return "decklist"
    return "public_page"


def _source_visibility(source_family: str, text: str) -> str:
    lowered = text.lower()
    if source_family == "decklist":
        return "decklist_only"
    if source_family == "stats":
        return "stats_only"
    if len(text) < 180:
        return "snippet_only"
    if any(marker in lowered for marker in ("mulligan", "guide", "matchup", "keep ")):
        return "full_text"
    return "unknown"


def _source_lane_hint(source_family: str, visibility: str) -> str:
    if source_family == "guide" and visibility == "full_text":
        return "public_guide"
    if source_family == "decklist":
        return "decklist"
    if source_family == "stats":
        return "stats"
    if source_family in {"static_semantics", "hearthstonejson_static_semantics"}:
        return "static_semantics"
    if visibility == "snippet_only":
        return "unknown"
    return "public_page"


def _source_category(source_family: str, visibility: str, lane_hint: str) -> str:
    if lane_hint == "public_guide":
        return "public_guide"
    if source_family == "decklist":
        return "decklist"
    if source_family == "stats":
        return "stats"
    if source_family in {"static_semantics", "hearthstonejson_static_semantics"}:
        return "static_semantics"
    if visibility == "snippet_only":
        return "diagnostic"
    return lane_hint or "public_page"


def _source_document_kind(source_family: str, visibility: str) -> str:
    if source_family == "decklist":
        return "decklist"
    if source_family == "stats":
        return "stats"
    if visibility == "snippet_only":
        return "snippet"
    if source_family == "guide":
        return "guide"
    if source_family in {"static_semantics", "hearthstonejson_static_semantics"}:
        return "static_semantics"
    return "public_page"


def _publication_year_from_metadata(
    values: Sequence[str],
    *,
    current_date: str | date | None = None,
) -> int | None:
    current_year = _current_year(current_date)
    for value in values:
        match = re.search(r"\b(20[2-3]\d)\b", str(value))
        if not match:
            continue
        year = int(match.group(1))
        if current_year is None or year <= current_year:
            return year
    return None


def _source_record_strength(
    *,
    source_family: str,
    visibility: str,
    deck_match_scope: str,
    publication_year: int | None,
    current_date: str | date | None,
) -> str:
    current_year = _current_year(current_date)
    if (
        source_family == "guide"
        and visibility == "full_text"
        and deck_match_scope == "deck_matched"
        and publication_year == current_year
    ):
        return "candidate_strong"
    if visibility in {"decklist_only", "full_text"}:
        return "partial"
    return "diagnostic_only"


def _record_policy_fields(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: policy[key]
        for key in (
            "source_lane",
            "source_freshness_lane",
            "source_rank_lane",
            "deck_match_scope",
            "promotion_eligible",
            "strong_promotion_eligible",
            "trust_ceiling",
            "promotion_blockers",
            "first_missing_source_action",
        )
        if key in policy
    }


def _current_year(current_date: str | date | None) -> int | None:
    if isinstance(current_date, date):
        return current_date.year
    text = str(current_date or "")
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return datetime.utcnow().year


def _dedupe_urls(urls: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        value = str(url).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def fetchable_source_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if (
        hostname in {"reddit.com", "www.reddit.com"}
        and "/comments/" in parsed.path
        and not parsed.path.endswith(".json")
    ):
        return parsed._replace(netloc="old.reddit.com").geturl()
    return url


def _fetchable_source_url(url: str) -> str:
    return fetchable_source_url(url)


def validate_public_source_url(url: str, *, resolver: HostResolver | None = None) -> str | None:
    validation_error, _ = _public_source_url_validation(
        url,
        resolver=resolver or _default_resolver,
    )
    return validation_error


def _public_source_url_validation(
    url: str,
    *,
    resolver: HostResolver,
) -> tuple[str | None, tuple[str, ...]]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return "non_public_https_url", ()
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return "non_public_https_url", ()
    try:
        address = ip_address(hostname)
    except ValueError:
        return _hostname_validation_result(hostname, resolver)
    if not address.is_global:
        return "non_public_https_url", ()
    return None, (str(address),)


def _hostname_validation_result(
    hostname: str,
    resolver: HostResolver,
) -> tuple[str | None, tuple[str, ...]]:
    try:
        addresses = tuple(str(address) for address in resolver(hostname))
    except Exception:
        return "dns_resolution_failed", ()
    if not addresses:
        return "dns_resolution_failed", ()
    for address_value in addresses:
        try:
            address = ip_address(str(address_value))
        except ValueError:
            return "dns_resolution_failed", ()
        if not address.is_global:
            return "non_public_https_url", ()
    return None, addresses


def _default_resolver(hostname: str) -> list[str]:
    try:
        infos = getaddrinfo(hostname, None)
    except gaierror:
        raise
    return sorted({info[4][0] for info in infos})


def _redirect_validation_error(content_type: str, *, resolver: HostResolver) -> str | None:
    location = _location_from_content_type(content_type)
    if not location:
        return None
    validation_error, _ = _public_source_url_validation(location, resolver=resolver)
    if validation_error:
        return f"redirect_target_{validation_error}"
    return None


def _location_from_content_type(content_type: str) -> str:
    for segment in content_type.split(";"):
        segment = segment.strip()
        if segment.lower().startswith("location="):
            return segment.split("=", 1)[1].strip()
    return ""


def _iso_datetime(current_date: str | date | None) -> str:
    if current_date is None:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    if isinstance(current_date, date):
        return datetime.combine(current_date, datetime.min.time()).isoformat() + "Z"
    return current_date


def _slug(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _norm(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())
