"""Intrinsic immutable request/result values for configure orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
from typing import Any

from hsconfig.configure_run_model import ConfigureRunModel
from hsconfig.package_assembler import PackageModel
from hsconfig.package_domain import (
    _ImmutableAuthorityNode,
    deep_freeze_definition,
    materialize_definition,
)


@dataclass(frozen=True, init=False)
class ConfigureRequest(_ImmutableAuthorityNode):
    deck_name: str
    deck_code: str
    output_root: Path
    runtime_root: Path | None
    apply_requested: bool
    current_date: date
    source_urls: tuple[str, ...]
    online_source: bool
    auto_source: bool
    source_evidence_json: Path | None
    source_search_results_json: Path | None
    cards_json: Path | None
    collectible_cards_json: Path | None
    full_cards_json: Path | None
    source_fixture_url_map_json: Path | None
    source_fetch_timeout_seconds: float
    allow_placeholder: bool
    json_output: bool

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(values)
        normalized["source_urls"] = tuple(str(url) for url in values["source_urls"])
        for name in (
            "output_root",
            "runtime_root",
            "source_evidence_json",
            "source_search_results_json",
            "cards_json",
            "collectible_cards_json",
            "full_cards_json",
            "source_fixture_url_map_json",
        ):
            value = values[name]
            normalized[name] = None if value is None else Path(value)
        return normalized

    def __post_init__(self) -> None:
        if not self.deck_name:
            raise ValueError("configure_deck_name_required")
        if not self.deck_code:
            raise ValueError("configure_deck_code_required")
        if not isinstance(self.current_date, date):
            raise TypeError("configure_current_date_invalid")
        if not isinstance(self.source_fetch_timeout_seconds, float) or (
            not math.isfinite(self.source_fetch_timeout_seconds)
            or self.source_fetch_timeout_seconds <= 0
        ):
            raise ValueError("configure_source_fetch_timeout_invalid")
        for name in (
            "apply_requested",
            "online_source",
            "auto_source",
            "allow_placeholder",
            "json_output",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"configure_{name}_invalid")


@dataclass(frozen=True, init=False)
class ConfigureResult(_ImmutableAuthorityNode):
    status: str
    exit_code: int
    package_model: PackageModel | None
    configure_run_model: ConfigureRunModel | None
    summary: Mapping[str, Any]

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(values)
        normalized["summary"] = deep_freeze_definition(values["summary"])
        return normalized

    def __post_init__(self) -> None:
        if not self.status:
            raise ValueError("configure_result_status_required")
        if type(self.exit_code) is not int or self.exit_code < 0:
            raise ValueError("configure_result_exit_code_invalid")
        if not isinstance(self.summary, Mapping):
            raise TypeError("configure_result_summary_invalid")
        if self.status not in {"OK", "failed"}:
            raise ValueError("configure_result_status_invalid")
        success = self.status == "OK"
        if success != (self.exit_code == 0):
            raise ValueError("configure_result_status_exit_mismatch")
        if "status" not in self.summary:
            raise ValueError("configure_result_summary_status_required")
        summary_status = self.summary["status"]
        if summary_status != self.status:
            raise ValueError("configure_result_status_mismatch")
        if success:
            if (
                not isinstance(self.package_model, PackageModel)
                or not isinstance(
                    self.configure_run_model,
                    ConfigureRunModel,
                )
            ):
                raise ValueError("configure_result_models_required")
            if self.configure_run_model.package is not self.package_model:
                raise ValueError("configure_result_package_identity_mismatch")
        elif (
            self.package_model is not None
            or self.configure_run_model is not None
        ):
            raise ValueError("configure_result_models_forbidden")

    def materialized_summary(self) -> dict[str, Any]:
        summary = materialize_definition(self.summary)
        if not isinstance(summary, dict):
            raise TypeError("configure_result_summary_invalid")
        return summary
