from __future__ import annotations

from argparse import Namespace
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.sync_installed_skill import sync_skill
from hsconfig.contract_preflight import (
    GitPreflight,
    _source_readiness_preview_visible,
    build_contract_preflight,
    build_git_preflight,
    build_package_contract_preflight,
)
from hsconfig.commands import contract_preflight as contract_preflight_command
from tests.helpers.current_apply_eligible_package import (
    write_current_apply_eligible_package,
)
from tests.helpers.current_globalvalues_contract import (
    write_current_globalvalues_contract,
)


def _clean_git() -> GitPreflight:
    return GitPreflight(
        branch="codex/test",
        upstream="origin/codex/test",
        dirty=False,
        ahead_origin_main=1,
        behind_origin_main=0,
        clean_for_runtime_work=True,
        ahead_upstream=0,
        behind_upstream=0,
    )


def _synced_install_root(tmp_path: Path) -> Path:
    install_root = tmp_path / "custom skill root"
    sync_skill(install_root)
    return install_root


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _contract_preflight_clean_package(tmp_path: Path) -> Path:
    package = tmp_path / "04_package"
    deck = package / "CustomConfig" / "shadowpriest"
    reports = package / "reports"
    _write_json(
        reports / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "runtime_load_safe": True,
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "source_status_diagnostic_only": True,
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
            "default_only_runtime_surface_details": [],
            "no_default_only_runtime_status": {
                "status": "clean",
                "default_only_runtime_surfaces": [],
            },
            "source_to_runtime_explainability_summary": {
                "non_blocking": True,
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "closure_lane_counts": {"source_backed_runtime_lowered": 1},
                "cards_with_closure": 1,
                "cards_missing_closure": 0,
                "closure_schema_current": True,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "surface_status_ledger": [
                {"surface": "cardid_behavior", "status": "emitted"},
                {"surface": "globalvalues", "status": "emitted"},
                {"surface": "mulligan", "status": "emitted"},
                {"surface": "combo", "status": "not_applicable"},
            ],
        },
    )
    _write_json(
        reports / "deck_identity.json",
        {
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "NX2_019", "name": "Mind Sear"}],
        },
    )
    _write_json(
        reports / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "NX2_019",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforeBattlecryTargetBonus",
                    "condition": "*",
                    "value": "10",
                    "meaningful_runtime_surface": True,
                    "semantic_score": {
                        "band": "high",
                        "reason": "conditional_target_kill_burn",
                        "profile": "semantic_intent",
                        "matched_signals": [
                            "enemy_hero_damage",
                            "death_condition",
                        ],
                    },
                }
            ]
        },
    )
    _write_json(
        reports / "source_to_runtime_explainability.json",
        {
            "default_only_runtime_surfaces": [],
            "summary": {
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "claim_rows": [
                {
                    "claim_id": "claim_mind_sear_effect",
                    "claim_kind": "targeting_rule",
                    "builder_or_router_decision": "emitted",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "first_missing_link": None,
                }
            ],
            "card_rows": [
                {
                    "card_id": "NX2_019",
                    "first_missing_link": None,
                    "source_lane": "runtime_lowered",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "runtime_surfaces": ["cardid"],
                    "closure": {
                        "lane": "source_backed_runtime_lowered",
                        "runtime_surfaces": ["NX2_019.json"],
                        "default_only_risk": False,
                    },
                    "evidence_chain": [
                        {
                            "claim_id": "claim_mind_sear_effect",
                            "claim_kind": "targeting_rule",
                            "source_lane": "runtime_lowered",
                            "source_type": "deck_matched_public_guide",
                            "runtime_files": ["NX2_019.json"],
                            "resolution_reason": "emitted",
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        reports / "surface_intent.json",
        {
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "runtime_write_performed": False,
            "surface_count": 3,
            "required_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "NX2_019.json",
            ],
            "optional_surfaces": [],
            "rich_optional_runtime_surfaces": ["NX2_019.json"],
            "rows": [
                {
                    "rule_id": "globalvalues_full_key_profile",
                    "card_id": None,
                    "surface": "GlobalValues.json",
                    "intent": "profile_and_overlay_full_global_values",
                    "intent_source": "contract",
                },
                {
                    "rule_id": "NX2_019_card_behavior",
                    "card_id": "NX2_019",
                    "surface": "NX2_019.json",
                    "surface_family": "CARDID.json",
                    "intent": "conditional_minion_death_burn",
                    "intent_source": "contract",
                },
            ],
        },
    )
    _write_json(
        deck / "NX2_019.json",
        {
            "GameCardId": "NX2_019",
            "ConfigComment": "ShadowPriest: generated behavior for NX2_019",
            "BeforeBattlecryTargetBonus": {
                "values": [
                    {
                        "comment": "ShadowPriest: Mind Sear source-backed target preference",
                        "condition": "*",
                        "value": "10",
                    }
                ]
            },
        },
    )
    _write_json(
        deck / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "ShadowPriest global values"},
    )
    write_current_globalvalues_contract(
        package,
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "ShadowPriest global values",
        },
    )
    _write_json(
        deck / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "ShadowPriest mulligan",
            "Mulligan": {"values": []},
        },
    )
    operator = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    return write_current_apply_eligible_package(
        package,
        operator_summary=operator,
        deck_directory="shadowpriest",
        deck_name="ShadowPriest",
        deck_code=(
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
            "KgG17oG1cEGAAA="
        ),
    )


def test_contract_preflight_import_path_does_not_require_research_sentinel() -> None:
    source = Path("src/hsconfig/contract_preflight.py").read_text(encoding="utf-8")
    top_level = source.split("def _latest_research_result_contract", 1)[0]

    assert "from hsconfig.research_result_contract_sentinel import" not in top_level
    assert "import yaml" not in top_level


def test_contract_preflight_reports_installed_skill_sync_when_clean(
    tmp_path: Path,
) -> None:
    install_root = _synced_install_root(tmp_path)

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=install_root,
    )

    assert payload["status"] == "PASS"
    assert payload["checks"]["installed_skill_sync_current"] is True
    assert "installed_skill_sync_current" not in payload["failures"]
    assert payload["installed_skill_sync"]["status"] == "in_sync"
    assert payload["installed_skill_sync"]["matches_repo_skill"] is True
    assert payload["installed_skill_sync"]["diagnostic_only"] is True
    assert (
        payload["installed_skill_sync"]["runtime_apply_authority"]
        == "reports/operator_summary.json"
    )


def test_contract_preflight_reports_attention_when_installed_skill_drifts(
    tmp_path: Path,
) -> None:
    install_root = _synced_install_root(tmp_path)
    installed_skill = install_root / "hsconfig" / "SKILL.md"
    installed_skill.write_text(
        installed_skill.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=install_root,
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["installed_skill_sync_current"] is False
    assert "installed_skill_sync_current" in payload["failures"]
    assert payload["installed_skill_sync"]["status"] == "attention"
    assert payload["installed_skill_sync"]["recommended_action"] == (
        'python scripts\\sync_installed_skill.py --install-root '
        f'"{install_root.resolve()}"'
    )
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False


def test_contract_preflight_passes_for_repo_contract_with_clean_git_snapshot(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["status"] == "PASS"
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False
    assert payload["diagnostic_only"] is True
    assert payload["failures"] == []
    assert payload["checks"]["repo_current"] is True
    assert payload["checks"]["checklist_listed_in_references"] is True
    assert payload["checks"]["no_default_only_visible"] is True
    assert payload["checks"]["source_status_nonblocking_visible"] is True
    assert payload["checks"]["runtime_surface_boundary_visible"] is True
    assert payload["checks"]["negative_scope_visible"] is True


def test_contract_preflight_exposes_skill_thin_router_contract(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["checks"]["skill_thin_router_visible"] is True
    assert "skill_thin_router_visible" not in payload["failures"]
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False


def test_contract_preflight_checks_configure_acceptance_route_contract(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["status"] == "PASS"
    assert payload["checks"]["configure_acceptance_route_visible"] is True
    assert payload["checks"]["configure_acceptance_projection_not_gate_visible"] is True
    assert payload["checks"]["config_quality_summary_diagnostic_only_visible"] is True
    assert payload["checks"]["config_proof_summary_visible"] is True
    assert "configure_acceptance_route_visible" not in payload["failures"]
    assert "configure_acceptance_projection_not_gate_visible" not in payload["failures"]
    assert "config_quality_summary_diagnostic_only_visible" not in payload["failures"]
    assert "config_proof_summary_visible" not in payload["failures"]


def test_contract_preflight_checks_source_candidate_plan_visibility(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    contract = payload["source_candidate_plan_contract"]

    assert payload["status"] == "PASS"
    assert payload["checks"]["source_candidate_plan_visible"] is True
    assert "source_candidate_plan_visible" not in payload["failures"]
    assert contract == {
        "status": "visible",
        "authority": "diagnostic_source_candidate_plan",
        "documentation_path": "docs/operator/source-builder-workflow.md",
        "operator_entrypoint_path": "docs/operator/README.md",
        "implementation_path": "src/hsconfig/source_candidate_plan.py",
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_path": (
            "source-manifest -> configure --online-source -> "
            "source-acquire/source-autopilot -> prepare"
        ),
        "notes": [
            "source_candidate_plan.json is acquisition guidance only.",
            "Candidate plans cannot promote or block runtime apply.",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }


def test_contract_preflight_reads_preview_from_configure_workflow_producer(
    tmp_path: Path,
) -> None:
    configure_command_text = (
        Path("src") / "hsconfig" / "commands" / "configure.py"
    ).read_text(encoding="utf-8")
    configure_workflow_text = (
        Path("src") / "hsconfig" / "configure_workflow.py"
    ).read_text(encoding="utf-8")
    producer_terms = (
        "build_source_readiness_preview",
        '"source_readiness_preview": source_readiness_preview',
    )

    assert all(term not in configure_command_text for term in producer_terms)
    assert all(term in configure_workflow_text for term in producer_terms)

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    contract = payload["source_readiness_preview_contract"]

    assert payload["status"] == "PASS"
    assert payload["checks"]["source_readiness_preview_visible"] is True
    assert "source_readiness_preview_visible" not in payload["failures"]
    assert contract == {
        "status": "visible",
        "authority": "diagnostic_source_readiness_preview",
        "documentation_paths": [
            "docs/operator/source-builder-workflow.md",
            ".agents/skills/hsconfig/references/workflow.md",
        ],
        "implementation_path": "src/hsconfig/source_readiness_preview.py",
        "configure_summary_field": "source_readiness_preview",
        "autopilot_report_field": "source_readiness_preview",
        "producer_paths": [
            "src/hsconfig/source_autopilot.py",
            "src/hsconfig/configure_workflow.py",
        ],
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "notes": [
            (
                "Source readiness preview summarizes candidate, autopilot, "
                "and operator source readiness."
            ),
            (
                "Source readiness preview cannot promote SOURCE_BACKED_STRONG, "
                "block apply, apply runtime files, or write runtime config."
            ),
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }


def test_contract_preflight_reports_attention_when_source_readiness_preview_drifts(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)

    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    source_root = tmp_path / "src" / "hsconfig"
    source_root.mkdir(parents=True)
    for filename in (
        "source_candidate_plan.py",
        "source_readiness_preview.py",
        "source_autopilot.py",
    ):
        shutil.copy2(
            Path("src") / "hsconfig" / filename,
            source_root / filename,
        )
    command_root = source_root / "commands"
    command_root.mkdir(parents=True)
    shutil.copy2(
        Path("src") / "hsconfig" / "commands" / "configure.py",
        command_root / "configure.py",
    )
    shutil.copy2(
        Path("src") / "hsconfig" / "configure_workflow.py",
        source_root / "configure_workflow.py",
    )

    workflow_path = target_docs / "operator" / "source-builder-workflow.md"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(
            "diagnostic-only",
            "diagnostic",
            1,
        ),
        encoding="utf-8",
    )
    preview_path = source_root / "source_readiness_preview.py"
    preview_path.write_text(
        preview_path.read_text(encoding="utf-8").replace(
            '"apply_blocking": False',
            '"apply_blocking": True',
            1,
        ),
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["source_readiness_preview_visible"] is False
    assert "source_readiness_preview_visible" in payload["failures"]
    assert payload["source_readiness_preview_contract"]["status"] == "attention"
    assert payload["source_readiness_preview_contract"]["runtime_apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert payload["source_readiness_preview_contract"][
        "source_status_apply_blocking"
    ] is False
    assert payload["source_status_apply_blocking"] is False
    assert payload["diagnostic_only"] is True


def test_source_readiness_preview_visibility_requires_default_only_status_fields() -> None:
    preview_text = (Path("src") / "hsconfig" / "source_readiness_preview.py").read_text(
        encoding="utf-8"
    )
    preview_without_status = preview_text.replace(
        '"default_only_runtime_surface_status": default_only_runtime_surface_status,',
        '"runtime_surface_status": default_only_runtime_surface_status,',
        1,
    )

    assert _source_readiness_preview_visible(
        preview_without_status,
        (Path("src") / "hsconfig" / "configure_workflow.py").read_text(
            encoding="utf-8"
        ),
        (Path("src") / "hsconfig" / "source_autopilot.py").read_text(
            encoding="utf-8"
        ),
        (Path("docs") / "operator" / "source-builder-workflow.md").read_text(
            encoding="utf-8"
        ),
        (Path(".agents") / "skills" / "hsconfig" / "references" / "workflow.md").read_text(
            encoding="utf-8"
        ),
    ) is False


def test_contract_preflight_reports_attention_when_source_candidate_plan_visibility_drifts(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)

    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    source_root = tmp_path / "src" / "hsconfig"
    source_root.mkdir(parents=True)
    shutil.copy2(
        Path("src") / "hsconfig" / "source_candidate_plan.py",
        source_root / "source_candidate_plan.py",
    )

    workflow_path = target_docs / "operator" / "source-builder-workflow.md"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(
            "The plan cannot promote, block apply, write runtime config, "
            "or replace `reports/operator_summary.json`.",
            "The plan can decide source status.",
        ),
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["source_candidate_plan_visible"] is False
    assert "source_candidate_plan_visible" in payload["failures"]
    assert payload["source_candidate_plan_contract"]["status"] == "attention"
    assert payload["source_candidate_plan_contract"]["runtime_apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert payload["source_candidate_plan_contract"]["source_status_apply_blocking"] is False
    assert payload["source_status_apply_blocking"] is False
    assert payload["diagnostic_only"] is True


def test_contract_preflight_checks_pre_run_config_contract_receipt_visibility(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["status"] == "PASS"
    assert payload["checks"]["pre_run_config_contract_receipt_visible"] is True
    assert "pre_run_config_contract_receipt_visible" not in payload["failures"]


def test_contract_preflight_reports_attention_when_git_is_dirty() -> None:
    dirty_git = GitPreflight(
        branch="codex/test",
        upstream="origin/codex/test",
        dirty=True,
        ahead_origin_main=1,
        behind_origin_main=0,
        clean_for_runtime_work=False,
        ahead_upstream=0,
        behind_upstream=0,
    )

    payload = build_contract_preflight(Path("."), git=dirty_git)

    assert payload["status"] == "ATTENTION"
    assert "repo_current" in payload["failures"]
    assert payload["source_status_apply_blocking"] is False
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"


def test_git_preflight_reports_attention_when_origin_main_is_unresolvable(
    tmp_path: Path,
) -> None:
    subprocess.run(
        ["git", "init", "-b", "feature"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    snapshot = build_git_preflight(tmp_path)
    payload = build_contract_preflight(tmp_path, git=snapshot)

    assert snapshot.ahead_origin_main == 0
    assert snapshot.behind_origin_main == 0
    assert snapshot.origin_main_error
    assert snapshot.clean_for_runtime_work is False
    assert payload["checks"]["repo_current"] is False
    assert payload["status"] == "ATTENTION"


def test_contract_preflight_cli_returns_json_attention_for_invalid_repo_root(
    tmp_path: Path,
) -> None:
    invalid_repo_root = tmp_path / "missing-repo"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hsconfig.cli",
            "contract-preflight",
            "--json",
            "--repo-root",
            str(invalid_repo_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    normal_payload = build_contract_preflight(Path("."), git=_clean_git())

    assert payload["status"] == "ATTENTION"
    assert payload["error"]
    assert payload["repo_root"] == str(invalid_repo_root.resolve())
    assert set(payload) - {"error"} == set(normal_payload)
    assert isinstance(payload["git"], dict)
    assert set(payload["git"]) == set(normal_payload["git"])
    assert isinstance(payload["checks"], dict)
    assert set(payload["checks"]) == set(normal_payload["checks"])
    assert isinstance(payload["research_context"], dict)
    assert set(payload["research_context"]) == set(normal_payload["research_context"])
    assert "Traceback" not in result.stderr


def test_contract_preflight_runtime_error_fallback_preserves_normal_payload_schema(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    normal_payload = build_contract_preflight(Path("."), git=_clean_git())

    def _raise_preflight(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("forced preflight failure")

    monkeypatch.setattr(
        contract_preflight_command,
        "build_contract_preflight",
        _raise_preflight,
    )

    code = contract_preflight_command.run_contract_preflight_command(
        Namespace(repo_root=".", skill_install_root=None, json=True)
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["source_candidate_plan_contract"] == {
        "status": "attention",
        "authority": "diagnostic_source_candidate_plan",
        "documentation_path": "docs/operator/source-builder-workflow.md",
        "operator_entrypoint_path": "docs/operator/README.md",
        "implementation_path": "src/hsconfig/source_candidate_plan.py",
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_path": (
            "source-manifest -> configure --online-source -> "
            "source-acquire/source-autopilot -> prepare"
        ),
        "notes": [
            "source candidate plan contract preflight unavailable",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }

    assert code == 1
    assert payload["source_readiness_preview_contract"][
        "configure_summary_field"
    ] == "source_readiness_preview"
    assert payload["source_readiness_preview_contract"][
        "autopilot_report_field"
    ] == "source_readiness_preview"
    assert payload["source_readiness_preview_contract"][
        "runtime_apply_authority"
    ] == "reports/operator_summary.json"
    assert payload["source_readiness_preview_contract"][
        "source_status_apply_blocking"
    ] is False
    assert {
        "research_context",
        "installed_skill_sync",
        "runtime_apply_authority",
        "source_status_apply_blocking",
        "diagnostic_only",
        "checks",
        "failures",
        "status",
        "git",
        "repo_root",
    } <= set(payload)
    assert set(payload) - {"error"} == set(normal_payload)
    assert set(payload["research_context"]) == set(normal_payload["research_context"])
    assert payload["error"]["type"] == "RuntimeError"
    assert payload["error"]["message"] == "forced preflight failure"


def test_contract_preflight_cli_emits_json_without_writing_files(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    result = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "contract-preflight", "--repo-root", ".", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    after = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    assert result.returncode in (0, 1)
    payload = json.loads(result.stdout)
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert before == after


def test_contract_preflight_cli_reports_installed_skill_sync_without_writes(
    tmp_path: Path,
) -> None:
    install_root = _synced_install_root(tmp_path)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hsconfig.cli",
            "contract-preflight",
            "--repo-root",
            ".",
            "--skill-install-root",
            str(install_root),
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    after = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    payload = json.loads(result.stdout)

    assert result.returncode in (0, 1)
    assert payload["checks"]["installed_skill_sync_current"] is True
    assert payload["installed_skill_sync"]["matches_repo_skill"] is True
    assert payload["installed_skill_sync"]["diagnostic_only"] is True
    assert before == after


def test_unavailable_installed_skill_payload_expands_tilde_install_root_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_root = "~/.codex/custom-skills"

    def _raise_sync_error(repo_root: str, passed_install_root: object) -> dict[str, object]:
        raise RuntimeError(f"boom: {repo_root} / {passed_install_root}")

    monkeypatch.setattr(
        contract_preflight_command,
        "build_installed_skill_sync_status",
        _raise_sync_error,
    )

    payload = contract_preflight_command._unavailable_installed_skill_payload(
        ".",
        install_root,
    )

    assert payload["installed_skill_path"] == str(
        Path(install_root).expanduser() / "hsconfig"
    )
    assert payload["recommended_action"] == (
        'python scripts\\sync_installed_skill.py --install-root '
        f'"{Path(install_root).expanduser().resolve()}"'
    )


def test_unavailable_installed_skill_payload_uses_default_root_for_empty_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_sync_error(repo_root: str, passed_install_root: object) -> dict[str, object]:
        raise RuntimeError(f"boom: {repo_root} / {passed_install_root}")

    monkeypatch.setattr(
        contract_preflight_command,
        "build_installed_skill_sync_status",
        _raise_sync_error,
    )

    payload = contract_preflight_command._unavailable_installed_skill_payload(
        ".",
        "",
    )

    assert payload["installed_skill_path"] == str(
        contract_preflight_command.DEFAULT_INSTALL_ROOT / "hsconfig"
    )
    assert payload["recommended_action"] == "python scripts\\sync_installed_skill.py"


def test_contract_preflight_is_registered_but_not_part_of_configure_path() -> None:
    parser_help = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert parser_help.returncode == 0
    assert "contract-preflight" in parser_help.stdout

    contract_preflight_help = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "contract-preflight", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert contract_preflight_help.returncode == 0
    assert "--package" in contract_preflight_help.stdout

    configure_help = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "configure", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert configure_help.returncode == 0
    assert "contract-preflight" not in configure_help.stdout


def test_contract_preflight_reports_research_context_as_diagnostic_only() -> None:
    payload = build_contract_preflight(Path("."), git=_clean_git())

    research_context = payload["research_context"]

    assert payload["checks"]["research_current_truth_index_visible"] is True
    assert payload["checks"]["historical_research_outlines_diagnostic_only"] is True
    assert research_context["status"] == "current"
    assert research_context["active_evidence_index_present"] is True
    assert research_context["active_evidence_index_path"] == "docs/research/current-truth.md"
    assert research_context["machine_evidence_index_path"] == "docs/research/current-truth-index.json"
    assert research_context["authority"] == "evidence_index_only"
    assert research_context["operator_gate_impact"] == "diagnostic_only"
    assert research_context["normal_apply_authority"] == "reports/operator_summary.json"
    assert research_context["historical_outlines_apply_authority"] is False
    assert research_context["recommended_research_entrypoint"] == "docs/research/current-truth.md"
    assert research_context["historical_outline_count"] > 0
    assert "docs/research/current-truth.md" not in research_context["historical_outline_paths"]


def test_contract_preflight_package_mode_aggregates_runtime_and_quality(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "PASS"
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False
    assert payload["checks"]["package_contract_current"] is True
    assert "package_contract_current" not in payload["failures"]
    assert "package_contract" in payload

    contract = payload["package_contract"]

    assert contract["status"] == "clean"
    assert contract["package_contract_current"] is True
    assert contract["authority"] == "diagnostic_only"
    assert contract["runtime_write_performed"] is False
    assert contract["apply_blocking"] is False
    assert contract["runtime_apply_authority"] == "reports/operator_summary.json"
    assert contract["ready_to_use_from_operator_summary"] is True
    assert contract["technical_status"] == "VALID_PACKAGE"
    assert contract["runtime_apply_mode"] == "load_safe_apply"
    assert contract["runtime_apply_allowed"] is True
    assert contract["load_safe_to_install"] is True
    assert contract["use_config_now"] is True
    assert contract["use_config_now_scope"] == "load_safety_only"
    assert contract["semantic_handoff_status"] == "closed"
    assert contract["semantic_handoff_reasons"] == []
    assert contract["source_status_apply_blocking"] is False
    assert contract["observed_operator_source_status_apply_blocking"] is False
    assert contract["default_only_runtime_surfaces"] == []
    assert contract["validate_config_package_status"] == "passed"
    assert contract["config_quality_status"] == "clean"
    assert contract["config_quality_problem_count"] == 0
    assert contract["config_intent_self_audit_status"] == "clean"
    assert contract["surface_intent_status"] == "clean"
    assert contract["surface_intent_present"] is True
    assert contract["surface_intent_surface_count"] == 3
    assert contract["surface_intent_fallback_intent_rows"] == 0
    assert contract["surface_intent_legacy_policy_surface_rows"] == []
    assert contract["surface_intent_first_attention"] is None
    assert contract["closure_schema_current"] is True
    assert contract["cards_missing_closure"] == 0
    assert contract["next_report_to_open"] == "reports/operator_summary.json"


def test_contract_preflight_semantic_attention_does_not_change_apply_authority(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    card_behavior_path = package / "reports" / "card_behavior_plan_report.json"
    card_behavior = json.loads(card_behavior_path.read_text(encoding="utf-8"))
    card_behavior["rows"] = []
    _write_json(card_behavior_path, card_behavior)

    contract = build_package_contract_preflight(package)

    assert contract["load_safe_to_install"] is True
    assert contract["use_config_now"] is True
    assert contract["semantic_handoff_status"] == "attention"
    assert "unreported_runtime_rows" in contract["semantic_handoff_reasons"]
    assert contract["runtime_apply_allowed"] is True
    assert contract["runtime_apply_authority"] == "reports/operator_summary.json"


def test_contract_preflight_projects_explicit_semantic_suppression_without_gate(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    card_behavior_path = package / "reports" / "card_behavior_plan_report.json"
    card_behavior = json.loads(card_behavior_path.read_text(encoding="utf-8"))
    card_behavior["suppressed"] = [
        {
            "claim_id": "claim_patches_trigger",
            "claim_kind": "mechanic_usage",
            "cards": ["CFM_637"],
            "reason": "semantic_surface_not_expressible",
        }
    ]
    _write_json(card_behavior_path, card_behavior)

    contract = build_package_contract_preflight(package)

    assert contract["load_safe_to_install"] is True
    assert contract["use_config_now"] is True
    assert contract["semantic_handoff_status"] == "attention"
    assert contract["semantic_handoff_reasons"] == [
        "semantic_surface_not_expressible"
    ]
    assert contract["runtime_apply_allowed"] is True
    assert contract["apply_blocking"] is False


def test_contract_preflight_quality_exception_is_insufficient_without_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)

    def raise_quality(_package: Path) -> dict[str, object]:
        raise RuntimeError("quality unavailable")

    monkeypatch.setattr(
        "hsconfig.config_quality_contract.build_config_quality_report",
        raise_quality,
    )

    contract = build_package_contract_preflight(package)

    assert contract["load_safe_to_install"] is True
    assert contract["use_config_now"] is True
    assert contract["semantic_handoff_status"] == "insufficient_evidence"
    assert contract["semantic_handoff_reasons"] == ["config_quality_exception"]
    assert contract["runtime_apply_allowed"] is True
    assert contract["apply_blocking"] is False


def test_contract_preflight_package_mode_surfaces_attention_surface_intent_without_gate(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    surface_intent_path = package / "reports" / "surface_intent.json"
    surface_intent = json.loads(surface_intent_path.read_text(encoding="utf-8"))
    surface_intent["rows"].append(
        {
            "card_id": "GENERIC_001",
            "surface": "GENERIC_001.json",
            "intent": "aggressive_card_behavior",
            "intent_source": "fallback",
        }
    )
    surface_intent["rows"].append(
        {
            "card_id": "Presume",
            "surface": "Presume.json",
            "intent": "legacy_policy",
            "intent_source": "contract",
        }
    )
    _write_json(surface_intent_path, surface_intent)

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "PASS"
    assert payload["checks"]["package_contract_current"] is True
    contract = payload["package_contract"]
    assert contract["package_contract_current"] is True
    assert contract["surface_intent_status"] == "attention"
    assert contract["surface_intent_present"] is True
    assert contract["surface_intent_surface_count"] == 3
    assert contract["surface_intent_fallback_intent_rows"] == 1
    assert contract["surface_intent_legacy_policy_surface_rows"] == ["Presume.json"]
    assert contract["surface_intent_first_attention"] == "surface_intent_fallback_visible"
    assert all("surface_intent" not in failure for failure in contract["failures"])


def test_contract_preflight_package_mode_surfaces_missing_surface_intent_without_gate(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    (package / "reports" / "surface_intent.json").unlink()

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "PASS"
    assert payload["checks"]["package_contract_current"] is True
    contract = payload["package_contract"]
    assert contract["package_contract_current"] is True
    assert contract["surface_intent_status"] == "missing"
    assert contract["surface_intent_present"] is False
    assert contract["surface_intent_surface_count"] == 0
    assert contract["surface_intent_fallback_intent_rows"] == 0
    assert contract["surface_intent_legacy_policy_surface_rows"] == []
    assert contract["surface_intent_first_attention"] is None
    assert all("surface_intent" not in failure for failure in contract["failures"])


def test_contract_preflight_omits_package_contract_without_package(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert "package_contract" not in payload
    assert "package_contract_current" not in payload["checks"]
    assert "package_contract_current" not in payload["failures"]


def test_contract_preflight_package_mode_requires_boolean_runtime_apply_allowed(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    operator_path = package / "reports" / "operator_summary.json"
    operator = json.loads(operator_path.read_text(encoding="utf-8"))
    operator["runtime_apply_allowed"] = "false"
    _write_json(operator_path, operator)

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["package_contract_current"] is False
    assert "package_contract_current" in payload["failures"]

    contract = payload["package_contract"]

    assert contract["status"] == "attention"
    assert contract["runtime_apply_allowed"] is False
    assert contract["ready_to_use_from_operator_summary"] is False
    assert contract["package_contract_current"] is False
    assert "runtime_apply_allowed_not_true" in contract["failures"]
    assert contract["source_status_apply_blocking"] is False


def test_contract_preflight_package_mode_exposes_default_only_attention_without_blocking(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    operator_path = package / "reports" / "operator_summary.json"
    operator = json.loads(operator_path.read_text(encoding="utf-8"))
    operator["semantic_status"] = "VALID_BUT_NOT_GUIDE_STRONG"
    operator["default_only_runtime_surfaces"] = ["Mulligan.json"]
    operator["no_default_only_runtime_status"] = {
        "status": "attention",
        "default_only_runtime_surfaces": ["Mulligan.json"],
    }
    operator_path.write_text(json.dumps(operator, indent=2), encoding="utf-8")

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "ATTENTION"
    assert payload["source_status_apply_blocking"] is False
    assert payload["checks"]["package_contract_current"] is False
    assert "package_contract_current" in payload["failures"]

    contract = payload["package_contract"]

    assert contract["status"] == "attention"
    assert contract["package_contract_current"] is False
    assert contract["authority"] == "diagnostic_only"
    assert contract["apply_blocking"] is False
    assert contract["runtime_write_performed"] is False
    assert contract["source_status_apply_blocking"] is False
    assert contract["observed_operator_source_status_apply_blocking"] is False
    assert contract["runtime_apply_allowed"] is True
    assert contract["ready_to_use_from_operator_summary"] is True
    assert contract["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert "default_only_runtime_surfaces_present" in contract["failures"]
    assert contract["next_report_to_open"] == "reports/contract_doctor.json"


def test_contract_preflight_package_mode_exposes_malformed_runtime_json_attention(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    (package / "CustomConfig" / "shadowpriest" / "Mulligan.json").write_text(
        "{not json",
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "ATTENTION"
    assert payload["source_status_apply_blocking"] is False
    assert payload["checks"]["package_contract_current"] is False

    contract = payload["package_contract"]

    assert contract["status"] == "attention"
    assert contract["validate_config_package_status"] == "failed"
    assert contract["apply_blocking"] is False
    assert contract["runtime_write_performed"] is False
    assert contract["source_status_apply_blocking"] is False
    assert "validate_config_package_failed" in contract["failures"]


def test_contract_preflight_package_mode_requires_complete_runtime_files(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    (package / "CustomConfig" / "shadowpriest" / "Mulligan.json").unlink()

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["package_contract_current"] is False

    contract = payload["package_contract"]

    assert contract["status"] == "attention"
    assert contract["validate_config_package_status"] == "failed"
    assert any(
        "missing required runtime file Mulligan.json" in error
        for error in contract["validate_config_package_errors"]
    )
    assert "validate_config_package_failed" in contract["failures"]
    assert contract["source_status_apply_blocking"] is False


def test_contract_preflight_uses_neutral_strict_validation_exception_text(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    (package / "reports" / "globalvalues_baseline.json").unlink()

    contract = build_package_contract_preflight(package)

    assert contract is not None
    assert contract["validation_status"] == "failed"
    assert contract["validation_errors"][0].startswith(
        "strict package validation raised ValueError:"
    )
    assert contract["package_contract_current"] is False
    assert contract["authority"] == "diagnostic_only"
    assert contract["apply_blocking"] is False
    assert contract["runtime_write_performed"] is False


def test_contract_preflight_package_mode_malformed_operator_summary_is_attention(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    (package / "reports" / "operator_summary.json").write_text(
        "{not json",
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["package_contract_current"] is False

    contract = payload["package_contract"]

    assert contract["status"] == "attention"
    assert contract["ready_to_use_from_operator_summary"] is False
    assert "operator_summary.json is missing or invalid." in contract["notes"]
    assert "config_quality_attention" in contract["failures"]
    assert contract["source_status_apply_blocking"] is False


def test_contract_preflight_research_context_attention_when_current_truth_missing(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)
    shutil.rmtree(target_docs / "research")
    (target_docs / "research").mkdir(parents=True)
    (target_docs / "research" / "historical-audit").mkdir()
    (target_docs / "research" / "historical-audit" / "outline.yaml").write_text(
        "items: []\n",
        encoding="utf-8",
    )

    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    payload = build_contract_preflight(tmp_path, git=_clean_git())
    research_context = payload["research_context"]

    assert payload["status"] == "ATTENTION"
    assert "research_current_truth_index_visible" in payload["failures"]
    assert payload["checks"]["research_current_truth_index_visible"] is False
    assert payload["checks"]["historical_research_outlines_diagnostic_only"] is True
    assert research_context["status"] == "attention"
    assert research_context["active_evidence_index_present"] is False
    assert research_context["historical_outline_count"] == 1
    assert research_context["historical_outlines_apply_authority"] is False
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False


def test_contract_preflight_reports_attention_when_configure_acceptance_route_drifts(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    operator_root = tmp_path / "docs" / "operator"
    operator_root.mkdir(parents=True)
    shutil.copy2(Path("docs") / "operator" / "README.md", operator_root / "README.md")

    research_root = tmp_path / "docs" / "research"
    research_root.mkdir(parents=True)
    for filename in ("current-truth.md", "current-truth-index.json"):
        shutil.copy2(Path("docs") / "research" / filename, research_root / filename)

    for path in (
        skill_root / "SKILL.md",
        skill_root / "references" / "workflow.md",
        operator_root / "README.md",
    ):
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "<out>/configure_summary.json.acceptance_summary",
            "<out>/configure_summary.json",
        )
        text = text.replace("use_config_now", "use_now")
        text = text.replace("next_report_to_open", "next_report")
        text = text.replace("operator projection", "operator overview")
        text = text.replace("diagnostic-only", "diagnostic")
        path.write_text(text, encoding="utf-8")

    payload = build_contract_preflight(tmp_path, git=_clean_git())

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["configure_acceptance_route_visible"] is False
    assert payload["checks"]["configure_acceptance_projection_not_gate_visible"] is False
    assert payload["checks"]["config_quality_summary_diagnostic_only_visible"] is False
    assert payload["checks"]["config_proof_summary_visible"] is False
    assert "configure_acceptance_route_visible" in payload["failures"]
    assert "configure_acceptance_projection_not_gate_visible" in payload["failures"]
    assert "config_quality_summary_diagnostic_only_visible" in payload["failures"]
    assert "config_proof_summary_visible" in payload["failures"]
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False
    assert payload["diagnostic_only"] is True


def test_contract_preflight_cli_includes_research_context_without_writing_files() -> None:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hsconfig.cli",
            "contract-preflight",
            "--repo-root",
            ".",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    after = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    payload = json.loads(result.stdout)

    assert result.returncode in (0, 1)
    assert "research_context" in payload
    assert payload["research_context"]["operator_gate_impact"] == "diagnostic_only"
    assert payload["research_context"]["normal_apply_authority"] == "reports/operator_summary.json"
    assert payload["research_context"]["historical_outlines_apply_authority"] is False
    assert payload["diagnostic_only"] is True
    assert before == after


def test_contract_preflight_cli_package_mode_does_not_write_files(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before_git = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    before_package = sorted(path.relative_to(package).as_posix() for path in package.rglob("*"))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hsconfig.cli",
            "contract-preflight",
            "--repo-root",
            ".",
            "--package",
            str(package),
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    after_git = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    after_package = sorted(path.relative_to(package).as_posix() for path in package.rglob("*"))

    assert before_git == after_git
    assert before_package == after_package
    assert result.returncode in (0, 1), result.stderr
    payload = json.loads(result.stdout)
    assert payload["package_contract"]["runtime_write_performed"] is False
    assert payload["package_contract"]["authority"] == "diagnostic_only"


def test_contract_preflight_cli_package_fallback_preserves_package_contract_schema(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    package = tmp_path / "missing_04_package"
    schema_keys = set(build_package_contract_preflight(package))

    def _raise_preflight(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("forced preflight failure")

    monkeypatch.setattr(
        contract_preflight_command,
        "build_contract_preflight",
        _raise_preflight,
    )

    exit_code = contract_preflight_command.run_contract_preflight_command(
        Namespace(
            repo_root=".",
            skill_install_root=None,
            package=str(package),
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "ATTENTION"
    assert payload["source_status_apply_blocking"] is False
    assert payload["checks"]["package_contract_current"] is False
    assert "package_contract_current" in payload["failures"]
    assert set(payload["package_contract"]) == schema_keys
    fallback_contract = payload["package_contract"]
    assert set(fallback_contract) == schema_keys
    assert fallback_contract["surface_intent_status"] == "attention"
    assert fallback_contract["surface_intent_present"] is False
    assert fallback_contract["surface_intent_surface_count"] == 0
    assert fallback_contract["surface_intent_fallback_intent_rows"] == 0
    assert fallback_contract["surface_intent_legacy_policy_surface_rows"] == []
    assert fallback_contract["surface_intent_first_attention"] == (
        "contract_preflight_exception"
    )
    assert payload["package_contract"]["status"] == "attention"
    assert payload["package_contract"]["package"] == str(package)
    assert payload["package_contract"]["package_contract_current"] is False
    assert payload["package_contract"]["failures"] == ["contract_preflight_exception"]


def test_contract_preflight_exposes_research_result_contract_sentinel() -> None:
    payload = build_contract_preflight(Path("."), git=_clean_git())
    research_context = payload["research_context"]

    assert payload["checks"]["research_result_contract_sentinel_visible"] is True
    assert research_context["latest_research_result_contract_status"] in {
        "clean",
        "attention",
        "not_found",
    }
    assert research_context["latest_research_result_contract_path"].startswith(
        "docs/research/"
    )
    assert isinstance(
        research_context["latest_research_result_contract_result_count"],
        int,
    )
    assert isinstance(
        research_context["latest_research_result_contract_invalid_count"],
        int,
    )
    assert research_context["source_status_apply_blocking"] is False
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"


def test_contract_preflight_exposes_research_freshness_missing_count() -> None:
    payload = build_contract_preflight(".")
    context = payload["research_context"]

    assert "latest_research_result_contract_freshness_missing_count" in context
    assert isinstance(
        context["latest_research_result_contract_freshness_missing_count"], int
    )
    assert context["source_status_apply_blocking"] is False
    assert payload["source_status_apply_blocking"] is False


def test_contract_preflight_projects_research_contract_first_non_promoting_result(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)
    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    latest = target_docs / "research" / "9999-bridge-research"
    (latest / "results").mkdir(parents=True)
    shutil.copy2(
        Path("docs")
        / "research"
        / "2026-07-17-hsconfig-source-contract-acceptance-loop"
        / "fields.yaml",
        latest / "fields.yaml",
    )
    (latest / "results" / "PirateDH.json").write_text(
        json.dumps(
            {
                "deck_name": "PirateDH",
                "archetype": "Wild Pirate Demon Hunter",
                "current_deck_sources": [],
                "guide_sources": [],
                "source_strength": "unfetched_acquisition_seed",
                "lowerable_claim_kinds": [],
                "non_promoting_support": [],
                "first_missing_source_action": (
                    "fetch_and_normalize_candidate_full_text_claims"
                ),
                "notes": "Seed row still needs full-text claims.",
            }
        ),
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )
    research_context = payload["research_context"]

    assert payload["checks"]["research_result_contract_sentinel_visible"] is True
    assert research_context["latest_research_result_contract_status"] == "clean"
    assert research_context["latest_research_result_contract_result_count"] == 1
    assert research_context["latest_research_result_contract_invalid_count"] == 0
    assert research_context["latest_research_result_contract_strict_invalid_count"] == 0
    assert research_context["latest_research_result_contract_contract_invalid_count"] == 0
    assert research_context["latest_research_result_contract_seed_only_count"] == 1
    assert research_context["latest_research_result_contract_strong_promoting_count"] == 0
    assert (
        research_context[
            "latest_research_result_contract_promotion_ready_deck_count"
        ]
        == 0
    )
    assert research_context["latest_research_result_contract_non_promoting_count"] == 1
    assert (
        research_context[
            "latest_research_result_contract_first_non_promoting_result"
        ]
        == "PirateDH"
    )
    assert (
        research_context[
            "latest_research_result_contract_first_non_promoting_action"
        ]
        == "fetch_and_normalize_candidate_full_text_claims"
    )
    assert (
        research_context[
            "latest_research_result_contract_first_non_promoting_reason"
        ]
        == "seed_only"
    )
    assert research_context["source_status_apply_blocking"] is False


def test_contract_preflight_research_result_attention_is_not_apply_blocking(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)
    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    latest = target_docs / "research" / "9999-invalid-research"
    (latest / "results").mkdir(parents=True)
    (latest / "fields.yaml").write_text("fields: []\n", encoding="utf-8")
    (latest / "results" / "ShadowPriest.json").write_text(
        json.dumps(
            {
                "deck_name": "ShadowPriest",
                "source_strength": "SOURCE_BACKED_STRONG",
                "first_missing_source_action": "none",
            }
        ),
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    research_context = payload["research_context"]
    assert payload["checks"]["research_result_contract_sentinel_visible"] is True
    assert research_context["latest_research_result_contract_status"] == "attention"
    assert (
        research_context["latest_research_result_contract_no_op_validation_risk"]
        is True
    )
    assert research_context["source_status_apply_blocking"] is False
    assert payload["source_status_apply_blocking"] is False
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"


def test_contract_preflight_latest_research_batch_is_deterministic_and_incomplete(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)
    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    latest = target_docs / "research" / "9999-incomplete-research"
    latest.mkdir(parents=True)

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    research_context = payload["research_context"]
    assert payload["checks"]["research_result_contract_sentinel_visible"] is True
    assert (
        research_context["latest_research_result_contract_path"]
        == "docs/research/9999-incomplete-research"
    )
    assert research_context["latest_research_result_contract_status"] == "attention"
    assert (
        research_context["latest_research_result_contract_no_op_validation_risk"]
        is True
    )
    assert research_context["source_status_apply_blocking"] is False
    assert payload["source_status_apply_blocking"] is False
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"


def test_contract_preflight_malformed_research_result_is_attention_not_crash(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)
    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    latest = target_docs / "research" / "9999-malformed-research"
    (latest / "results").mkdir(parents=True)
    (latest / "fields.yaml").write_text("fields: []\n", encoding="utf-8")
    (latest / "results" / "ShadowPriest.json").write_text(
        "{not json",
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    research_context = payload["research_context"]
    assert payload["checks"]["research_result_contract_sentinel_visible"] is True
    assert research_context["latest_research_result_contract_status"] == "attention"
    assert (
        research_context["latest_research_result_contract_no_op_validation_risk"]
        is True
    )
    assert research_context["source_status_apply_blocking"] is False
    assert payload["source_status_apply_blocking"] is False
