from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_optimized(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-O", "-c", dedent(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_optimized_python_rejects_runtime_surface_ledger_mismatch():
    result = _run_optimized(
        """
        from hsconfig.runtime_surface_ledger import require_surface_ledger_parity

        require_surface_ledger_parity(
            expected={"expected-ledger"},
            observed={"observed-ledger"},
        )
        """
    )

    assert result.returncode != 0
    assert "runtime_surface_ledger_mismatch" in result.stdout + result.stderr


def test_optimized_python_rejects_invalid_source_document_fixture():
    result = _run_optimized(
        """
        from datetime import date
        import hsconfig.source_document_builder as source_document_builder

        source_document_builder._normalize_source_claim = (
            lambda *args, **kwargs: (None, None)
        )
        source_document_builder.build_source_document_bundle(
            deck_identity={
                "deck_name": "FixtureDeck",
                "cards": [{"card_id": "CARD_001"}],
            },
            card_metadata={
                "CARD_001": {
                    "card_id": "CARD_001",
                    "name": "Fixture Card",
                },
            },
            source_documents=[
                {
                    "source_url": "https://example.invalid/fixture",
                    "source_title": "Invalid source fixture",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-28T00:00:00Z",
                    "claims": [
                        {
                            "claim_kind": "card_role",
                            "cards": ["CARD_001"],
                            "evidence_text_short": "Fixture role.",
                            "source_confidence": "high",
                        }
                    ],
                }
            ],
            current_date=date(2026, 7, 28),
        )
        """
    )

    assert result.returncode != 0
    assert "source_document_contract_invalid" in result.stdout + result.stderr
