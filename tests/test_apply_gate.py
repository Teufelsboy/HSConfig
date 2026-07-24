from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import write_json
from hsconfig.package_io import read_optional_profile, read_required_baseline


def _write_operator_summary(package: Path, payload: dict) -> None:
    write_json(package / "reports" / "operator_summary.json", payload)


def _write_minimal_runtime_package(package: Path) -> None:
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )


def test_apply_gate_allows_source_backed_ready_package(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
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

    gate = evaluate_apply_gate(package)

    assert gate == {
        "status": "allowed",
        "allowed": True,
        "operator_summary_path": str(package / "reports" / "operator_summary.json"),
        "mode": "load_safe_apply",
        "reasons": [
            {
                "reason": "runtime_load_safe_package",
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "next_action": "READY_TO_APPLY_OR_HANDOFF",
                "apply_policy": "ALLOWED",
                "semantic_blocker_count": 0,
            }
        ],
    }


def test_apply_gate_allows_valid_but_not_guide_strong_as_load_safe_apply(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 3}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate == {
        "status": "allowed",
        "allowed": True,
        "operator_summary_path": str(package / "reports" / "operator_summary.json"),
        "mode": "load_safe_apply",
        "reasons": [
            {
                "reason": "runtime_load_safe_package",
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
                "next_action": "READY_TO_APPLY_WITH_WARNINGS",
                "apply_policy": "ALLOWED_WITH_WARNINGS",
                "semantic_blocker_count": 1,
            }
        ],
    }


def test_apply_gate_allows_minimal_load_safe_package_without_cardid_files(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "STATIC_SEMANTICS_USABLE",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "no_cardid_runtime_rows", "count": 30}],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
    assert gate["reasons"][0]["semantic_blocker_count"] == 1


def test_apply_gate_allows_valid_runtime_surface_gap_as_load_safe_warning(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 2}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
    assert gate["reasons"][0]["semantic_blocker_count"] == 1


def test_apply_gate_allows_source_informed_apply_ready_without_flag(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": None,
                "source_gap_count": 2,
            },
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 2}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    default_gate = evaluate_apply_gate(package)

    assert default_gate["status"] == "allowed"
    assert default_gate["mode"] == "load_safe_apply"


def test_apply_gate_allows_load_safe_apply_when_source_gap_readiness_is_blocked(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "source_informed_apply_readiness": {
                "status": "blocked",
                "requires_flag": None,
                "source_gap_count": 2,
                "blocking_reasons": ["cards_need_runtime_surface"],
            },
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 2}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
    assert gate["reasons"][0]["semantic_blocker_count"] == 1


def test_apply_gate_ignores_forged_runtime_apply_fields_but_allows_valid_structure(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "normal_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 3}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"


def test_apply_gate_blocks_invalid_package(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "INVALID_PACKAGE",
            "semantic_status": "NEEDS_MORE_RESEARCH",
            "next_action": "FIX_PACKAGE_BEFORE_APPLY",
            "apply_policy": "BLOCKED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0]["reason"] == "operator_summary_not_valid_package"


@pytest.mark.parametrize("surface", ["Presume.json", "Concede.json", "CardBehavior.json"])
def test_apply_gate_blocks_normal_path_optional_surfaces(tmp_path: Path, surface: str):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
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
                f"CustomConfig\\deck\\{surface}",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "normal_path_optional_surface_present",
            "generated_file": f"CustomConfig\\deck\\{surface}",
        }
    ]


@pytest.mark.parametrize("surface", ["Presume.json", "Concede.json", "CardBehavior.json"])
def test_apply_gate_blocks_actual_optional_surface_when_summary_is_stale(
    tmp_path: Path, surface: str
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    write_json(package / "CustomConfig" / "deck" / surface, {})
    _write_operator_summary(
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

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "normal_path_optional_surface_present",
            "generated_file": str(package / "CustomConfig" / "deck" / surface),
        }
    ]


def test_apply_gate_blocks_nested_runtime_files(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    write_json(package / "CustomConfig" / "deck" / "nested" / "Presume.json", {})
    _write_operator_summary(
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

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "nested_runtime_file_present",
            "generated_file": str(package / "CustomConfig" / "deck" / "nested" / "Presume.json"),
        }
    ]


def test_apply_gate_blocks_actual_runtime_file_missing_from_summary(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    write_json(package / "CustomConfig" / "deck" / "EX1_999.json", {})
    _write_operator_summary(
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

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "actual_runtime_file_not_in_operator_summary",
            "generated_file": str(package / "CustomConfig" / "deck" / "EX1_999.json"),
        }
    ]


@pytest.mark.parametrize(
    "generated_files",
    [
        [],
        None,
        "CustomConfig\\deck\\GlobalValues.json",
        ["reports\\operator_summary.json"],
    ],
)
def test_apply_gate_blocks_actual_runtime_files_when_summary_runtime_entries_missing(
    tmp_path: Path, generated_files
):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(package / "CustomConfig" / "deck" / "GlobalValues.json", {})
    write_json(package / "CustomConfig" / "deck" / "Mulligan.json", {})
    write_json(package / "CustomConfig" / "deck" / "EX1_001.json", {})
    summary = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "next_action": "READY_TO_APPLY_OR_HANDOFF",
        "apply_policy": "ALLOWED",
        "semantic_blockers": [],
    }
    if generated_files is not None:
        summary["generated_files"] = generated_files
    _write_operator_summary(package, summary)

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "required_runtime_file_not_in_operator_summary",
        "generated_file": "CustomConfig/deck/GlobalValues.json",
    }


def test_apply_gate_blocks_unreported_cardid_file_but_allows_absent_cardid_files(
    tmp_path: Path,
):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(package / "CustomConfig" / "deck" / "GlobalValues.json", {})
    write_json(package / "CustomConfig" / "deck" / "Mulligan.json", {})
    write_json(package / "CustomConfig" / "deck" / "EX1_001.json", {})
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "actual_runtime_file_not_in_operator_summary",
            "generated_file": str(package / "CustomConfig" / "deck" / "EX1_001.json"),
        }
    ]


def test_apply_gate_blocks_missing_operator_summary(tmp_path: Path):
    gate = evaluate_apply_gate(tmp_path / "package")

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "missing_operator_summary",
            "path": str(tmp_path / "package" / "reports" / "operator_summary.json"),
        }
    ]


def test_apply_gate_blocks_summary_only_ready_package(tmp_path: Path):
    package = tmp_path / "package"
    _write_operator_summary(
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

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "missing_custom_config_directory",
        "path": str(package / "CustomConfig"),
    }


def test_apply_gate_blocks_package_without_input_manifest(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    _write_operator_summary(
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

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "missing_input_manifest",
        "path": str(package / "reports" / "input_manifest.json"),
    }


def test_apply_gate_ignores_config_usefulness_when_package_is_load_safe(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
            "config_usefulness": {
                "status": "load_safe_but_thin",
                "runtime_permission_impact": "none",
            },
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"


def test_package_io_reads_optional_profile_when_present(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "globalvalues_profile.json",
        {"status": "present", "speed": "fast"},
    )

    assert read_optional_profile(package) == {"status": "present", "speed": "fast"}


def test_package_io_returns_none_when_optional_profile_missing(tmp_path: Path):
    assert read_optional_profile(tmp_path / "package") is None


def test_package_io_requires_globalvalues_baseline(tmp_path: Path):
    with pytest.raises(ValueError, match="Missing GlobalValues baseline report"):
        read_required_baseline(tmp_path / "package")
