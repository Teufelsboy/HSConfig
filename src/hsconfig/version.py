from __future__ import annotations

__version__ = "1.0.0"


def version_payload() -> dict[str, str]:
    return {"version": __version__}


__all__ = ("__version__", "version_payload")
