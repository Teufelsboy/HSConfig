from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json


_OPERATOR_DOCS = Path(__file__).resolve().parents[2] / "docs" / "operator"
AUDITED_DECK_CATALOG_PATH = _OPERATOR_DOCS / "audited-deck-catalog.json"
_CATALOG_IDENTITY_FIELDS = (
    "deck_name",
    "deck_code",
    "hs_id",
    "hdt_deck_id",
)
_CATALOG_REQUIRED_FIELDS = (*_CATALOG_IDENTITY_FIELDS, "matrix_role")
_CATALOG_ROLES = {"representative", "supplemental"}
_CATALOG_ROLE_COUNTS = {"representative": 11, "supplemental": 1}
_VISIBILITY_ONLY_DECK_NAMES = {"SecretMage", "HighlanderPriest"}
_VISIBILITY_ONLY_PROOF_SCOPE = "supplemental_visibility_only"
_VISIBILITY_ONLY_MATRIX_POLICY = "not_representative_visibility_only"


@dataclass(frozen=True, slots=True)
class AuditedDeckBuildIdentity:
    deck_name: str
    deck_code_sha256: str
    deck_fingerprint: str


def load_audited_deck_catalog(
    path: str | Path = AUDITED_DECK_CATALOG_PATH,
) -> list[dict[str, Any]]:
    payload = read_json(path)
    rows = payload.get("decks") if isinstance(payload, Mapping) else None
    if (
        not isinstance(payload, Mapping)
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != 1
        or not isinstance(rows, list)
        or len(rows) != 12
        or any(not isinstance(row, Mapping) for row in rows)
    ):
        raise ValueError("audited_deck_catalog_invalid")

    normalized_rows = [dict(row) for row in rows]
    if any(
        not all(_nonempty_string(row.get(field)) for field in _CATALOG_REQUIRED_FIELDS)
        or row["matrix_role"] not in _CATALOG_ROLES
        for row in normalized_rows
    ):
        raise ValueError("audited_deck_catalog_invalid")
    if any(
        len({str(row[field]) for row in normalized_rows}) != len(normalized_rows)
        for field in _CATALOG_IDENTITY_FIELDS
    ):
        raise ValueError("audited_deck_catalog_invalid")
    if {
        role: sum(row["matrix_role"] == role for row in normalized_rows)
        for role in _CATALOG_ROLES
    } != _CATALOG_ROLE_COUNTS:
        raise ValueError("audited_deck_catalog_invalid")
    return normalized_rows


def load_audited_deck_build_identity(
    deck_name: str,
    path: str | Path = AUDITED_DECK_CATALOG_PATH,
) -> AuditedDeckBuildIdentity:
    normalized_name = str(deck_name).strip()
    matches = [
        row
        for row in load_audited_deck_catalog(path)
        if row["deck_name"] == normalized_name
    ]
    if len(matches) != 1:
        raise ValueError("audited_deck_build_identity_invalid")
    deck_code = str(matches[0]["deck_code"])
    try:
        decoded = decode_deck_code(deck_code)
    except (TypeError, ValueError) as error:
        raise ValueError("audited_deck_build_identity_invalid") from error
    if (
        decoded.get("card_count_total") != 30
        or decoded.get("unresolved_identity_count") != 0
    ):
        raise ValueError("audited_deck_build_identity_invalid")
    return AuditedDeckBuildIdentity(
        deck_name=normalized_name,
        deck_code_sha256=sha256(deck_code.encode("utf-8")).hexdigest(),
        deck_fingerprint=stable_deck_fingerprint(
            (str(card["card_id"]), int(card["count"]))
            for card in decoded["cards"]
        ),
    )


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
        not isinstance(payload, Mapping)
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != 1
        or not isinstance(rows, list)
        or any(not isinstance(row, Mapping) for row in rows)
        or not _nonempty_string(catalog_reference)
    ):
        raise ValueError("audited_role_manifest_invalid")

    catalog_path = manifest_path.parent / str(catalog_reference)
    identities = {
        str(row["deck_name"]): row
        for row in load_audited_deck_catalog(catalog_path)
    }
    role_rows = [dict(row) for row in rows]
    deck_names = [row.get("deck_name") for row in role_rows]
    if (
        any(not _nonempty_string(deck_name) for deck_name in deck_names)
        or len(set(deck_names)) != len(deck_names)
    ):
        raise ValueError("audited_role_manifest_invalid")

    resolved: list[dict[str, Any]] = []
    for row in role_rows:
        deck_name = str(row["deck_name"])
        identity = identities.get(deck_name)
        if identity is not None:
            resolved.append({**row, **identity})
            continue
        if not _valid_visibility_only_identity(row):
            raise ValueError("audited_role_manifest_invalid")
        resolved.append(row)
    return resolved


def _valid_visibility_only_identity(row: Mapping[str, Any]) -> bool:
    if not (
        row.get("deck_name") in _VISIBILITY_ONLY_DECK_NAMES
        and _nonempty_string(row.get("deck_code"))
        and row.get("proof_scope") == _VISIBILITY_ONLY_PROOF_SCOPE
        and row.get("matrix_policy") == _VISIBILITY_ONLY_MATRIX_POLICY
    ):
        return False
    try:
        decoded = decode_deck_code(str(row["deck_code"]))
    except (TypeError, ValueError):
        return False
    return (
        decoded.get("card_count_total") == 30
        and decoded.get("unresolved_identity_count") == 0
    )


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


__all__ = (
    "AUDITED_DECK_CATALOG_PATH",
    "AuditedDeckBuildIdentity",
    "load_audited_deck_catalog",
    "load_audited_deck_build_identity",
    "load_audited_role_manifest",
)
