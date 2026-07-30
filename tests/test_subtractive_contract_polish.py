from __future__ import annotations

import inspect
import json
from pathlib import Path

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.cli import main
from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel_report
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from tests.helpers.current_apply_eligible_package import (
    write_current_apply_eligible_package,
)
import hsconfig.package_render_authority as package_render_authority
from hsconfig.surface_intent import build_surface_intent


LEGACY_SURFACES = {"Presume.json", "Concede.json", "CardBehavior.json"}

REMOVED_REPORT_ALIASES = frozenset(
    {
        "reports/global_values_key_profile_report.json",
        "reports/global_values_blocked_changes.json",
        "reports/card_behavior_suppression_report.json",
        "reports/combo_suppression_report.json",
        "reports/source_evidence_index.json",
    }
)

CANONICAL_REPORT_OWNERS = frozenset(
    {
        "reports/globalvalues_profile.json",
        "reports/global_values_authority_matrix.json",
        "reports/card_behavior_plan_report.json",
        "reports/combo_plan_report.json",
        "reports/guide_claim_bundle.json",
    }
)

DEAD_ARCHITECTURE_MODULES = (
    "compile_optional_surfaces",
    "matrix_closure",
    "matrix_visibility",
    "source_depth_closure_index",
)

ACTIVE_CODE_ROOTS = (
    Path("src"),
    Path("tests"),
    Path("scripts"),
)
ACTIVE_DOC_ROOTS = (
    Path("docs/operator"),
    Path(".agents/skills/hsconfig"),
)
NEGATIVE_CONTRACT_PATH = Path(__file__).resolve()

ACTIVE_DOC_PATHS = [
    Path("docs/operator/README.md"),
    Path("docs/operator/guide-research-policy.md"),
    Path("docs/operator/universal-wild-no-block-contract.md"),
    Path(".agents/skills/hsconfig/SKILL.md"),
    Path(".agents/skills/hsconfig/references/workflow.md"),
    Path(".agents/skills/hsconfig/references/visionai-surfaces.md"),
]

def _active_python_consumers() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for root in ACTIVE_CODE_ROOTS
            for path in root.rglob("*.py")
            if path.resolve() != NEGATIVE_CONTRACT_PATH
        )
    )


def _active_markdown_documents() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for root in ACTIVE_DOC_ROOTS
            for path in root.rglob("*.md")
        )
    )


def test_active_docs_describe_legacy_surfaces_as_non_normal_only():
    allowed_diagnostic_boundary = (
        "`semantic_handoff_status` is diagnostic and never creates a second apply gate."
    )
    for path in ACTIVE_DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "operator_summary.json" in text
        assert "legacy/diagnostic" in text or "outside the normal HSConfig output path" in text
        assert "emit Presume.json" not in text
        assert "emit Concede.json" not in text
        assert "second apply gate" not in text.replace(
            allowed_diagnostic_boundary, ""
        ).lower()


def test_contract_spine_sentinel_covers_subtractive_contract_polish():
    report = build_contract_spine_sentinel_report()
    checks = report["checks"]

    assert "legacy_surface_normal_routing" in checks
    assert "source_informed_apply_flag_policy" in checks
    assert "report_ownership_gate_files" in checks
    assert "report_ownership_unclassified_files" in checks
    assert checks["legacy_surface_normal_routing"] == []
    assert checks["source_informed_apply_flag_policy"]["behavior"] == "legacy_no_op"
    assert checks["report_ownership_gate_files"] == ["reports/operator_summary.json"]


def test_surface_intent_ignores_legacy_policy_surfaces_in_normal_path():
    contract = {
        "cards": {},
        "mulligan_anchors": [],
        "combos": [],
        "legacy_policy_surfaces_enabled": True,
        "policies": {
            "presume": [{"source_claim_ids": ["claim-presume"]}],
            "concede": [{"source_claim_ids": ["claim-concede"]}],
        },
    }

    intent = build_surface_intent(contract)

    assert set(intent["optional_surfaces"]).isdisjoint(LEGACY_SURFACES)
    assert all(row["surface"] not in LEGACY_SURFACES for row in intent["rows"])
    assert set(intent["required_surfaces"]) == {"GlobalValues.json", "Mulligan.json"}


def _write_minimal_package(
    package: Path,
    *,
    technical_status: str = "VALID_PACKAGE",
) -> None:
    write_current_apply_eligible_package(
        package,
        operator_summary={
            "technical_status": technical_status,
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
        },
    )


def test_allow_source_informed_does_not_change_apply_gate(tmp_path):
    package = tmp_path / "package"
    _write_minimal_package(package)

    normal = evaluate_apply_gate(package)
    legacy_flag = evaluate_apply_gate(package, allow_source_informed=True)

    assert legacy_flag == normal
    assert normal["status"] == "allowed"


def test_output_ownership_manifest_classifies_every_generated_file():
    from hsconfig.output_ownership_manifest import build_output_ownership_manifest

    generated_files = [
        "CustomConfig/deck/GlobalValues.json",
        "CustomConfig/deck/Mulligan.json",
        "CustomConfig/deck/SW_448.json",
        "CustomConfig/deck/Combo.json",
        "reports/operator_summary.json",
        "reports/source_contract_audit.json",
        "reports/source_to_runtime_explainability.json",
        "reports/source_evidence_closure.json",
        "reports/mechanic_drift_report.json",
        "reports/strong_promotion_report.json",
        "reports/output_ownership_manifest.json",
    ]

    manifest = build_output_ownership_manifest(generated_files)

    assert manifest["summary"]["generated_file_count"] == len(generated_files)
    assert manifest["summary"]["unclassified_file_count"] == 0
    gate_rows = [row for row in manifest["files"] if row["classification"] == "gate"]
    assert [row["file"] for row in gate_rows] == ["reports/operator_summary.json"]
    runtime_rows = {
        row["file"]: row for row in manifest["files"] if row["file"].startswith("CustomConfig/")
    }
    assert runtime_rows["CustomConfig/deck/GlobalValues.json"]["runtime_surface"] == "GlobalValues.json"
    assert runtime_rows["CustomConfig/deck/Mulligan.json"]["runtime_surface"] == "Mulligan.json"
    assert runtime_rows["CustomConfig/deck/SW_448.json"]["runtime_surface"] == "CARDID.json"
    assert runtime_rows["CustomConfig/deck/Combo.json"]["runtime_surface"] == "Combo.json"


def test_compiler_emits_only_canonical_report_owners(tmp_path: Path):
    from hsconfig.package_compiler import compile_package
    from tests.helpers.audited_package_request import audited_request

    compiled = compile_package(audited_request(tmp_path, "ShadowPriest"))
    report_paths = {
        projection.relative_path for projection in compiled.json_projections
    }

    assert report_paths.isdisjoint(REMOVED_REPORT_ALIASES)
    assert CANONICAL_REPORT_OWNERS <= report_paths


def test_removed_report_aliases_are_not_registered_or_in_active_docs():
    from hsconfig.visionai_registry import REPORT_REGISTRY

    assert set(REPORT_REGISTRY).isdisjoint(REMOVED_REPORT_ALIASES)
    stale_consumers = {
        str(path): sorted(
            alias
            for alias in REMOVED_REPORT_ALIASES
            if alias in path.read_text(encoding="utf-8")
        )
        for path in _active_python_consumers()
    }
    assert stale_consumers == {
        path: [] for path in stale_consumers
    }
    active_docs = _active_markdown_documents()
    stale_docs = {
        str(path): sorted(
            alias
            for alias in REMOVED_REPORT_ALIASES
            if alias.rsplit("/", 1)[-1] in path.read_text(encoding="utf-8")
        )
        for path in active_docs
    }
    assert stale_docs == {
        str(path): [] for path in active_docs
    }


def test_dead_architecture_modules_have_no_files_or_active_consumers():
    module_paths = {
        name: Path(f"src/hsconfig/{name}.py")
        for name in DEAD_ARCHITECTURE_MODULES
    }

    assert {
        name: path.exists() for name, path in module_paths.items()
    } == {name: False for name in DEAD_ARCHITECTURE_MODULES}
    stale_consumers = {
        str(path): sorted(
            module
            for module in DEAD_ARCHITECTURE_MODULES
            if module in path.read_text(encoding="utf-8")
        )
        for path in _active_python_consumers()
    }

    assert stale_consumers == {
        path: [] for path in stale_consumers
    }


def test_output_ownership_manifest_marks_unknown_report_unclassified():
    from hsconfig.output_ownership_manifest import build_output_ownership_manifest

    manifest = build_output_ownership_manifest(
        [
            "reports/operator_summary.json",
            "reports/new_unregistered_report.json",
            "reports/research/new_unregistered_report.json",
        ]
    )
    by_file = {row["file"]: row for row in manifest["files"]}

    assert by_file["reports/new_unregistered_report.json"]["classification"] == (
        "unclassified"
    )
    assert by_file["reports/research/new_unregistered_report.json"]["classification"] == (
        "unclassified"
    )
    assert manifest["summary"]["unclassified_file_count"] == 2


def test_output_ownership_manifest_classifies_runtime_surface_ledger_as_integrity():
    manifest = build_output_ownership_manifest(
        [
            "reports/operator_summary.json",
            "reports/runtime_surface_ledger.json",
        ]
    )
    by_file = {row["file"]: row for row in manifest["files"]}

    assert by_file["reports/runtime_surface_ledger.json"] == {
        "file": "reports/runtime_surface_ledger.json",
        "producer": "prepare",
        "classification": "integrity_receipt",
        "authority": "physical_runtime_surface_ledger",
        "can_block_apply": True,
        "runtime_surface": None,
        "diagnostic_only": False,
    }
    assert manifest["summary"]["unclassified_file_count"] == 0
    assert manifest["summary"]["gate_count"] == 1


def test_output_ownership_manifest_marks_legacy_surfaces_as_forbidden_drift():
    from hsconfig.output_ownership_manifest import build_output_ownership_manifest

    manifest = build_output_ownership_manifest(
        [
            "CustomConfig/deck/Presume.json",
            "CustomConfig/deck/Concede.json",
        ]
    )
    by_file = {row["file"]: row for row in manifest["files"]}

    for path in (
        "CustomConfig/deck/Presume.json",
        "CustomConfig/deck/Concede.json",
    ):
        assert by_file[path]["classification"] == "forbidden_legacy_surface"
        assert by_file[path]["runtime_surface"] == "legacy_non_normal_surface"
    assert manifest["summary"]["forbidden_legacy_surface_count"] == 2
    assert not any(
        row["classification"] == "runtime_surface" for row in manifest["files"]
    )


def test_package_renderer_calls_build_operator_summary_once_in_prepare_flow():
    source = inspect.getsource(
        package_render_authority.render_package_authority
    )

    assert source.count("build_operator_summary_from_inputs(") == 1


def test_prepared_package_keeps_operator_manifest_and_emitted_files_in_sync(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    reports = package / "reports"
    operator_summary = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (reports / "output_ownership_manifest.json").read_text(encoding="utf-8")
    )
    emitted_files = {
        str(path.relative_to(package)).replace("\\", "/")
        for path in package.rglob("*")
        if path.is_file()
    }
    predicted_files = {
        str(path).replace("\\", "/") for path in operator_summary["generated_files"]
    }
    manifest_files = {row["file"] for row in manifest["files"]}

    assert code == 0
    assert emitted_files.isdisjoint(REMOVED_REPORT_ALIASES)
    assert CANONICAL_REPORT_OWNERS <= emitted_files
    assert predicted_files == emitted_files
    assert manifest_files == emitted_files
    assert {
        "reports/operator_summary.json",
        "reports/strong_promotion_report.json",
        "reports/output_ownership_manifest.json",
    }.issubset(predicted_files)
    assert manifest["summary"]["generated_file_count"] == len(emitted_files)
    assert manifest["summary"]["unclassified_file_count"] == 0
    assert operator_summary["output_ownership_summary"] == {
        "non_blocking": True,
        "generated_file_count": len(emitted_files),
        "unclassified_file_count": 0,
        "gate_count": 1,
    }
