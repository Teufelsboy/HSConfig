from __future__ import annotations

from hsconfig.visionai_registry import NORMAL_APPLY_AUTHORITY


def test_operator_summary_is_the_sole_normal_apply_authority() -> None:
    """Break caught: another report replaces the sole normal apply authority."""
    assert NORMAL_APPLY_AUTHORITY == "reports/operator_summary.json"
