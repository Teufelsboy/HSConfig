from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
from ipaddress import ip_address
from typing import Any, Callable, Mapping, Sequence
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


Fetcher = Callable[[str, float], tuple[int, str, bytes]]


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
        if not _is_public_https(url):
            failures.append({"url": url, "error": "non_public_https_url"})
            continue

        try:
            status, content_type, body = fetch(url, timeout_seconds)
        except Exception as exc:
            failures.append({"url": url, "error": type(exc).__name__})
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
    request = Request(url, headers={"User-Agent": "HSConfig/1.0 source acquisition"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return (
                int(response.status),
                str(response.headers.get("Content-Type", "")),
                response.read(400_000),
            )
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


def _is_public_https(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return False
    try:
        address = ip_address(hostname)
    except ValueError:
        return True
    return address.is_global


def _iso_datetime(current_date: str | date | None) -> str:
    if current_date is None:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    if isinstance(current_date, date):
        return datetime.combine(current_date, datetime.min.time()).isoformat() + "Z"
    return current_date


def _slug(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())
