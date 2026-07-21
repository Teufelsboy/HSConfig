from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess


REQUIRED_REFERENCE_FILES = (
    "references/workflow.md",
    "references/visionai-surfaces.md",
    "references/guide-research-policy.md",
    "references/globalvalues-policy.md",
    "references/card-behavior-policy.md",
    "references/contract-compiler-checklist.md",
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
    status = _run_git(root, "status", "--short", "--branch").stdout
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


def _references_line(skill_text: str) -> str:
    for line in skill_text.splitlines():
        if line.startswith("## References:"):
            return line
    return ""


def build_contract_preflight(
    repo_root: str | Path = ".",
    *,
    git: GitPreflight | None = None,
) -> dict[str, object]:
    root = Path(repo_root).resolve()
    skill_root = root / ".agents" / "skills" / "hsconfig"
    skill_text = _read(skill_root / "SKILL.md")
    workflow_text = _read(skill_root / "references" / "workflow.md")
    checklist_text = _read(skill_root / "references" / "contract-compiler-checklist.md")
    operator_text = _read(root / "docs" / "operator" / "README.md")
    combined = "\n".join([skill_text, workflow_text, checklist_text, operator_text])
    references_line = _references_line(skill_text)
    git_snapshot = git or build_git_preflight(root)

    checks = {
        "repo_current": (
            git_snapshot.clean_for_runtime_work
            and git_snapshot.origin_main_error is None
            and git_snapshot.behind_origin_main == 0
        ),
        "skill_root_present": skill_root.exists(),
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
                "inspect winrate",
                "analyze runtime logs",
                "tune after games",
            )
        ),
        "diagnostic_only_visible": (
            "diagnostic-only" in combined
            and "not another operator gate" in checklist_text
            and "not another runtime apply gate" in combined
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "status": "PASS" if not failures else "ATTENTION",
        "repo_root": str(root),
        "git": asdict(git_snapshot),
        "checks": checks,
        "failures": failures,
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "diagnostic_only": True,
    }
