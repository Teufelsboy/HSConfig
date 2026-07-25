from pathlib import Path

import pytest

from hsconfig.io import write_json
from hsconfig.runtime_package_match import (
    RuntimePackageMismatchError,
    assert_runtime_matches_package,
    build_runtime_package_match_report,
)


def _write_deck(root: Path, config_dir: str, files: dict[str, dict]) -> None:
    target = root / "CustomConfig" / config_dir
    target.mkdir(parents=True)
    for name, payload in files.items():
        write_json(target / name, payload)


def test_runtime_package_match_accepts_semantically_equal_json(tmp_path: Path):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {
        "GlobalValues.json": {"GameCardId": "GlobalValues", "Face": {"values": [{"condition": "*", "value": "1"}]}},
        "Mulligan.json": {"Mulligan": {"values": []}},
        "NX2_019.json": {"GameCardId": "NX2_019", "BeforeBattlecryTargetBonus": {"values": []}},
    }
    _write_deck(package, "shadowpriest", files)
    _write_deck(runtime, "shadowpriest", files)
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.write_text("ShadowPriest=shadowpriest\n", encoding="utf-8")

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "matched"
    assert report["runtime_write_performed"] is False
    assert report["runtime_permission_impact"] == "none"
    assert report["semantic_mismatch_count"] == 0
    assert report["deck_config_ini"]["mentions_config_dir"] is True


def test_runtime_package_match_reports_missing_and_changed_json_keys(tmp_path: Path):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_deck(
        package,
        "shadowpriest",
        {
            "GlobalValues.json": {"GameCardId": "GlobalValues"},
            "NX2_019.json": {"GameCardId": "NX2_019", "BeforeBattlecryTargetBonus": {"values": []}},
        },
    )
    _write_deck(
        runtime,
        "shadowpriest",
        {
            "GlobalValues.json": {"GameCardId": "GlobalValues"},
            "NX2_019.json": {"GameCardId": "NX2_019", "BeforePlayCardBonus": {"values": []}},
            "OLD.json": {"GameCardId": "OLD"},
        },
    )
    (runtime / "CustomConfig" / "deck_config.ini").write_text("", encoding="utf-8")

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "mismatch"
    assert report["extra_in_runtime"] == ["OLD.json"]
    assert report["semantic_mismatch_count"] == 1
    assert report["semantic_mismatches"][0]["file"] == "NX2_019.json"
    assert report["semantic_mismatches"][0]["missing_keys_in_runtime"] == ["BeforeBattlecryTargetBonus"]
    assert report["semantic_mismatches"][0]["extra_keys_in_runtime"] == ["BeforePlayCardBonus"]
    assert report["deck_config_ini"]["mentions_config_dir"] is False
    with pytest.raises(RuntimePackageMismatchError):
        assert_runtime_matches_package(
            package_root=package,
            runtime_root=runtime,
            config_dir="shadowpriest",
        )


@pytest.mark.parametrize(
    "mapping_line",
    [
        "# ShadowPriest=shadowpriest",
        "ShadowPriest=shadowpriest-extra",
        "OtherDeck=other-config",
    ],
)
def test_runtime_package_match_requires_exact_active_mapping(
    tmp_path: Path, mapping_line: str
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, "shadowpriest", files)
    _write_deck(runtime, "shadowpriest", files)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        mapping_line, encoding="utf-8"
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "mismatch"
    assert report["deck_config_ini"]["mentions_config_dir"] is False
    assert report["deck_config_ini"]["matched_lines"] == []


def test_runtime_package_match_ignores_json_directories(tmp_path: Path):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, "shadowpriest", files)
    _write_deck(runtime, "shadowpriest", files)
    (package / "CustomConfig" / "shadowpriest" / "ignored.json").mkdir()
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "ShadowPriest=shadowpriest\n", encoding="utf-8"
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "matched"
    assert report["package_file_count"] == 1
    assert report["runtime_file_count"] == 1
