from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess

from hsconfig.skill_sync_status import build_installed_skill_sync_status


REQUIRED_REFERENCE_FILES = (
    "references/workflow.md",
    "references/visionai-surfaces.md",
    "references/guide-research-policy.md",
    "references/globalvalues-policy.md",
    "references/card-behavior-policy.md",
    "references/contract-compiler-checklist.md",
)

EXPECTED_CHECK_KEYS = (
    "repo_current",
    "skill_root_present",
    "installed_skill_sync_current",
    "reference_files_present",
    "checklist_referenced_by_normal_workflow",
    "checklist_listed_in_references",
    "configure_acceptance_route_visible",
    "configure_acceptance_projection_not_gate_visible",
    "config_quality_summary_diagnostic_only_visible",
    "config_proof_summary_visible",
    "operator_summary_single_authority_visible",
    "source_status_nonblocking_visible",
    "no_default_only_visible",
    "runtime_surface_boundary_visible",
    "darkbishop_effect_not_mulligan_visible",
    "negative_scope_visible",
    "diagnostic_only_visible",
    "research_current_truth_index_visible",
    "historical_research_outlines_diagnostic_only",
)


@dataclass(frozen=True)
class GitPreflight:
    branch: str
    upstream: str | None
    dirty: bool
    ahead_origin_main: int
    behind_origin_main: int
    clean_for_runtime_work: bool
    ahead_upstream: int | None = None
    behind_upstream: int | None = None
    origin_main_error: str | None = None


@dataclass(frozen=True)
class ResearchContextPreflight:
    status: str
    active_evidence_index_present: bool
    active_evidence_index_path: str
    machine_evidence_index_present: bool
    machine_evidence_index_path: str
    authority: str
    operator_gate_impact: str
    normal_apply_authority: str
    recommended_research_entrypoint: str
    historical_outline_count: int
    historical_outline_paths: tuple[str, ...]
    historical_outlines_apply_authority: bool
    source_status_apply_blocking: bool
    notes: tuple[str, ...]


def _run_git(
    repo_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _parse_counts(text: str) -> tuple[int, int]:
    parts = text.replace("\t", " ").split()
    if len(parts) < 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def _parse_status(text: str) -> tuple[str, bool]:
    lines = [line for line in text.splitlines() if line.strip()]
    branch_line = lines[0] if lines else "## unknown"
    branch = branch_line.removeprefix("## ").split("...")[0].strip()
    dirty = any(not line.startswith("## ") for line in lines)
    return branch, dirty


def build_git_preflight(repo_root: str | Path) -> GitPreflight:
    root = Path(repo_root)
    if not root.exists():
        return GitPreflight(
            branch="unknown",
            upstream=None,
            dirty=False,
            ahead_origin_main=0,
            behind_origin_main=0,
            clean_for_runtime_work=False,
            ahead_upstream=None,
            behind_upstream=None,
            origin_main_error=f"repo root does not exist: {root.resolve()}",
        )

    status_result = _run_git(root, "status", "--short", "--branch", check=False)
    if status_result.returncode != 0:
        error = (
            status_result.stderr.strip()
            or status_result.stdout.strip()
            or f"git status exited with status {status_result.returncode}"
        )
        return GitPreflight(
            branch="unknown",
            upstream=None,
            dirty=False,
            ahead_origin_main=0,
            behind_origin_main=0,
            clean_for_runtime_work=False,
            ahead_upstream=None,
            behind_upstream=None,
            origin_main_error=error,
        )

    status = status_result.stdout
    branch, dirty = _parse_status(status)

    upstream_result = _run_git(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
        check=False,
    )
    upstream = upstream_result.stdout.strip() or None

    origin_main_result = _run_git(
        root,
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main",
        check=False,
    )
    origin_main_error: str | None = None
    if origin_main_result.returncode == 0:
        try:
            ahead_origin_main, behind_origin_main = _parse_counts(
                origin_main_result.stdout
            )
        except ValueError as exc:
            ahead_origin_main, behind_origin_main = 0, 0
            origin_main_error = f"invalid origin/main count output: {exc}"
    else:
        ahead_origin_main, behind_origin_main = 0, 0
        origin_main_error = (
            origin_main_result.stderr.strip()
            or origin_main_result.stdout.strip()
            or f"git rev-list exited with status {origin_main_result.returncode}"
        )

    ahead_upstream: int | None = None
    behind_upstream: int | None = None
    if upstream:
        upstream_result = _run_git(
            root,
            "rev-list",
            "--left-right",
            "--count",
            f"HEAD...{upstream}",
            check=False,
        )
        ahead_upstream, behind_upstream = _parse_counts(upstream_result.stdout)

    return GitPreflight(
        branch=branch,
        upstream=upstream,
        dirty=dirty,
        ahead_origin_main=ahead_origin_main,
        behind_origin_main=behind_origin_main,
        clean_for_runtime_work=(
            not dirty and origin_main_error is None and behind_origin_main == 0
        ),
        ahead_upstream=ahead_upstream,
        behind_upstream=behind_upstream,
        origin_main_error=origin_main_error,
    )


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _references_line(skill_text: str) -> str:
    for line in skill_text.splitlines():
        if line.startswith("## References:"):
            return line
    return ""


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _configure_acceptance_route_visible(combined: str) -> bool:
    return all(
        term in combined
        for term in (
            "<out>/configure_summary.json.acceptance_summary",
            "acceptance_summary",
            "use_config_now",
            "technical_status",
            "runtime_apply_allowed",
            "source_strength",
            "default_only_clean",
            "next_report_to_open",
            "<out>/configure_summary.json.config_quality_summary",
            "config_quality_summary",
            "reports/operator_summary.json",
        )
    )


def _configure_acceptance_projection_not_gate_visible(combined: str) -> bool:
    return (
        "operator projection" in combined
        and _has_any(
            combined,
            (
                "does not replace `reports/operator_summary.json` as apply authority",
                "does not replace `reports/operator_summary.json`",
                "does not replace `operator_summary.json`",
            ),
        )
        and _has_any(
            combined,
            (
                "operator_summary.json remains the only normal apply authority",
                "operator_summary.json` remains the only normal apply authority",
                "operator_summary.json` remains the normal apply authority",
                "reports/operator_summary.json` as the apply authority",
            ),
        )
    )


def _config_quality_summary_diagnostic_only_visible(combined: str) -> bool:
    return (
        "<out>/configure_summary.json.config_quality_summary" in combined
        and "config_quality_summary" in combined
        and "diagnostic-only" in combined
        and "non-blocking" in combined
        and "contract-doctor" in combined
        and _has_any(
            combined,
            (
                "operator_summary.json remains the only normal apply authority",
                "operator_summary.json` remains the only normal apply authority",
                "operator_summary.json` remains the normal apply authority",
            ),
        )
    )


def _config_proof_summary_visible(combined: str) -> bool:
    return (
        "config_proof_summary" in combined
        and "diagnostic-only config proof" in combined
        and "not another apply gate" in combined
    )


def build_research_context_preflight(repo_root: str | Path) -> ResearchContextPreflight:
    root = Path(repo_root).resolve()
    current_truth_path = root / "docs" / "research" / "current-truth.md"
    current_truth_index_path = root / "docs" / "research" / "current-truth-index.json"
    current_truth_text = _read(current_truth_path)
    index_text = _read(current_truth_index_path)
    index_payload: dict[str, object] = {}
    if index_text:
        try:
            parsed = json.loads(index_text)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            index_payload = parsed

    research_root = root / "docs" / "research"
    historical_outline_paths: tuple[str, ...] = ()
    if research_root.exists():
        historical_outline_paths = tuple(
            sorted(
                _relative_posix(root, path)
                for path in research_root.glob("*/outline.yaml")
                if path.is_file()
            )
        )

    active_evidence_index_present = (
        current_truth_path.exists()
        and current_truth_index_path.exists()
        and "# HSConfig Current Truth Index" in current_truth_text
        and "Research artifacts are evidence, not operator instructions."
        in current_truth_text
    )
    machine_evidence_index_present = (
        current_truth_index_path.exists()
        and index_payload.get("authority") == "evidence_index_only"
        and index_payload.get("operator_gate_impact") == "diagnostic_only"
        and index_payload.get("normal_apply_authority") == "reports/operator_summary.json"
    )
    historical_outlines_apply_authority = False
    sync_policy = index_payload.get("research_snapshot_sync_policy")
    source_status_apply_blocking = bool(
        sync_policy.get("source_status_apply_blocking", False)
        if isinstance(sync_policy, dict)
        else False
    )
    status = (
        "current"
        if active_evidence_index_present
        and machine_evidence_index_present
        and not historical_outlines_apply_authority
        and not source_status_apply_blocking
        else "attention"
    )

    return ResearchContextPreflight(
        status=status,
        active_evidence_index_present=active_evidence_index_present,
        active_evidence_index_path="docs/research/current-truth.md",
        machine_evidence_index_present=machine_evidence_index_present,
        machine_evidence_index_path="docs/research/current-truth-index.json",
        authority=str(index_payload.get("authority") or "missing"),
        operator_gate_impact=str(index_payload.get("operator_gate_impact") or "missing"),
        normal_apply_authority=str(
            index_payload.get("normal_apply_authority")
            or "reports/operator_summary.json"
        ),
        recommended_research_entrypoint="docs/research/current-truth.md",
        historical_outline_count=len(historical_outline_paths),
        historical_outline_paths=historical_outline_paths,
        historical_outlines_apply_authority=historical_outlines_apply_authority,
        source_status_apply_blocking=source_status_apply_blocking,
        notes=(
            "Historical research outline files are evidence only.",
            "Use docs/research/current-truth.md before opening dated research folders.",
            "Research context diagnostics do not replace reports/operator_summary.json.",
        ),
    )


def build_contract_preflight(
    repo_root: str | Path = ".",
    *,
    git: GitPreflight | None = None,
    skill_install_root: str | Path | None = None,
) -> dict[str, object]:
    root = Path(repo_root).resolve()
    repo_root_exists = root.exists()
    skill_root = root / ".agents" / "skills" / "hsconfig"
    skill_text = _read(skill_root / "SKILL.md")
    workflow_text = _read(skill_root / "references" / "workflow.md")
    checklist_text = _read(skill_root / "references" / "contract-compiler-checklist.md")
    operator_text = _read(root / "docs" / "operator" / "README.md")
    combined = "\n".join([skill_text, workflow_text, checklist_text, operator_text])
    references_line = _references_line(skill_text)
    git_snapshot = git or build_git_preflight(root)
    research_context = build_research_context_preflight(root)
    installed_skill_sync = build_installed_skill_sync_status(root, skill_install_root)

    checks = {
        "repo_current": (
            git_snapshot.clean_for_runtime_work
            and git_snapshot.origin_main_error is None
            and git_snapshot.behind_origin_main == 0
        ),
        "skill_root_present": skill_root.exists(),
        "installed_skill_sync_current": (
            installed_skill_sync.get("matches_repo_skill") is True
            and installed_skill_sync.get("diagnostic_only") is True
            and installed_skill_sync.get("runtime_apply_authority")
            == "reports/operator_summary.json"
        ),
        "reference_files_present": all(
            (skill_root / relative_path).exists()
            for relative_path in REQUIRED_REFERENCE_FILES
        ),
        "checklist_referenced_by_normal_workflow": (
            "Contract compiler checklist: `references/contract-compiler-checklist.md`."
            in skill_text
            and "Contract compiler checklist: `references/contract-compiler-checklist.md`."
            in workflow_text
        ),
        "checklist_listed_in_references": (
            "references/contract-compiler-checklist.md" in references_line
        ),
        "configure_acceptance_route_visible": _configure_acceptance_route_visible(
            combined
        ),
        "configure_acceptance_projection_not_gate_visible": (
            _configure_acceptance_projection_not_gate_visible(combined)
        ),
        "config_quality_summary_diagnostic_only_visible": (
            _config_quality_summary_diagnostic_only_visible(combined)
        ),
        "config_proof_summary_visible": _config_proof_summary_visible(combined),
        "operator_summary_single_authority_visible": (
            "operator_summary.json remains the only normal apply authority" in combined
            or "operator_summary.json` remains the only normal apply authority"
            in combined
        ),
        "source_status_nonblocking_visible": (
            "source_status_apply_blocking" in combined
            and "must remain `false`" in combined
            and "SOURCE_BACKED_STRONG is an evidence-quality label" in combined
        ),
        "no_default_only_visible": (
            "No hidden default-only runtime" in combined
            and "default_only_runtime_surfaces=[]" in combined
        ),
        "runtime_surface_boundary_visible": all(
            term in combined
            for term in (
                "`GlobalValues.json`",
                "`Mulligan.json`",
                "`per-card <CARDID>.json`",
                "`Combo.json`",
                "`Presume.json`",
                "`Concede.json`",
                "outside the normal HSConfig output path",
            )
        ),
        "darkbishop_effect_not_mulligan_visible": (
            "Darkbishop" in combined
            and "hero-power-transform" in combined
            and "do not emit a Mulligan keep without explicit opening-hand source text"
            in combined
        ),
        "negative_scope_visible": all(
            term in combined
            for term in (
                "does not parse replays",
                "inspect " + "win" + "rate",
                "analyze runtime logs",
                "tune after games",
            )
        ),
        "diagnostic_only_visible": (
            "diagnostic-only" in combined
            and "not another operator gate" in checklist_text
            and "not another runtime apply gate" in combined
        ),
        "research_current_truth_index_visible": (
            research_context.status == "current"
            and research_context.active_evidence_index_present
            and research_context.machine_evidence_index_present
            and research_context.authority == "evidence_index_only"
            and research_context.operator_gate_impact == "diagnostic_only"
            and research_context.normal_apply_authority == "reports/operator_summary.json"
            and research_context.source_status_apply_blocking is False
        ),
        "historical_research_outlines_diagnostic_only": (
            research_context.historical_outlines_apply_authority is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    payload: dict[str, object] = {
        "status": "PASS" if not failures else "ATTENTION",
        "repo_root": str(root),
        "git": asdict(git_snapshot),
        "checks": checks,
        "failures": failures,
        "research_context": asdict(research_context),
        "installed_skill_sync": installed_skill_sync,
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "diagnostic_only": True,
    }
    if not repo_root_exists:
        payload["error"] = {
            "type": "FileNotFoundError",
            "message": f"repo root does not exist: {root}",
        }
    return payload
