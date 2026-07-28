from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hsconfig.io import read_json


_OPERATOR_DOCS = Path(__file__).resolve().parents[2] / "docs" / "operator"
AUDITED_DECK_CATALOG_PATH = _OPERATOR_DOCS / "audited-deck-catalog.json"


def load_audited_deck_catalog(
    path: str | Path = AUDITED_DECK_CATALOG_PATH,
) -> list[dict[str, Any]]:
    payload = read_json(path)
    rows = payload.get("decks") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("audited_deck_catalog_invalid")
    return [dict(row) for row in rows]


def load_audited_role_manifest(
    path: str | Path,
) -> list[dict[str, Any]]:
    manifest_path = Path(path)
    payload = read_json(manifest_path)
    rows = payload.get("decks") if isinstance(payload, Mapping) else None
    catalog_reference = (
        payload.get("identity_catalog") if isinstance(payload, Mapping) else None
    )
    if (
        not isinstance(rows, list)
        or any(not isinstance(row, Mapping) for row in rows)
        or not isinstance(catalog_reference, str)
        or not catalog_reference
    ):
        raise ValueError("audited_role_manifest_invalid")

    catalog_path = manifest_path.parent / catalog_reference
    identities = {
        str(row.get("deck_name", "")): row
        for row in load_audited_deck_catalog(catalog_path)
    }
    resolved: list[dict[str, Any]] = []
    for role_row in rows:
        row = dict(role_row)
        deck_name = str(row.get("deck_name", ""))
        identity = identities.get(deck_name)
        resolved.append({**row, **identity} if identity is not None else row)
    return resolved


__all__ = (
    "AUDITED_DECK_CATALOG_PATH",
    "load_audited_deck_catalog",
    "load_audited_role_manifest",
)
