"""Compatibility facade for package-quality diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.config_quality_checks import (
    _file_card_id,
    _runtime_value_row_keys,
    evaluate_config_quality,
    semantic_handoff_projection,
)
from hsconfig.config_quality_inputs import load_config_quality_inputs
from hsconfig.package_model import DirectoryPackageView, PackageView


def build_config_quality_report(
    package: str | Path | PackageView,
) -> dict[str, Any]:
    """Load once, then evaluate only the frozen in-memory package snapshot."""

    view: PackageView
    if isinstance(package, (str, Path)):
        view = DirectoryPackageView(Path(package))
    else:
        view = package
    return evaluate_config_quality(load_config_quality_inputs(view))


__all__ = (
    "_file_card_id",
    "_runtime_value_row_keys",
    "build_config_quality_report",
    "evaluate_config_quality",
    "load_config_quality_inputs",
    "semantic_handoff_projection",
)
