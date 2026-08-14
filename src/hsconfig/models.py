from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InputManifest:
    deck_name: str
    deck_code: str
    runtime_root: str
    target_config_mode: str = "preview"
    format: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InputManifest:
        return cls(
            deck_name=str(data["deck_name"]),
            deck_code=str(data["deck_code"]),
            runtime_root=str(data["runtime_root"]),
            target_config_mode=str(data.get("target_config_mode", "preview")),
            format=data.get("format"),
        )


@dataclass(frozen=True)
class ConfigRow:
    file_path: str
    json_pointer: str
    source_rule_id: str
    source_refs: list[str] = field(default_factory=list)
    confidence: str = "source_backed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigRow:
        return cls(
            file_path=str(data["file_path"]),
            json_pointer=str(data["json_pointer"]),
            source_rule_id=str(data["source_rule_id"]),
            source_refs=[str(item) for item in data.get("source_refs", [])],
            confidence=str(data.get("confidence", "source_backed")),
        )
