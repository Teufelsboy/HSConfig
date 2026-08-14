from __future__ import annotations

from hsconfig.visionai_registry import (
    FORBIDDEN_RUNTIME_SURFACES,
    classify_runtime_surface,
    runtime_surface_spec,
)


def test_presume_runtime_surface_is_forbidden_on_normal_path() -> None:
    """Break caught: a forbidden legacy runtime surface becomes optional."""
    spec = runtime_surface_spec("Presume.json")

    assert classify_runtime_surface("Presume.json") == "forbidden"
    assert "Presume.json" in FORBIDDEN_RUNTIME_SURFACES
    assert spec.normal_apply_allowed is False
