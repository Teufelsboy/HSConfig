from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.validate_package import validate_config_package


def validate_complete_package(package: str | Path) -> dict[str, Any]:
    """Run the strict complete-package contract used by every caller."""
    package_path = Path(package)
    baseline = read_required_baseline(package_path)
    profile = read_optional_profile(package_path)
    return validate_config_package(
        package_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
