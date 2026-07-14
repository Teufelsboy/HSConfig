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
    assert "Use this loop to run `hsconfig configure`, then inspect source-contract and no-default-only diagnostics without treating them as extra gates." in text
    assert "Do not add another runtime-write authority for real-deck usage." in text
    assert "Run `hsconfig configure`" in text
    assert "Open `reports/operator_summary.json` first." in text
    assert "`default_only_runtime_surfaces` must be inspected when non-empty." in text
    assert "`source_to_runtime_explainability.json` is diagnostic." in text
    assert "`source_contract_audit.json` is diagnostic." in text
    assert "Concrete defects get targeted fixes; warnings do not become blockers." in text


def test_shadowpriest_configure_path_real_deck_loop_uses_operator_summary_without_new_gate(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )

    out = tmp_path / SHADOWPRIEST_DECK_NAME
    runtime_root = tmp_path / "runtime"

    code = main(
        [
            "configure",
            "--deck-name",
            SHADOWPRIEST_DECK_NAME,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    package = out / "04_package"
    reports = package / "reports"
    operator = _json(reports / "operator_summary.json")
    source_contract_audit = _json(reports / "source_contract_audit.json")
    source_to_runtime = _json(reports / "source_to_runtime_explainability.json")
    deck_dir = _single_deck_dir(package)
    mulligan = _json(deck_dir / "Mulligan.json")
    darkbishop = _json(deck_dir / f"{DARKBISHOP_CARD_ID}.json")

    assert code == 0
    assert payload["status"] == "OK"
    assert Path(payload["package_path"]) == package

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )

    assert operator["default_only_runtime_surfaces"] == []
    assert operator["default_only_runtime_surface_details"] == []
    assert operator["mulligan_policy_status"]["default_only"] is False
    assert operator["mulligan_policy_status"]["status"] in {
        "policy_backed",
        "source_backed",
        "source_and_policy_backed",
    }

    assert source_contract_audit["schema_version"] == 1
    assert isinstance(source_contract_audit["claim_lifecycle_rows"], list)
    assert source_to_runtime["authority"] == "diagnostic_only"
    assert source_to_runtime["apply_blocking"] is False
    assert operator["source_contract_audit_summary"]["non_blocking"] is True
    assert operator["source_to_runtime_explainability_summary"]["non_blocking"] is True
    assert operator["source_to_runtime_explainability_summary"]["closure_schema_current"] is True
    assert operator["source_to_runtime_explainability_summary"]["cards_missing_closure"] == 0

    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()

    mulligan_text = json.dumps(mulligan, sort_keys=True)
    assert DARKBISHOP_CARD_ID not in mulligan_text
    assert darkbishop["GameCardId"] == DARKBISHOP_CARD_ID
    darkbishop_text = json.dumps(darkbishop, sort_keys=True)
    assert "BeforeUseHeroPowerBonus" in darkbishop_text
    assert "hero_power" in darkbishop_text.lower()
