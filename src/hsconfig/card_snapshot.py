from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import Context, ContextVar
from hashlib import sha256
from typing import Any

from hsconfig.package_request import FrozenJsonDocument


_VALIDATED_SNAPSHOT_BYTES: ContextVar[bytes | None] = ContextVar(
    "hsconfig_validated_snapshot_bytes", default=None
)


@contextmanager
def card_snapshot_validation_scope(snapshot: FrozenJsonDocument) -> Iterator[None]:
    """Fully validate on entry; reuse only these immutable bytes until exit."""
    token = _VALIDATED_SNAPSHOT_BYTES.set(None)
    try:
        # Nested/new scopes must still perform their own full entrance check.
        validated_card_snapshot(snapshot)
        _VALIDATED_SNAPSHOT_BYTES.set(snapshot.canonical_json)
        yield
    finally:
        _VALIDATED_SNAPSHOT_BYTES.reset(token)


def card_snapshot_worker_context() -> Context:
    """Carry only the checked snapshot, never unrelated runtime authority."""
    context = Context()
    context.run(_VALIDATED_SNAPSHOT_BYTES.set, _VALIDATED_SNAPSHOT_BYTES.get())
    return context


_SNAPSHOT_FIELDS = frozenset(
    {
        "full_cards",
        "collectible_cards",
        "dbf_to_card_id",
        "captured_at",
        "upstream_version",
        "dataset_sha256",
    }
)
_NORMALIZED_CARD_FIELDS = frozenset(
    {
        "id",
        "dbf_id",
        "name",
        "type",
        "card_class",
        "classes",
        "collectible",
        "cost",
        "attack",
        "health",
        "durability",
        "text",
        "mechanics",
        "referenced_tags",
        "spell_school",
        "race",
        "races",
        "overload",
        "spell_damage",
        "targeting_arrow_text",
        "hero_power_dbf_id",
        "child_ids",
        "quest_reward",
        "play_requirements",
        "entourage",
        "source_fields",
    }
)


def build_card_snapshot(
    rows: list[dict],
    *,
    captured_at: str,
    upstream_version: str | None = None,
) -> FrozenJsonDocument:
    """Freeze one normalized, identity-checked HearthstoneJSON card dataset."""
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise ValueError("card_snapshot_invalid")
    if upstream_version is not None and (
        not isinstance(upstream_version, str) or not upstream_version.strip()
    ):
        raise ValueError("card_snapshot_invalid")
    if type(rows) is not list:
        raise ValueError("card_snapshot_invalid")

    normalized_rows = [_normalize_source_row(row) for row in rows]
    full_cards, dbf_to_card_id = _deduplicated_cards(normalized_rows)
    collectible_cards = [row for row in full_cards if row.get("collectible") is True]
    dataset_sha256 = _full_projection_sha256(full_cards)
    document = FrozenJsonDocument.from_value(
        {
            "full_cards": full_cards,
            "collectible_cards": collectible_cards,
            "dbf_to_card_id": dbf_to_card_id,
            "captured_at": captured_at,
            "upstream_version": upstream_version,
            "dataset_sha256": dataset_sha256,
        }
    )
    validated_card_snapshot(document)
    return document


def validated_card_snapshot(snapshot: FrozenJsonDocument) -> dict[str, Any]:
    """Validate the snapshot, or reuse an acquisition-local immutable check."""
    if type(snapshot) is not FrozenJsonDocument:
        raise ValueError("card_snapshot_invalid")
    value = snapshot.to_value()
    # Never reuse a mutable projection or trust a caller-provided digest/flag.
    # A different bytes object (even with equal content) takes the full path.
    if type(snapshot.canonical_json) is bytes and (
        snapshot.canonical_json is _VALIDATED_SNAPSHOT_BYTES.get()
    ):
        return value
    if not isinstance(value, dict) or set(value) != _SNAPSHOT_FIELDS:
        raise ValueError("card_snapshot_invalid")
    full_cards = value.get("full_cards")
    collectible_cards = value.get("collectible_cards")
    dbf_to_card_id = value.get("dbf_to_card_id")
    captured_at = value.get("captured_at")
    upstream_version = value.get("upstream_version")
    dataset_sha256 = value.get("dataset_sha256")
    if (
        type(full_cards) is not list
        or type(collectible_cards) is not list
        or type(dbf_to_card_id) is not dict
        or not isinstance(captured_at, str)
        or not captured_at.strip()
        or (
            upstream_version is not None
            and (not isinstance(upstream_version, str) or not upstream_version.strip())
        )
        or not isinstance(dataset_sha256, str)
    ):
        raise ValueError("card_snapshot_invalid")

    checked_rows = [_validated_normalized_row(row) for row in full_cards]
    canonical_full, expected_index = _deduplicated_cards(checked_rows)
    if canonical_full != full_cards:
        raise ValueError("card_snapshot_invalid")
    expected_collectible = [row for row in full_cards if row.get("collectible") is True]
    if collectible_cards != expected_collectible:
        raise ValueError("card_snapshot_invalid")
    if dbf_to_card_id != expected_index:
        raise ValueError("card_snapshot_invalid")
    if dataset_sha256 != _full_projection_sha256(full_cards):
        raise ValueError("card_snapshot_invalid")
    return value


def _normalize_source_row(row: dict) -> dict[str, Any]:
    if not isinstance(row, dict) or any(type(key) is not str for key in row):
        raise ValueError("card_snapshot_invalid")
    _validated_source_identity(row)

    # Delayed to avoid a module import cycle with fetch_card_snapshot().
    from hsconfig.hearthstonejson import normalize_card_row

    normalized = normalize_card_row(row)
    return {**normalized, "source_fields": sorted(row)}


def _validated_source_identity(row: dict[str, Any]) -> None:
    card_id = row.get("id")
    if type(card_id) is not str or not card_id.strip():
        raise ValueError("card_snapshot_identity_invalid")

    supplied_dbfs = [row[field] for field in ("dbfId", "dbf_id") if field in row]
    if any(type(value) is not int or value <= 0 for value in supplied_dbfs):
        raise ValueError("card_snapshot_identity_invalid")
    if len(set(supplied_dbfs)) > 1:
        raise ValueError("card_snapshot_identity_invalid")


def _validated_normalized_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != _NORMALIZED_CARD_FIELDS:
        raise ValueError("card_snapshot_invalid")
    card_id = row.get("id")
    dbf_id = row.get("dbf_id")
    source_fields = row.get("source_fields")
    if (
        type(card_id) is not str
        or not card_id.strip()
        or (dbf_id is not None and (type(dbf_id) is not int or dbf_id <= 0))
        or type(source_fields) is not list
        or any(type(field) is not str for field in source_fields)
        or source_fields != sorted(set(source_fields))
        or "id" not in source_fields
        or (
            dbf_id is not None
            and "dbfId" not in source_fields
            and "dbf_id" not in source_fields
        )
    ):
        raise ValueError("card_snapshot_invalid")
    from hsconfig.hearthstonejson import normalize_card_row

    normalized_projection = {
        key: value for key, value in row.items() if key != "source_fields"
    }
    renormalized = normalize_card_row(normalized_projection)
    if (
        FrozenJsonDocument.from_value(normalized_projection).canonical_json
        != FrozenJsonDocument.from_value(renormalized).canonical_json
    ):
        raise ValueError("card_snapshot_invalid")
    return row


def _deduplicated_cards(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    by_card_id: dict[str, dict[str, Any]] = {}
    dbf_to_card_id: dict[str, str] = {}
    for row in rows:
        card_id = row["id"]
        existing = by_card_id.get(card_id)
        if existing is not None:
            if existing != row:
                raise ValueError("card_snapshot_identity_conflict")
            continue
        dbf_id = row.get("dbf_id")
        if dbf_id is not None:
            dbf_key = str(dbf_id)
            indexed_card_id = dbf_to_card_id.get(dbf_key)
            if indexed_card_id is not None and indexed_card_id != card_id:
                raise ValueError("card_snapshot_identity_conflict")
            dbf_to_card_id[dbf_key] = card_id
        by_card_id[card_id] = row

    full_cards = [by_card_id[card_id] for card_id in sorted(by_card_id)]
    return full_cards, {key: dbf_to_card_id[key] for key in sorted(dbf_to_card_id)}


def _full_projection_sha256(full_cards: list[dict[str, Any]]) -> str:
    canonical = FrozenJsonDocument.from_value(full_cards).canonical_json
    return f"sha256:{sha256(canonical).hexdigest()}"


__all__ = ("build_card_snapshot", "validated_card_snapshot")
