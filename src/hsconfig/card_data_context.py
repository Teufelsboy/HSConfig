from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from hsconfig.io import read_json


_CONTENT_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class PinnedCardDataContext:
    card_snapshot_id: str
    card_snapshot_sha256: str


def load_pinned_card_data_context(
    path: str | Path,
) -> PinnedCardDataContext:
    snapshot_path = Path(path).resolve(strict=True)
    payload = read_json(snapshot_path)
    if (
        not isinstance(payload, Mapping)
        or type(payload.get("schema_version")) is not int
        or not isinstance(payload.get("cards"), list)
    ):
        raise ValueError("card_snapshot_invalid")
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("card_snapshot_unpinned")
    snapshot_id = metadata.get("source_identifier")
    expected_sha256 = metadata.get("snapshot_sha256")
    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id.strip()
        or not isinstance(expected_sha256, str)
        or _CONTENT_SHA256_PATTERN.fullmatch(expected_sha256) is None
    ):
        raise ValueError("card_snapshot_unpinned")
    if _card_snapshot_sha256(payload) != expected_sha256:
        raise ValueError("card_snapshot_sha256_mismatch")
    return PinnedCardDataContext(
        card_snapshot_id=snapshot_id.strip(),
        card_snapshot_sha256=expected_sha256,
    )


def _card_snapshot_sha256(payload: Mapping[str, Any]) -> str:
    metadata = payload["metadata"]
    if not isinstance(metadata, Mapping):
        raise ValueError("card_snapshot_unpinned")
    digest_payload = {
        "cards": payload.get("cards"),
        "metadata": {
            str(key): value
            for key, value in metadata.items()
            if key != "snapshot_sha256"
        },
        "schema_version": payload.get("schema_version"),
    }
    canonical = json.dumps(
        digest_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


__all__ = ("PinnedCardDataContext", "load_pinned_card_data_context")
