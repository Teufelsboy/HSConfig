import hashlib
from pathlib import Path

import pytest

from hsconfig.io import write_json
from hsconfig.runtime_apply_receipts import (
    build_fake_apply_receipt,
    package_fingerprint,
    runtime_snapshot,
    verify_fake_apply_receipt,
)


def _package(root: Path) -> Path:
    package = root / "package"
    deck = package / "CustomConfig" / "deck"
    write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(deck / "Mulligan.json", {"GameCardId": "Mulligan"})
    write_json(deck / "EX1_001.json", {"GameCardId": "EX1_001"})
    return package


def _gate() -> dict:
    return {"status": "allowed", "mode": "load_safe_apply"}


def test_package_fingerprint_binds_path_and_content(tmp_path: Path) -> None:
    package = _package(tmp_path)

    before = package_fingerprint(package)
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "changed": True},
    )
    after = package_fingerprint(package)

    assert before["package_sha256"] != after["package_sha256"]
    assert before["file_count"] == after["file_count"] == 3
    assert all(
        set(row) == {"path", "size", "sha256"}
        for row in after["files"]
    )


def test_package_fingerprint_canonically_frames_path_size_and_same_content(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    first = package / "reports" / "same-a.bin"
    second = package / "reports" / "same-b.bin"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_bytes(b"same-content")
    second.write_bytes(b"same-content")

    fingerprint = package_fingerprint(package)
    same_rows = [
        row
        for row in fingerprint["files"]
        if row["path"].startswith("reports/same-")
    ]
    assert len(same_rows) == 2
    assert same_rows[0]["sha256"] == same_rows[1]["sha256"]
    assert same_rows[0]["size"] == same_rows[1]["size"] == 12

    expected = hashlib.sha256()
    for row in fingerprint["files"]:
        expected.update(row["path"].encode("utf-8"))
        expected.update(b"\0")
        expected.update(str(row["size"]).encode("ascii"))
        expected.update(b"\0")
        expected.update(row["sha256"].encode("ascii"))
        expected.update(b"\0")
    assert fingerprint["package_sha256"] == expected.hexdigest()


def test_package_fingerprint_binds_legacy_fake_receipt_drift(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    legacy_receipt = package / "reports" / "runtime_apply_fake_receipt.json"
    write_json(legacy_receipt, {"status": "old"})
    before = package_fingerprint(package)

    write_json(legacy_receipt, {"status": "tampered"})
    after = package_fingerprint(package)

    assert before["package_sha256"] != after["package_sha256"]
    assert any(
        row["path"] == "reports/runtime_apply_fake_receipt.json"
        for row in after["files"]
    )


def test_fake_apply_receipt_is_pure_hash_bound_and_verifiable(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    runtime = tmp_path / "runtime"
    before = package_fingerprint(package)

    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        apply_gate=_gate(),
    )
    verified = verify_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        receipt=receipt,
    )

    assert receipt["status"] == "fake_apply_ready"
    assert receipt["runtime_write_performed"] is False
    assert verified["status"] == "verified"
    assert package_fingerprint(package) == before


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 999, "schema_version is not supported"),
        ("status", "failed", "receipt is not ready"),
        ("runtime_write_performed", True, "must not record a runtime write"),
    ],
)
def test_fake_apply_verification_rejects_malformed_receipt(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    package = _package(tmp_path)
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=tmp_path / "runtime",
        config_dir="deck",
        apply_gate=_gate(),
    )
    receipt[field] = value

    with pytest.raises(ValueError, match=message):
        verify_fake_apply_receipt(
            package_root=package,
            runtime_root=tmp_path / "runtime",
            config_dir="deck",
            receipt=receipt,
        )


def test_fake_apply_verification_rejects_package_drift(tmp_path: Path) -> None:
    package = _package(tmp_path)
    runtime = tmp_path / "runtime"
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        apply_gate=_gate(),
    )
    write_json(package / "CustomConfig" / "deck" / "new.json", {"new": True})

    with pytest.raises(ValueError, match="does not match package"):
        verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir="deck",
            receipt=receipt,
        )


def test_fake_apply_verification_rejects_runtime_drift(tmp_path: Path) -> None:
    package = _package(tmp_path)
    runtime = tmp_path / "runtime"
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        apply_gate=_gate(),
    )
    write_json(runtime / "CustomConfig" / "deck" / "drift.json", {"drift": True})

    with pytest.raises(ValueError, match="does not match runtime"):
        verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir="deck",
            receipt=receipt,
        )


def test_runtime_snapshot_reports_target_and_ini_hash(tmp_path: Path) -> None:
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
