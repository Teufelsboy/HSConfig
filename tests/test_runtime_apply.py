import json
from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import read_json, write_json
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    DERIVATION_RECEIPT_SCHEMA_VERSION,
    build_package_derivation_receipt,
    write_package_derivation_receipt,
)
from hsconfig.runtime_package_match import RuntimePackageMismatchError
from hsconfig.runtime_apply import apply_package, plan_apply_package


def _write_validation_reports(package: Path, globalvalues: dict) -> None:
    write_json(package / "reports" / "globalvalues_baseline.json", globalvalues)
    write_json(
        package / "reports" / "globalvalues_profile.json",
        {
            "key_count": len(globalvalues),
            "keys": {key: {"status": "unchanged"} for key in globalvalues},
            "generated_overlay_keys": [],
            "summary": {"all_expected_overlay_keys_accounted_for": True},
            "expected_overlay_keys": [],
            "missing_overlay_keys": [],
        },
    )


def _write_operator_summary_with_derivation(
    package: Path,
    summary: dict,
) -> None:
    reports = package / "reports"
    manifest = read_json(reports / "input_manifest.json")
    deck_name = str(manifest.get("deck_name", "deck"))
    deck_fingerprint = "sha256:" + ("0" * 64)
    write_json(
        reports / "deck_identity.json",
        {
            "deck_name": deck_name,
            "deck_fingerprint": deck_fingerprint,
        },
    )
    write_json(
        reports / "deck_fingerprint.json",
        {"deck_fingerprint": deck_fingerprint},
    )
    write_json(
        reports / "guide_claim_bundle.json",
        {"canonical_source_receipts": []},
    )
    generated = summary.get("generated_files", [])
    generated_files = list(generated) if isinstance(generated, list) else []
    ownership = build_output_ownership_manifest(
        [
            *generated_files,
            DERIVATION_RECEIPT_PATH,
            "reports/operator_summary.json",
            "reports/output_ownership_manifest.json",
        ]
    )
    write_json(reports / "output_ownership_manifest.json", ownership)
    receipt = build_package_derivation_receipt(package)
    digest = write_package_derivation_receipt(
        package / DERIVATION_RECEIPT_PATH,
        receipt,
    )
    write_json(
        reports / "operator_summary.json",
        {
            **summary,
            "package_derivation": {
                "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
                "receipt_path": DERIVATION_RECEIPT_PATH,
                "receipt_sha256": digest,
                "verified": True,
            },
        },
    )


def _complete_package(
    tmp_path: Path,
    *,
    semantic_status: str,
    next_action: str,
    apply_policy: str,
    source_informed_apply_readiness: dict | None = None,
):
    package = tmp_path / "package"
    deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(deck / "GlobalValues.json", globalvalues)
    write_json(
        deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    _write_validation_reports(package, globalvalues)
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Gate Deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    summary = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": semantic_status,
        "next_action": next_action,
        "apply_policy": apply_policy,
        "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 1}]
        if semantic_status != "SOURCE_BACKED_STRONG"
        else [],
        "generated_files": [
            "CustomConfig\\deck\\GlobalValues.json",
            "CustomConfig\\deck\\Mulligan.json",
            "CustomConfig\\deck\\EX1_001.json",
        ],
    }
    if source_informed_apply_readiness is not None:
        summary["source_informed_apply_readiness"] = source_informed_apply_readiness
    _write_operator_summary_with_derivation(package, summary)
    return package


def _minimal_load_safe_package_without_cardid(tmp_path: Path) -> Path:
    package = tmp_path / "minimal-package"
    deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "minimal"}
    write_json(deck / "GlobalValues.json", globalvalues)
    write_json(
        deck / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "minimal",
            "Mulligan": {"values": []},
        },
    )
    _write_validation_reports(package, globalvalues)
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Minimal Deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    _write_operator_summary_with_derivation(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [{"reason": "load_safe_but_thin"}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
            ],
            "config_usefulness": {
                "status": "load_safe_but_thin",
                "runtime_permission_impact": "none",
            },
        },
    )
    return package


def _raw_complete_package_without_operator_summary(tmp_path: Path) -> Path:
    package = tmp_path / "raw-package"
    deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(deck / "GlobalValues.json", globalvalues)
    write_json(
        deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    _write_validation_reports(package, globalvalues)
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Gate Deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    return package


def _allowed_gate(package: Path) -> dict:
    return evaluate_apply_gate(package)


def _mutate_globalvalues_report(package: Path, mutation: str) -> None:
    reports = package / "reports"
    if mutation == "missing_baseline":
        (reports / "globalvalues_baseline.json").unlink()
        return
    if mutation == "missing_profile":
        (reports / "globalvalues_profile.json").unlink()
        return
    profile_path = reports / "globalvalues_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["missing_overlay_keys"] = ["GlobalMinionAttack"]
    write_json(profile_path, profile)


@pytest.mark.parametrize("operation", ["plan", "apply"])
@pytest.mark.parametrize(
    "mutation",
    ["missing_baseline", "missing_profile", "missing_overlay_keys"],
)
def test_runtime_apply_rejects_invalid_globalvalues_reports_before_any_write(
    tmp_path: Path,
    operation: str,
    mutation: str,
) -> None:
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    apply_gate = _allowed_gate(package)
    _mutate_globalvalues_report(package, mutation)

    with pytest.raises(
        ValueError,
        match="Runtime apply requires a valid complete package",
    ):
        if operation == "plan":
            plan_apply_package(
                package_root=package,
                runtime_root=runtime,
                apply_gate=apply_gate,
            )
        else:
            apply_package(
                package_root=package,
                runtime_root=runtime,
                apply_gate=apply_gate,
            )

    assert not (package / "reports" / "runtime_apply_fake_receipt.json").exists()
    assert not (package / "reports" / "runtime_apply_receipt.json").exists()
    assert not runtime.exists()


@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_runtime_apply_obeys_shared_strict_validation_result_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    from hsconfig import runtime_apply

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    apply_gate = _allowed_gate(package)
    monkeypatch.setattr(
        runtime_apply,
        "validate_complete_package",
        lambda _package: {
            "status": "failed",
            "errors": ["shared strict validation sentinel"],
            "checked_files": 0,
        },
        raising=False,
    )

    with pytest.raises(ValueError, match="shared strict validation sentinel"):
        if operation == "plan":
            plan_apply_package(
                package_root=package,
                runtime_root=runtime,
                apply_gate=apply_gate,
            )
        else:
            apply_package(
                package_root=package,
                runtime_root=runtime,
                apply_gate=apply_gate,
            )

    assert not (package / "reports" / "runtime_apply_fake_receipt.json").exists()
    assert not (package / "reports" / "runtime_apply_receipt.json").exists()
    assert not runtime.exists()


def test_apply_package_blocks_direct_write_without_operator_summary(tmp_path: Path):
    package = _raw_complete_package_without_operator_summary(tmp_path)
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="Runtime apply requires an allowed apply gate"):
        apply_package(package_root=package, runtime_root=runtime)

    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_rejects_forged_allowed_gate_without_operator_summary_path(
    tmp_path: Path,
):
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="Runtime apply requires an allowed apply gate"):
        apply_package(
            package_root=package,
            runtime_root=runtime,
            apply_gate={"status": "allowed", "mode": "source_backed_strong"},
        )

    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_rejects_forged_allowed_gate_with_matching_operator_summary_path(
    tmp_path: Path,
):
    package = _raw_complete_package_without_operator_summary(tmp_path)
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="Runtime apply requires an allowed apply gate"):
        apply_package(
            package_root=package,
            runtime_root=runtime,
            apply_gate={
                "status": "allowed",
                "operator_summary_path": str(
                    package / "reports" / "operator_summary.json"
                ),
                "mode": "source_backed_strong",
                "reasons": [],
            },
        )

    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_rejects_forged_runtime_apply_fields_in_allowed_gate(
    tmp_path: Path,
):
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="Runtime apply requires an allowed apply gate"):
        apply_package(
            package_root=package,
            runtime_root=runtime,
            apply_gate={
                "status": "allowed",
                "allowed": True,
                "operator_summary_path": str(
                    package / "reports" / "operator_summary.json"
                ),
                "mode": "source_backed_strong",
                "reasons": [],
                "runtime_apply_mode": "normal_apply",
                "runtime_apply_allowed": True,
                "runtime_apply_requires_flag": None,
            },
        )

    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_applies_valid_warning_package_without_source_informed_flag(
    tmp_path: Path,
):
    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="READY_TO_APPLY_WITH_WARNINGS",
        apply_policy="ALLOWED_WITH_WARNINGS",
        source_informed_apply_readiness={
            "status": "blocked",
            "blocking_reasons": ["cards_need_runtime_surface"],
        },
    )
    runtime = tmp_path / "runtime"

    receipt = apply_package(package_root=package, runtime_root=runtime)

    assert receipt["status"] == "applied"
    assert receipt["apply_gate"]["mode"] == "load_safe_apply"
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()


def test_apply_package_applies_minimal_load_safe_package_without_cardid(
    tmp_path: Path,
):
    package = _minimal_load_safe_package_without_cardid(tmp_path)
    runtime = tmp_path / "runtime"

    receipt = apply_package(package_root=package, runtime_root=runtime)

    assert receipt["status"] == "applied"
    assert receipt["runtime_write_performed"] is True
    assert receipt["apply_gate"]["mode"] == "load_safe_apply"
    assert receipt["copied_files"] == ["GlobalValues.json", "Mulligan.json"]
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert (runtime / "CustomConfig" / "deck" / "Mulligan.json").exists()
    assert not (runtime / "CustomConfig" / "deck" / "EX1_001.json").exists()


def test_apply_package_replaces_only_target_deck_folder(tmp_path: Path):
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )

    runtime = tmp_path / "runtime"
    stale_deck = runtime / "CustomConfig" / "deck"
    other_deck = runtime / "CustomConfig" / "other"
    write_json(stale_deck / "stale.json", {"old": True})
    write_json(other_deck / "keep.json", {"keep": True})
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.write_text("[CONFIGS]\nOther Deck = other\n", encoding="utf-8")

    receipt = apply_package(package_root=package, runtime_root=runtime, config_dir="deck")

    assert receipt["status"] == "applied"
    assert receipt["runtime_write_performed"] is True
    assert receipt["copied_files"] == ["EX1_001.json", "GlobalValues.json", "Mulligan.json"]
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert not (runtime / "CustomConfig" / "deck" / "stale.json").exists()
    assert (runtime / "CustomConfig" / "other" / "keep.json").exists()
    assert "Other Deck = other" in deck_config.read_text(encoding="utf-8")
    assert "Gate Deck = deck" in deck_config.read_text(encoding="utf-8")
    assert receipt["mapped_deck_name"] == "Gate Deck"
    assert receipt["deck_config_ini_updated"] is True
    receipt_path = package / "reports" / "runtime_apply_receipt.json"
    assert receipt_path.exists()
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == "applied"


def test_apply_package_rejects_incomplete_source_before_replacing_runtime(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(package_deck / "GlobalValues.json", globalvalues)
    _write_validation_reports(package, globalvalues)
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Gate Deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": ["CustomConfig\\deck\\GlobalValues.json"],
        },
    )
    runtime_deck = tmp_path / "runtime" / "CustomConfig" / "deck"
    write_json(runtime_deck / "Mulligan.json", {"old": True})

    with pytest.raises(ValueError, match="Runtime apply requires a valid complete package"):
        apply_package(
            package_root=package,
            runtime_root=tmp_path / "runtime",
            config_dir="deck",
        )

    assert (runtime_deck / "Mulligan.json").exists()


def test_apply_cli_rejects_incomplete_package_without_deleting_runtime(tmp_path: Path, capsys):
    package = tmp_path / "package"
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    runtime_deck = tmp_path / "runtime" / "CustomConfig" / "deck"
    write_json(runtime_deck / "Mulligan.json", {"old": True})

    from hsconfig.cli import main

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 1
    assert payload["status"] == "failed"
    assert "Missing GlobalValues baseline report" in payload["errors"][0]
    assert (runtime_deck / "Mulligan.json").exists()


def test_apply_cli_applies_valid_warning_package_without_source_informed_flag(
    tmp_path: Path, capsys
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="READY_TO_APPLY_WITH_WARNINGS",
        apply_policy="ALLOWED_WITH_WARNINGS",
        source_informed_apply_readiness={
            "status": "blocked",
            "blocking_reasons": ["cards_need_runtime_surface"],
            "source_gap_count": 1,
        },
    )
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["apply_gate"]["status"] == "allowed"
    assert payload["apply_gate"]["mode"] == "load_safe_apply"
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()


def test_apply_cli_applies_minimal_load_safe_package_without_cardid(
    tmp_path: Path,
    capsys,
):
    from hsconfig.cli import main

    package = _minimal_load_safe_package_without_cardid(tmp_path)
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["receipt"]["apply_gate"]["mode"] == "load_safe_apply"
    assert payload["receipt"]["copied_files"] == ["GlobalValues.json", "Mulligan.json"]
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert (runtime / "CustomConfig" / "deck" / "Mulligan.json").exists()


def test_apply_cli_load_safe_warning_package_ignores_optional_source_informed_flag(
    tmp_path: Path, capsys
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="READY_TO_APPLY_WITH_WARNINGS",
        apply_policy="ALLOWED_WITH_WARNINGS",
        source_informed_apply_readiness={
            "status": "blocked",
            "requires_flag": "--allow-source-informed",
            "source_gap_count": 1,
        },
    )
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--allow-source-informed",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["apply_gate"]["mode"] == "load_safe_apply"
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()


def test_apply_cli_source_informed_receipt_contains_real_operator_gate(
    tmp_path: Path,
    capsys,
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="READY_TO_APPLY_WITH_WARNINGS",
        apply_policy="ALLOWED_WITH_WARNINGS",
        source_informed_apply_readiness={
            "status": "blocked",
            "requires_flag": "--allow-source-informed",
            "source_gap_count": 1,
        },
    )
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--allow-source-informed",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    receipt = json.loads(
        (package / "reports" / "runtime_apply_receipt.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["apply_gate"]["mode"] == "load_safe_apply"
    assert receipt["apply_gate"] == payload["apply_gate"]
    assert receipt["apply_gate"]["operator_summary_path"].endswith(
        "reports\\operator_summary.json"
    ) or receipt["apply_gate"]["operator_summary_path"].endswith(
        "reports/operator_summary.json"
    )


def test_apply_cli_blocks_missing_operator_summary(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = tmp_path / "package"
    deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(deck / "GlobalValues.json", globalvalues)
    write_json(
        deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(package / "reports" / "globalvalues_baseline.json", globalvalues)
    write_json(
        package / "reports" / "globalvalues_profile.json",
        {
            "key_count": len(globalvalues),
            "keys": {key: {"status": "unchanged"} for key in globalvalues},
            "generated_overlay_keys": [],
            "summary": {"all_expected_overlay_keys_accounted_for": True},
            "expected_overlay_keys": [],
            "missing_overlay_keys": [],
        },
    )

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "blocked"
    assert payload["apply_gate"]["reasons"][0]["reason"] == "missing_operator_summary"


def test_apply_cli_blocks_empty_operator_summary_runtime_files(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    operator_path = package / "reports" / "operator_summary.json"
    summary = json.loads(operator_path.read_text(encoding="utf-8"))
    summary["generated_files"] = []
    write_json(operator_path, summary)
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "blocked"
    assert (
        payload["apply_gate"]["reasons"][0]["reason"]
        == "required_runtime_file_not_in_operator_summary"
    )
    assert (
        payload["apply_gate"]["reasons"][0]["generated_file"]
        == "CustomConfig/deck/GlobalValues.json"
    )
    assert not runtime.exists()


def test_apply_cli_returns_json_status_for_built_package(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = tmp_path / "package"
    runtime = tmp_path / "runtime"

    build_code = main(
        [
            "build",
            "--deck-name",
            "Apply Deck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--allow-placeholder",
            "--json",
        ]
    )
    capsys.readouterr()
    assert build_code == 0

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["receipt"]["target_path"].endswith("CustomConfig/apply_deck") or payload[
        "receipt"
    ]["target_path"].endswith("CustomConfig\\apply_deck")
    assert payload["receipt"]["mapped_deck_name"] == "Apply Deck"
    assert payload["receipt"]["deck_config_ini_updated"] is True
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    assert "Apply Deck = apply_deck" in deck_config.read_text(encoding="utf-8")


def test_apply_package_updates_bom_deck_config_without_duplicate_configs_section(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "shadowpriest"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(package_deck / "GlobalValues.json", globalvalues)
    write_json(package_deck / "Mulligan.json", {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}})
    write_json(
        package_deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    _write_validation_reports(package, globalvalues)
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "ShadowPriest", "deck_code": "fixture", "runtime_root": "unused"},
    )
    _write_operator_summary_with_derivation(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\shadowpriest\\GlobalValues.json",
                "CustomConfig\\shadowpriest\\Mulligan.json",
                "CustomConfig\\shadowpriest\\EX1_001.json",
            ],
        },
    )

    runtime = tmp_path / "runtime"
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.parent.mkdir(parents=True)
    deck_config.write_bytes(
        "\ufeff[CONFIGS]\r\nShadowPriest = old_shadow\r\nOther Deck = other\r\n".encode("utf-8")
    )

    receipt = apply_package(package_root=package, runtime_root=runtime)
    text = deck_config.read_text(encoding="utf-8")

    assert receipt["mapped_deck_name"] == "ShadowPriest"
    assert receipt["config_dir"] == "shadowpriest"
    assert receipt["deck_config_ini_previous_sha256"] != receipt["deck_config_ini_current_sha256"]
    assert text.count("[CONFIGS]") == 1
    assert "ShadowPriest = shadowpriest" in text
    assert "ShadowPriest = old_shadow" not in text
    assert "Other Deck = other" in text


def test_apply_package_rejects_manifest_deck_name_that_breaks_ini_mapping(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(package_deck / "GlobalValues.json", globalvalues)
    write_json(package_deck / "Mulligan.json", {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}})
    write_json(
        package_deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    _write_validation_reports(package, globalvalues)
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Bad\nDeck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    _write_operator_summary_with_derivation(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    with pytest.raises(ValueError, match="deck_config.ini"):
        apply_package(package_root=package, runtime_root=tmp_path / "runtime")

    assert not (tmp_path / "runtime" / "CustomConfig" / "deck").exists()


def test_plan_apply_package_writes_fake_receipt_without_runtime_mutation(tmp_path: Path):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    receipt = plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate=_allowed_gate(package),
    )

    assert receipt["status"] == "fake_apply_ready"
    assert receipt["runtime_write_performed"] is False
    assert (package / "reports" / "runtime_apply_fake_receipt.json").exists()
    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_cli_fake_mode_does_not_write_runtime(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--fake",
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "fake_apply_ready"
    assert payload["receipt"]["runtime_write_performed"] is False
    assert (package / "reports" / "runtime_apply_fake_receipt.json").exists()
    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_cli_from_fake_receipt_applies_matching_package(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    fake_code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--fake",
        "--json",
    ])
    capsys.readouterr()
    assert fake_code == 0

    receipt_path = package / "reports" / "runtime_apply_fake_receipt.json"
    apply_code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--from-fake-receipt",
        str(receipt_path),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert apply_code == 0
    assert payload["status"] == "applied"
    assert payload["receipt"]["fake_receipt_verified"]["status"] == "verified"
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()


def test_apply_cli_from_fake_receipt_rejects_runtime_mismatch(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    other_runtime = tmp_path / "other-runtime"

    fake_code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--fake",
        "--json",
    ])
    capsys.readouterr()
    assert fake_code == 0

    apply_code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(other_runtime),
        "--from-fake-receipt",
        str(package / "reports" / "runtime_apply_fake_receipt.json"),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert apply_code == 1
    assert payload["status"] == "failed"
    assert payload["errors"] == [
        "fake apply receipt runtime path does not match runtime"
    ]
    assert not (other_runtime / "CustomConfig" / "deck").exists()


def test_apply_cli_normal_apply_persists_actual_apply_gate_in_fake_receipt(
    tmp_path: Path, capsys
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    fake_receipt = json.loads(
        (package / "reports" / "runtime_apply_fake_receipt.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "applied"
    assert fake_receipt["apply_gate"] == payload["apply_gate"]
    assert fake_receipt["apply_gate"]["status"] == "allowed"


def test_apply_package_rejects_stale_fake_receipt_before_runtime_mutation(tmp_path: Path):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    receipt = plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate=_allowed_gate(package),
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {
            "GameCardId": "EX1_001",
            "ConfigComment": "changed",
            "InHandPlayPriority": {"values": [{"condition": "*", "value": 100}]},
        },
    )

    with pytest.raises(ValueError, match="package_derivation_mismatch"):
        apply_package(package_root=package, runtime_root=runtime, fake_receipt=receipt)

    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_rejects_corrupted_runtime_json_before_runtime_mutation(
    tmp_path: Path,
):
    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="READY_TO_APPLY_WITH_WARNINGS",
        apply_policy="ALLOWED_WITH_WARNINGS",
        source_informed_apply_readiness={
            "status": "blocked",
            "blocking_reasons": ["cards_need_runtime_surface"],
        },
    )
    runtime = tmp_path / "runtime"
    (package / "CustomConfig" / "deck" / "EX1_001.json").write_text(
        "{ invalid json",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Runtime apply requires a valid complete package"):
        apply_package(package_root=package, runtime_root=runtime)

    assert not (runtime / "CustomConfig").exists()
    assert not (package / "reports" / "runtime_apply_receipt.json").exists()


def test_apply_package_rejects_trailing_comma_runtime_json_before_runtime_mutation(
    tmp_path: Path,
):
    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="READY_TO_APPLY_WITH_WARNINGS",
        apply_policy="ALLOWED_WITH_WARNINGS",
        source_informed_apply_readiness={
            "status": "blocked",
            "blocking_reasons": ["cards_need_runtime_surface"],
        },
    )
    runtime = tmp_path / "runtime"
    runtime_json = package / "CustomConfig" / "deck" / "EX1_001.json"
    runtime_json.write_text(
        '{\n'
        '  "GameCardId": "EX1_001",\n'
        '  "ConfigComment": "new",\n'
        '  "InHandPlayPriority": {"values": []},\n'
        '}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Runtime apply requires a valid complete package",
    ) as excinfo:
        apply_package(package_root=package, runtime_root=runtime)

    assert "invalid JSON" in str(excinfo.value)
    assert "EX1_001.json" in str(excinfo.value)
    assert not (runtime / "CustomConfig").exists()
    assert not (package / "reports" / "runtime_apply_receipt.json").exists()


def test_apply_package_writes_history_and_backup_snapshot(tmp_path: Path):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})

    fake = plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate=_allowed_gate(package),
    )
    receipt = apply_package(package_root=package, runtime_root=runtime, fake_receipt=fake)

    assert receipt["status"] == "applied"
    assert receipt["runtime_write_performed"] is True
    assert receipt["fake_receipt_verified"]["status"] == "verified"
    assert receipt["rollback_snapshot_path"]
    assert Path(receipt["rollback_snapshot_path"]).exists()
    assert (runtime / "CustomConfig" / "hsconfig_write_history.jsonl").exists()


def test_plan_apply_package_rejects_corrupted_runtime_json_before_writing_fake_receipt(
    tmp_path: Path,
):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    (package / "CustomConfig" / "deck" / "EX1_001.json").write_text(
        "{ invalid json",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Runtime apply requires a valid complete package"):
        plan_apply_package(
            package_root=package,
            runtime_root=runtime,
            apply_gate=_allowed_gate(package),
        )

    assert not (package / "reports" / "runtime_apply_fake_receipt.json").exists()
    assert not (runtime / "CustomConfig").exists()


def test_plan_apply_package_rejects_trailing_comma_runtime_json_before_writing_fake_receipt(
    tmp_path: Path,
):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    runtime_json = package / "CustomConfig" / "deck" / "EX1_001.json"
    runtime_json.write_text(
        '{\n'
        '  "GameCardId": "EX1_001",\n'
        '  "ConfigComment": "new",\n'
        '  "InHandPlayPriority": {"values": []},\n'
        '}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Runtime apply requires a valid complete package",
    ) as excinfo:
        plan_apply_package(
            package_root=package,
            runtime_root=runtime,
            apply_gate=_allowed_gate(package),
        )

    assert "invalid JSON" in str(excinfo.value)
    assert "EX1_001.json" in str(excinfo.value)
    assert not (package / "reports" / "runtime_apply_fake_receipt.json").exists()
    assert not (runtime / "CustomConfig").exists()


def test_apply_package_rejects_runtime_drift_before_runtime_mutation(tmp_path: Path):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.write_text("[CONFIGS]\nGate Deck = deck\n", encoding="utf-8")

    fake = plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate=_allowed_gate(package),
    )
    write_json(runtime / "CustomConfig" / "deck" / "drift.json", {"drift": True})

    with pytest.raises(ValueError, match="fake apply receipt does not match runtime"):
        apply_package(package_root=package, runtime_root=runtime, fake_receipt=fake)

    assert (runtime / "CustomConfig" / "deck" / "old.json").exists()
    assert (runtime / "CustomConfig" / "deck" / "drift.json").exists()
    assert not (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert deck_config.read_text(encoding="utf-8") == "[CONFIGS]\nGate Deck = deck\n"


def test_apply_package_passes_apply_gate_to_generated_fake_receipt(tmp_path: Path):
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    allowed_gate = _allowed_gate(package)

    apply_package(package_root=package, runtime_root=runtime, apply_gate=allowed_gate)

    fake_receipt = json.loads(
        (package / "reports" / "runtime_apply_fake_receipt.json").read_text(encoding="utf-8")
    )
    assert fake_receipt["apply_gate"] == allowed_gate


def test_apply_package_backup_snapshot_names_do_not_collide_within_same_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})
    stamps = iter([1_700_000_000_000_000_001, 1_700_000_000_000_000_002])
    monkeypatch.setattr("hsconfig.runtime_apply.time.time_ns", lambda: next(stamps))

    first = apply_package(package_root=package, runtime_root=runtime)
    second = apply_package(package_root=package, runtime_root=runtime)

    assert first["rollback_snapshot_path"] != second["rollback_snapshot_path"]
    assert Path(first["rollback_snapshot_path"]).exists()
    assert Path(second["rollback_snapshot_path"]).exists()


@pytest.mark.parametrize(
    ("failure_point", "message"),
    [
        ("copytree", "copy failed"),
        ("deck_config", "deck config failed"),
        ("history", "history failed"),
        ("receipt", "receipt failed"),
    ],
)
def test_apply_package_restores_previous_runtime_when_mutation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    message: str,
):
    import hsconfig.runtime_apply as runtime_apply

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    old_deck_config_text = "[CONFIGS]\nGate Deck = old_deck\nOther Deck = other\n"
    deck_config.write_text(old_deck_config_text, encoding="utf-8")
    fake = runtime_apply.plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate=_allowed_gate(package),
    )

    if failure_point == "copytree":
        original_copytree = runtime_apply.shutil.copytree

        def fail_runtime_copytree(src, dst, *args, **kwargs):
            if (
                Path(src) == package / "CustomConfig" / "deck"
                and Path(dst) == runtime / "CustomConfig" / "deck"
            ):
                raise RuntimeError(message)
            return original_copytree(src, dst, *args, **kwargs)

        monkeypatch.setattr(runtime_apply.shutil, "copytree", fail_runtime_copytree)
    elif failure_point == "deck_config":

        def fail_deck_config(**kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(runtime_apply, "_update_deck_config_ini", fail_deck_config)
    elif failure_point == "history":

        def fail_history(*args, **kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(runtime_apply, "write_runtime_write_history", fail_history)
    else:

        def fail_receipt(*args, **kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(runtime_apply, "write_json", fail_receipt)

    with pytest.raises(RuntimeError, match=message):
        apply_package(package_root=package, runtime_root=runtime, fake_receipt=fake)

    old_json = (runtime / "CustomConfig" / "deck" / "old.json").read_text(
        encoding="utf-8"
    )
    assert json.loads(old_json) == {"old": True}
    assert not (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert deck_config.read_text(encoding="utf-8") == old_deck_config_text


def test_apply_package_appends_rollback_history_when_final_receipt_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import hsconfig.runtime_apply as runtime_apply

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    old_deck_config_text = "[CONFIGS]\nGate Deck = old_deck\nOther Deck = other\n"
    deck_config.write_text(old_deck_config_text, encoding="utf-8")
    fake = runtime_apply.plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate=_allowed_gate(package),
    )
    original_write_json = runtime_apply.write_json

    def fail_final_receipt(path, data):
        if Path(path).name == "runtime_apply_receipt.json":
            raise RuntimeError("receipt failed")
        return original_write_json(path, data)

    monkeypatch.setattr(runtime_apply, "write_json", fail_final_receipt)

    with pytest.raises(RuntimeError, match="receipt failed"):
        apply_package(package_root=package, runtime_root=runtime, fake_receipt=fake)

    history_path = runtime / "CustomConfig" / "hsconfig_write_history.jsonl"
    history_rows = [
        json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()
    ]
    assert history_rows[-1]["status"] == "rolled_back"
    assert history_rows[-1]["failed_status"] == "applied"
    assert history_rows[-1]["failure_type"] == "RuntimeError"
    assert history_rows[-1]["rollback_restored"] is True
    assert json.loads(
        (runtime / "CustomConfig" / "deck" / "old.json").read_text(encoding="utf-8")
    ) == {"old": True}
    assert not (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert deck_config.read_text(encoding="utf-8") == old_deck_config_text


def test_apply_package_receipt_includes_runtime_package_match(tmp_path: Path):
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    receipt = apply_package(package_root=package, runtime_root=runtime)

    assert receipt["status"] == "applied"
    assert receipt["runtime_package_match_status"] == "matched"
    assert receipt["runtime_package_match"]["status"] == "matched"
    assert receipt["runtime_package_match"]["runtime_write_performed"] is False
    assert receipt["runtime_package_match"]["runtime_permission_impact"] == "none"


def test_apply_package_rolls_back_when_runtime_package_match_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import hsconfig.runtime_apply as runtime_apply

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "marker.json", {"marker": "before"})

    def fail_match(**_: object) -> dict[str, object]:
        raise RuntimePackageMismatchError(
            {
                "status": "mismatch",
                "config_dir": "deck",
                "missing_in_runtime": ["EX1_001.json"],
                "extra_in_runtime": [],
                "semantic_mismatch_count": 0,
                "semantic_mismatches": [],
            }
        )

    monkeypatch.setattr(runtime_apply, "assert_runtime_matches_package", fail_match)

    with pytest.raises(RuntimePackageMismatchError):
        apply_package(package_root=package, runtime_root=runtime)

    marker = runtime / "CustomConfig" / "deck" / "marker.json"
    assert json.loads(marker.read_text(encoding="utf-8")) == {"marker": "before"}
