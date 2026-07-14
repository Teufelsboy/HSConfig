import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_DECK_NAME = "ShadowPriest"
SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
DARKBISHOP_CARD_ID = "SW_448"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _single_deck_dir(package: Path) -> Path:
    deck_dirs = [path for path in (package / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    return deck_dirs[0]


def test_operator_docs_define_real_deck_usage_loop_without_new_gate():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "## Real-Deck Usage Loop" in text
    assert "Use this loop after a source-contract or no-default-only audit passes." in text
    assert "Do not add a second apply gate for real-deck usage." in text
    assert "Run `hsconfig configure`" in text
    assert "Open `reports/operator_summary.json` first." in text
    assert "`default_only_runtime_surfaces` must be inspected when non-empty." in text
    assert "`source_to_runtime_explainability.json` is diagnostic." in text
    assert "`source_contract_audit.json` is diagnostic." in text
    assert "Concrete defects get targeted fixes; warnings do not become blockers." in text
