from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
from ipaddress import ip_address
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener


Fetcher = Callable[[str, float], tuple[int, str, bytes]]


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if normalized_tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if normalized_tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)


def extract_visible_text(html: str) -> dict[str, str]:
    parser = _VisibleTextParser()
    parser.feed(html)
    title = " ".join(parser.title_parts).strip()
    text = " ".join(parser.text_parts).strip()
    return {"title": title, "text": text}


def collect_public_source_records(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_urls: Sequence[str],
    current_date: str | date | None = None,
    fetcher: Fetcher | None = None,
    timeout_seconds: float = 6.0,
) -> dict[str, Any]:
    fetch = fetcher or _default_fetcher
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    deduped_urls = _dedupe_urls(source_urls)
    retrieved_at = _iso_datetime(current_date)

    for url in deduped_urls:
        validation_error = validate_public_source_url(url)
        if validation_error:
            failures.append({"url": url, "error": validation_error})
            continue

        try:
            status, content_type, body = fetch(url, timeout_seconds)
        except Exception as exc:
            failures.append({"url": url, "error": type(exc).__name__})
            continue

        if 300 <= status < 400:
            redirect_error = _redirect_validation_error(content_type)
            failures.append({"url": url, "error": redirect_error or f"http_status_{status}"})
            continue

        if status < 200 or status >= 300:
            failures.append({"url": url, "error": f"http_status_{status}"})
            continue

        if "html" not in content_type.lower() and "text" not in content_type.lower():
            failures.append({"url": url, "error": f"unsupported_content_type:{content_type}"})
            continue

        parsed = extract_visible_text(body.decode("utf-8", errors="replace"))
        records.append(
            {
                "source_url": url,
                "source_title": parsed["title"] or url,
                "source_family": _infer_source_family(url, parsed["text"]),
                "retrieved_at": retrieved_at,
                "deck_match": {
                    "deck_name": deck_name,
                    "archetype": _slug(deck_name),
                    "matched_card_ids": _matched_card_ids(deck_identity, parsed["text"]),
                },
                "normalized_text": parsed["text"],
            }
        )

    report = {
        "schema_version": 1,
        "deck_name": deck_name,
        "attempted_url_count": len(deduped_urls),
        "source_record_count": len(records),
        "failed_fetch_count": len(failures),
        "failures": failures,
        "first_missing_source_action": (
            "none" if records else "add_public_guide_url_or_use_static_semantics"
        ),
    }
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "status": "OK",
        "source_records": records,
        "source_acquisition_report": report,
    }


def _default_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    opener = build_opener(_NoRedirectHandler())
    return _fetch_with_opener(url, timeout_seconds, opener)


def _fetch_with_opener(
    url: str,
    timeout_seconds: float,
    opener: OpenerDirector,
) -> tuple[int, str, bytes]:
    request = Request(url, headers={"User-Agent": "HSConfig/1.0 source acquisition"})
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            return (
                int(response.status),
                str(response.headers.get("Content-Type", "")),
                response.read(400_000),
            )
    except HTTPError as exc:
        location = str(exc.headers.get("Location", ""))
        content_type = str(exc.headers.get("Content-Type", ""))
        if location:
            content_type = f"{content_type}; location={location}".strip("; ")
        return int(exc.code), content_type, b""
    except URLError:
        raise


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


def _infer_source_family(url: str, text: str) -> str:
    lowered = f"{url} {text}".lower()
    if "mulligan" in lowered or "guide" in lowered or "keep " in lowered:
        return "guide"
    if "deck code" in lowered or "decklist" in lowered:
        return "decklist"
    return "public_page"


def _dedupe_urls(urls: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        value = str(url).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def validate_public_source_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return "non_public_https_url"
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return "non_public_https_url"
    try:
        address = ip_address(hostname)
    except ValueError:
        return None
    return None if address.is_global else "non_public_https_url"


def _redirect_validation_error(content_type: str) -> str | None:
    location = _location_from_content_type(content_type)
    if not location:
        return None
    validation_error = validate_public_source_url(location)
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
