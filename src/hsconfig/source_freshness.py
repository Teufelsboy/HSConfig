from __future__ import annotations

from datetime import date, datetime, timezone


STALE_SOURCE_DAYS = 365


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def classify_freshness(
    retrieved_at: str,
    *,
    current_date: date | str | None = None,
) -> str:
    retrieved = _parse_retrieved_date(retrieved_at)
    current = _normalize_current_date(current_date)
    if retrieved is None or current is None:
        return "unknown"
    return "stale" if (current - retrieved).days > STALE_SOURCE_DAYS else "current"


def is_stale_source(
    retrieved_at: str,
    *,
    current_date: date | str | None = None,
) -> bool:
    return classify_freshness(retrieved_at, current_date=current_date) == "stale"


def _parse_retrieved_date(retrieved_at: str) -> date | None:
    if not retrieved_at:
        return None
    try:
        return datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _normalize_current_date(current_date: date | str | None) -> date | None:
    if current_date is None:
        return utc_today()
    if isinstance(current_date, date):
        return current_date
    try:
        return date.fromisoformat(str(current_date))
    except ValueError:
        return None
