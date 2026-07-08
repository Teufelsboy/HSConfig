from pathlib import Path

import pytest

from hsconfig.io import write_json
from hsconfig.runtime_apply_receipts import (
    build_fake_apply_receipt,
    package_fingerprint,
    runtime_snapshot,
    verify_fake_apply_receipt,
    write_fake_apply_receipt,
    write_runtime_write_history,
)


def _package(root: Path) -> Path:
    package = root / "package"
    deck = package / "CustomConfig" / "deck"
    write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(deck / "Mulligan.json", {"GameCardId": "Mulligan"})
    write_json(deck / "EX1_001.json", {"GameCardId": "EX1_001"})
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
        },
    )
    return package


def test_package_fingerprint_changes_when_runtime_file_changes(tmp_path: Path):
    package = _package(tmp_path)

    before = package_fingerprint(package)
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "changed": True},
    )
    after = package_fingerprint(package)

    assert before["package_sha256"] != after["package_sha256"]
    assert before["file_count"] == 4
    assert after["file_count"] == 4


def test_fake_apply_receipt_is_hash_bound_and_verifiable(tmp_path: Path):
    package = _package(tmp_path)
    runtime = tmp_path / "runtime"
    apply_gate = {"status": "allowed", "mode": "source_backed_strong", "reasons": []}

    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        apply_gate=apply_gate,
    )
    path = write_fake_apply_receipt(package, receipt)
    verified = verify_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        receipt=receipt,
    )

    assert path.name == "runtime_apply_fake_receipt.json"
    assert receipt["status"] == "fake_apply_ready"
    assert receipt["runtime_write_performed"] is False
    assert verified["status"] == "verified"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 999, "schema_version is not supported"),
        ("runtime_write_performed", True, "must not record a runtime write"),
    ],
)
def test_fake_apply_verification_blocks_malformed_receipts(
    tmp_path: Path, field: str, value: object, message: str
):
    package = _package(tmp_path)
    runtime = tmp_path / "runtime"
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        apply_gate={"status": "allowed", "mode": "source_backed_strong", "reasons": []},
    )
    receipt[field] = value

    with pytest.raises(ValueError, match=message):
        verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir="deck",
            receipt=receipt,
        )


def test_fake_apply_verification_blocks_stale_package(tmp_path: Path):
    package = _package(tmp_path)
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=tmp_path / "runtime",
        config_dir="deck",
        apply_gate={"status": "allowed", "mode": "source_backed_strong", "reasons": []},
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "stale": True},
    )

    with pytest.raises(ValueError, match="fake apply receipt does not match package"):
        verify_fake_apply_receipt(
            package_root=package,
            runtime_root=tmp_path / "runtime",
            config_dir="deck",
            receipt=receipt,
        )


def test_fake_apply_verification_blocks_runtime_drift(tmp_path: Path):
    package = _package(tmp_path)
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        apply_gate={"status": "allowed", "mode": "source_backed_strong", "reasons": []},
    )
    write_json(runtime / "CustomConfig" / "deck" / "drift.json", {"drift": True})

    with pytest.raises(ValueError, match="fake apply receipt does not match runtime"):
        verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir="deck",
            receipt=receipt,
        )


def test_runtime_snapshot_reports_existing_target_and_deck_config_hash(tmp_path: Path):
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "[CONFIGS]\nDeck = deck\n",
        encoding="utf-8",
    )

    snapshot = runtime_snapshot(runtime, "deck")

    assert snapshot["target_exists"] is True
    assert snapshot["target_file_count"] == 1
    assert snapshot["deck_config_ini_exists"] is True
    assert snapshot["deck_config_ini_sha256"]


def test_write_runtime_write_history_appends_jsonl(tmp_path: Path):
    runtime = tmp_path / "runtime"

    first = write_runtime_write_history(
        runtime,
        {"status": "applied", "config_dir": "deck"},
    )
    second = write_runtime_write_history(
        runtime,
        {"status": "rolled_back", "config_dir": "deck"},
    )

    assert first == second
    lines = first.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"status": "applied"' in lines[0]
    assert '"status": "rolled_back"' in lines[1]
