import hashlib
import os
import subprocess
from pathlib import Path

import pytest

import hsconfig.package_io as package_io
from hsconfig.io import write_json
from hsconfig.runtime_package_match import (
    RuntimePackageMismatchError,
    _deck_name_from_manifest,
    assert_runtime_matches_package,
    build_runtime_package_match_report,
)


def _write_deck(root: Path, config_dir: str, files: dict[str, object]) -> None:
    target = root / "CustomConfig" / config_dir
    target.mkdir(parents=True)
    for name, payload in files.items():
        write_json(target / name, payload)


def _write_manifest(package: Path, deck_name: str) -> None:
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": deck_name,
            "deck_code": "fixture",
            "runtime_root": "unused",
        },
    )


def _write_raw_runtime_deck(root: Path, config_dir: str) -> str:
    content = b'{"GameCardId":"GlobalValues"}\n'
    target = root / "CustomConfig" / config_dir
    target.mkdir(parents=True)
    (target / "GlobalValues.json").write_bytes(content)
    record = (
        f"GlobalValues.json\0{len(content)}\0"
        f"{hashlib.sha256(content).hexdigest()}\n"
    ).encode("utf-8")
    return hashlib.sha256(record).hexdigest()


def _make_directory_reparse(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            pytest.skip(f"directory junction unavailable: {completed.stderr}")
        return
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {error}")


def test_runtime_deck_identity_requires_existing_input_manifest(tmp_path: Path):
    with pytest.raises(ValueError, match="requires input manifest"):
        _deck_name_from_manifest(tmp_path / "package")


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (["ShadowPriest"], "must be a JSON object"),
        (
            {"deck_name": "ShadowPriest"},
            "requires non-empty deck_name, deck_code, and runtime_root",
        ),
        (
            {
                "deck_name": "",
                "deck_code": "fixture",
                "runtime_root": "unused",
            },
            "requires non-empty deck_name, deck_code, and runtime_root",
        ),
        (
            {
                "deck_name": "ShadowPriest",
                "deck_code": "",
                "runtime_root": "unused",
            },
            "requires non-empty deck_name, deck_code, and runtime_root",
        ),
        (
            {
                "deck_name": "ShadowPriest",
                "deck_code": "fixture",
                "runtime_root": "",
            },
            "requires non-empty deck_name, deck_code, and runtime_root",
        ),
    ],
)
def test_runtime_deck_identity_rejects_unverified_input_manifest(
    tmp_path: Path,
    manifest: object,
    message: str,
):
    package = tmp_path / "package"
    write_json(package / "reports" / "input_manifest.json", manifest)

    with pytest.raises(ValueError, match=message):
        _deck_name_from_manifest(package)


def test_runtime_package_match_rejects_right_directory_for_wrong_deck_name(
    tmp_path: Path,
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, "shadowpriest", files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, "shadowpriest", files)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "WrongDeck=shadowpriest\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "mismatch"
    assert report["expected_deck_name"] == "ShadowPriest"
    assert report["matching_mapping_count"] == 0
    assert report["mapping_ambiguous"] is False


@pytest.mark.parametrize(
    ("mapping_text", "expected_status", "matching_count", "ambiguous"),
    [
        ("ShadowPriest=shadowpriest\n", "matched", 1, False),
        ("ShadowPriest=wrong-directory\n", "mismatch", 0, False),
        (
            "ShadowPriest=shadowpriest\nShadowPriest=shadowpriest\n",
            "mismatch",
            2,
            True,
        ),
        (
            "ShadowPriest=shadowpriest\nShadowPriest=wrong-directory\n",
            "mismatch",
            1,
            True,
        ),
    ],
)
def test_runtime_package_match_requires_one_exact_logical_mapping(
    tmp_path: Path,
    mapping_text: str,
    expected_status: str,
    matching_count: int,
    ambiguous: bool,
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, "shadowpriest", files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, "shadowpriest", files)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        mapping_text,
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == expected_status
    assert report["expected_deck_name"] == "ShadowPriest"
    assert report["matching_mapping_count"] == matching_count
    assert report["mapping_ambiguous"] is ambiguous


def test_runtime_package_match_normalizes_bom_comments_and_mapping_whitespace(
    tmp_path: Path,
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, "shadowpriest", files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, "shadowpriest", files)
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.write_text(
        "\ufeff[CONFIGS]\n"
        "# ShadowPriest=wrong-directory\n"
        "; WrongDeck=shadowpriest\n"
        " OtherDeck = other-config \n"
        "  ShadowPriest  =  shadowpriest  \n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "matched"
    assert report["expected_deck_name"] == "ShadowPriest"
    assert report["matching_mapping_count"] == 1
    assert report["mapping_ambiguous"] is False
    assert report["deck_config_ini"]["matched_lines"] == [
        "  ShadowPriest  =  shadowpriest  "
    ]


def test_runtime_package_match_accepts_semantically_equal_json(tmp_path: Path):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {
        "GlobalValues.json": {"GameCardId": "GlobalValues", "Face": {"values": [{"condition": "*", "value": "1"}]}},
        "Mulligan.json": {"Mulligan": {"values": []}},
        "NX2_019.json": {"GameCardId": "NX2_019", "BeforeBattlecryTargetBonus": {"values": []}},
    }
    _write_deck(package, "shadowpriest", files)
    _write_manifest(package, "ShadowPriest")
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
    _write_manifest(package, "ShadowPriest")
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
    _write_manifest(package, "ShadowPriest")
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
    _write_manifest(package, "ShadowPriest")
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


def test_runtime_package_match_detects_nested_boolean_numeric_mismatches(
    tmp_path: Path,
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_deck(
        package,
        "shadowpriest",
        {
            "GlobalValues.json": {
                "settings": {
                    "enabled": True,
                    "steps": [{"active": False}],
                }
            }
        },
    )
    _write_manifest(package, "ShadowPriest")
    _write_deck(
        runtime,
        "shadowpriest",
        {
            "GlobalValues.json": {
                "settings": {
                    "enabled": 1,
                    "steps": [{"active": 0}],
                }
            }
        },
    )
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "ShadowPriest=shadowpriest\n", encoding="utf-8"
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "mismatch"
    assert report["semantic_mismatch_count"] == 1
    assert report["semantic_mismatches"] == [
        {
            "file": "GlobalValues.json",
            "missing_keys_in_runtime": [],
            "extra_keys_in_runtime": [],
            "changed_common_keys": ["settings"],
        }
    ]
    with pytest.raises(RuntimePackageMismatchError):
        assert_runtime_matches_package(
            package_root=package,
            runtime_root=runtime,
            config_dir="shadowpriest",
        )


@pytest.mark.parametrize(
    ("package_value", "runtime_value"),
    [(True, 1), (False, 0)],
)
def test_runtime_package_match_distinguishes_root_boolean_from_number(
    tmp_path: Path,
    package_value: bool,
    runtime_value: int,
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_deck(package, "shadowpriest", {"GlobalValues.json": package_value})
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, "shadowpriest", {"GlobalValues.json": runtime_value})
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "ShadowPriest=shadowpriest\n", encoding="utf-8"
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "mismatch"
    assert report["runtime_write_performed"] is False
    assert report["runtime_permission_impact"] == "none"
    assert report["semantic_mismatch_count"] == 1
    assert report["semantic_mismatches"][0]["changed_common_keys"] == ["__root__"]
    with pytest.raises(RuntimePackageMismatchError):
        assert_runtime_matches_package(
            package_root=package,
            runtime_root=runtime,
            config_dir="shadowpriest",
        )


@pytest.mark.parametrize(
    "config_dir",
    ["", " ", ".", "..", "shadow/priest", "shadow\\priest"],
)
def test_runtime_package_match_rejects_unsafe_explicit_config_dir(
    tmp_path: Path,
    config_dir: str,
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, "shadowpriest", files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, "shadowpriest", files)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "ShadowPriest=shadowpriest\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Invalid config directory name"):
        build_runtime_package_match_report(
            package_root=package,
            runtime_root=runtime,
            config_dir=config_dir,
        )


def test_runtime_package_match_rejects_absolute_explicit_config_dir(tmp_path: Path):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, "shadowpriest", files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, "shadowpriest", files)

    with pytest.raises(ValueError, match="Invalid config directory name"):
        build_runtime_package_match_report(
            package_root=package,
            runtime_root=runtime,
            config_dir=str(tmp_path),
        )


def test_runtime_package_match_separates_logical_and_versioned_config_names(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    versioned = f"{logical}--sha256-{'a' * 64}"
    files = {
        "GlobalValues.json": {"GameCardId": "GlobalValues"},
        "Mulligan.json": {"Mulligan": {"values": []}},
    }
    _write_deck(package, logical, files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, versioned, files)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "[OTHER]\n"
        f"ShadowPriest = {logical}\n"
        "[configs]\n"
        f"shadowpriest = {versioned}\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        logical_config_dir=logical,
        runtime_config_dir=versioned,
    )

    assert report["status"] == "matched"
    assert report["logical_config_dir"] == logical
    assert report["runtime_config_dir"] == versioned
    assert report["config_dir"] == versioned
    assert report["matching_mapping_count"] == 1
    assert report["mapping_ambiguous"] is False
    assert report["runtime_write_performed"] is False


def test_runtime_package_match_auto_resolves_active_versioned_config(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(package, logical)
    versioned = f"{logical}--sha256-{digest}"
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(runtime, versioned)
    _write_deck(
        runtime,
        logical,
        {"GlobalValues.json": {"GameCardId": "Legacy"}},
    )
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "[configs]\n"
        f"ShadowPriest = {versioned}\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
    )

    assert report["status"] == "matched"
    assert report["logical_config_dir"] == logical
    assert report["runtime_config_dir"] == versioned
    assert report["config_dir"] == versioned
    assert report["runtime_config_path"] == str(
        runtime / "CustomConfig" / versioned
    )


def test_runtime_package_match_auto_resolution_rejects_sectionless_mapping(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(package, logical)
    versioned = f"{logical}--sha256-{digest}"
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(runtime, versioned)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"ShadowPriest = {versioned}\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
    )

    assert report["status"] == "mismatch"
    assert report["matching_mapping_count"] == 0
    assert report["runtime_config_dir"] == logical


@pytest.mark.parametrize(
    "mapped_config_dir",
    [
        "shadowpriest",
        f"otherdeck--sha256-{'0' * 64}",
        f"shadowpriest--sha256-{'0' * 64}",
        f"shadowpriest--sha256-{'A' * 64}",
    ],
)
def test_runtime_package_match_auto_resolution_requires_applied_package_identity(
    tmp_path: Path,
    mapped_config_dir: str,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(package, logical)
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(runtime, mapped_config_dir)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {mapped_config_dir}\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
    )

    assert report["status"] == "mismatch"
    assert report["runtime_config_dir"] == logical
    assert report["expected_runtime_config_dir"] == (
        f"{logical}--sha256-{digest}"
    )
    assert report["runtime_mapping_identity_valid"] is False


def test_runtime_package_match_auto_resolution_rejects_empty_package(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    digest = hashlib.sha256(b"").hexdigest()
    versioned = f"{logical}--sha256-{digest}"
    (package / "CustomConfig" / logical).mkdir(parents=True)
    _write_manifest(package, "ShadowPriest")
    (runtime / "CustomConfig" / versioned).mkdir(parents=True)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {versioned}\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
    )

    assert report["status"] == "mismatch"
    assert report["package_file_count"] == 0


def test_runtime_package_match_auto_resolution_binds_runtime_tree_digest(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(package, logical)
    versioned = f"{logical}--sha256-{digest}"
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(runtime, versioned)
    (runtime / "CustomConfig" / versioned / "unexpected.txt").write_text(
        "not part of the applied package",
        encoding="utf-8",
    )
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {versioned}\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
    )

    assert report["status"] == "mismatch"
    assert report["runtime_mapping_identity_valid"] is True
    assert report["runtime_tree_identity_valid"] is False


def test_runtime_package_match_auto_resolution_rejects_runtime_junction(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    external = tmp_path / "external-runtime-config"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(package, logical)
    versioned = f"{logical}--sha256-{digest}"
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(tmp_path / "external", "config")
    external = tmp_path / "external" / "CustomConfig" / "config"
    custom_config = runtime / "CustomConfig"
    custom_config.mkdir(parents=True)
    _make_directory_reparse(custom_config / versioned, external)
    (custom_config / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {versioned}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="filesystem"):
        build_runtime_package_match_report(
            package_root=package,
            runtime_root=runtime,
        )


def test_runtime_package_match_rejects_hardlinked_deck_config_ini(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(package, logical)
    versioned = f"{logical}--sha256-{digest}"
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(runtime, versioned)
    external_ini = tmp_path / "external-deck-config.ini"
    external_ini.write_text(
        f"[configs]\nShadowPriest = {versioned}\n",
        encoding="utf-8",
    )
    os.link(external_ini, runtime / "CustomConfig" / "deck_config.ini")

    with pytest.raises(ValueError, match="filesystem"):
        build_runtime_package_match_report(
            package_root=package,
            runtime_root=runtime,
        )


def test_runtime_package_match_rejects_runtime_custom_config_junction(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    external_runtime = tmp_path / "external-runtime"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(package, logical)
    versioned = f"{logical}--sha256-{digest}"
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(external_runtime, versioned)
    (external_runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {versioned}\n",
        encoding="utf-8",
    )
    runtime.mkdir()
    _make_directory_reparse(
        runtime / "CustomConfig",
        external_runtime / "CustomConfig",
    )

    with pytest.raises(ValueError, match="filesystem"):
        build_runtime_package_match_report(
            package_root=package,
            runtime_root=runtime,
        )


def test_runtime_package_match_rejects_package_custom_config_junction(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    external_package = tmp_path / "external-package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(external_package, logical)
    versioned = f"{logical}--sha256-{digest}"
    package.mkdir()
    _write_manifest(package, "ShadowPriest")
    _make_directory_reparse(
        package / "CustomConfig",
        external_package / "CustomConfig",
    )
    _write_raw_runtime_deck(runtime, versioned)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {versioned}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="filesystem"):
        build_runtime_package_match_report(
            package_root=package,
            runtime_root=runtime,
        )


def test_runtime_package_match_explicit_arguments_reject_runtime_junction(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    external = tmp_path / "external-runtime-config"
    logical = "shadowpriest"
    versioned = f"{logical}--sha256-{'0' * 64}"
    _write_raw_runtime_deck(package, logical)
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(tmp_path / "external", "config")
    external = tmp_path / "external" / "CustomConfig" / "config"
    custom_config = runtime / "CustomConfig"
    custom_config.mkdir(parents=True)
    _make_directory_reparse(custom_config / versioned, external)
    (custom_config / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {versioned}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="filesystem"):
        build_runtime_package_match_report(
            package_root=package,
            runtime_root=runtime,
            logical_config_dir=logical,
            runtime_config_dir=versioned,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows directory lease contract")
def test_runtime_package_match_holds_selected_child_during_file_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    digest = _write_raw_runtime_deck(package, logical)
    versioned = f"{logical}--sha256-{digest}"
    _write_manifest(package, "ShadowPriest")
    _write_raw_runtime_deck(runtime, versioned)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {versioned}\n",
        encoding="utf-8",
    )
    selected = runtime / "CustomConfig" / versioned
    parked = tmp_path / "parked-runtime-config"
    original_read = package_io.read_file_no_follow
    attempted = False
    blocked = False
    selected_read_count = 0

    def read_with_directory_replacement_attempt(
        path: Path,
        *,
        expected_status: os.stat_result,
        maximum_size: int,
    ) -> bytes:
        nonlocal attempted, blocked, selected_read_count
        if Path(path).parent == selected:
            selected_read_count += 1
        if not attempted and selected_read_count == 2:
            attempted = True
            try:
                selected.rename(parked)
            except OSError:
                blocked = True
            else:
                try:
                    _make_directory_reparse(selected, parked)
                    return original_read(
                        path,
                        expected_status=expected_status,
                        maximum_size=maximum_size,
                    )
                finally:
                    if os.path.lexists(selected):
                        selected.rmdir()
                    parked.rename(selected)
        return original_read(
            path,
            expected_status=expected_status,
            maximum_size=maximum_size,
        )

    monkeypatch.setattr(
        package_io,
        "read_file_no_follow",
        read_with_directory_replacement_attempt,
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
    )

    assert report["status"] == "matched"
    assert attempted is True
    assert blocked is True


@pytest.mark.skipif(os.name != "nt", reason="Windows case-insensitive paths")
def test_runtime_package_match_explicit_names_are_case_insensitive_on_windows(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    runtime_name = "runtime-v1"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, logical, files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, runtime_name, files)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\nShadowPriest = {runtime_name}\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        logical_config_dir="ShadowPriest",
        runtime_config_dir="Runtime-V1",
    )

    assert report["status"] == "matched"
    assert report["logical_config_dir"] == logical
    assert report["runtime_config_dir"] == runtime_name


@pytest.mark.parametrize(
    ("mapping_kind", "mapping_ambiguous"),
    [
        ("absent", False),
        ("duplicate", True),
        ("unsafe", False),
    ],
)
def test_runtime_package_match_auto_resolution_requires_one_safe_mapping(
    tmp_path: Path,
    mapping_kind: str,
    mapping_ambiguous: bool,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    versioned = f"{logical}--sha256-{'a' * 64}"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, logical, files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, logical, files)
    _write_deck(runtime, versioned, files)
    write_json(
        runtime / "outside" / "GlobalValues.json",
        {"GameCardId": "GlobalValues"},
    )
    mapping_text = {
        "absent": "[configs]\nOtherDeck = shadowpriest\n",
        "duplicate": (
            "[configs]\n"
            f"ShadowPriest = {versioned}\n"
            f"shadowpriest = {versioned}\n"
        ),
        "unsafe": "[configs]\nShadowPriest = .." + chr(92) + "outside\n",
    }[mapping_kind]
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        mapping_text,
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
    )

    assert report["status"] == "mismatch"
    assert report["runtime_config_dir"] == logical
    assert report["runtime_config_path"] == str(
        runtime / "CustomConfig" / logical
    )
    assert report["mapping_ambiguous"] is mapping_ambiguous


def test_runtime_package_match_uses_configs_section_and_casefolded_deck_keys(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {"GlobalValues.json": {"GameCardId": "GlobalValues"}}
    _write_deck(package, "shadowpriest", files)
    _write_manifest(package, "ShadowPriest")
    _write_deck(runtime, "runtime-v1", files)
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.write_text(
        "[OTHER]\nShadowPriest = runtime-v1\n"
        "[CONFIGS]\nshadowpriest = runtime-v1\n",
        encoding="utf-8",
    )

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        logical_config_dir="shadowpriest",
        runtime_config_dir="runtime-v1",
    )

    assert report["status"] == "matched"
    assert report["deck_config_ini"]["matched_lines"] == [
        "shadowpriest = runtime-v1"
    ]

    deck_config.write_text(
        "[CONFIGS]\n"
        "ShadowPriest = runtime-v1\n"
        "shadowpriest = runtime-v1\n",
        encoding="utf-8",
    )
    duplicate = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        logical_config_dir="shadowpriest",
        runtime_config_dir="runtime-v1",
    )
    assert duplicate["status"] == "mismatch"
    assert duplicate["mapping_ambiguous"] is True


def test_runtime_package_match_rejects_conflicting_legacy_and_split_arguments(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="config directory arguments conflict"):
        build_runtime_package_match_report(
            package_root=tmp_path / "package",
            runtime_root=tmp_path / "runtime",
            config_dir="shadowpriest",
            logical_config_dir="shadowpriest",
            runtime_config_dir="runtime-v1",
        )
