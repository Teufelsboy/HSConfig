from __future__ import annotations

from unittest.mock import patch

from hsconfig.source_acquisition import collect_public_source_records


def acquire_live_test_provenance(
    content: bytes = b"<html><body>Verified test source.</body></html>",
) -> dict[str, str]:
    """Exercise the real acquisition boundary while replacing only network I/O."""

    with patch(
        "hsconfig.source_acquisition._fetch_with_validated_address",
        return_value=(200, "text/html", content),
    ):
        acquired = collect_public_source_records(
            deck_name="AcquisitionTest",
            deck_identity={
                "deck_name": "AcquisitionTest",
                "deck_fingerprint": "sha256:acquisition-test",
                "cards": [],
            },
            source_urls=["https://example.test/acquisition"],
            current_date="2026-07-26",
            resolver=lambda _hostname: ["93.184.216.34"],
        )

    return acquired["source_records"][0]["acquisition_provenance"]
