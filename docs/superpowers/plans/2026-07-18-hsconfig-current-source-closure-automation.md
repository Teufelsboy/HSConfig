# HSConfig Current Source Closure Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep HSConfig current and clean while making the 12-deck Wild source-closure workflow automatically surface the next claim needed for `SOURCE_BACKED_STRONG` without creating apply blockers or default-only runtime surfaces.

**Architecture:** Do not rewrite the existing Source/Contract spine. Add a narrow repo-currentness preflight and extend the existing source-candidate, research-deep, and closure-optimizer surfaces so online source candidates, fetched full-text claims, generated packages, and first missing source actions reconcile into one diagnostic priority queue. Runtime generation stays on the normal `prepare`/`configure` pipeline; `operator_summary.json` remains the only normal apply authority.

**Tech Stack:** Python, pytest, existing HSConfig CLI/package builders, existing source candidate registry, existing source closure optimizer, existing research-deep outline/results under `docs/research`, Git CLI for repository currentness checks.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Run `git fetch --all --prune --tags` before planning, source refresh, config generation, or runtime-facing verification.
- End with no dirty worktree unless the user explicitly asks to leave reviewed local changes uncommitted.
- Do not run destructive git cleanup: no `git reset --hard`, no `git clean`, no branch deletion, no unrequested force push.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or runtime-apply gate.
- `SOURCE_BACKED_PARTIAL` must remain load-safe when the package is technically valid.
- `source_status_apply_blocking` must stay `false` for source-quality gaps.
- Candidate URLs, decklist pages, HSGuru/Hearthstone-Decks pages, and source proof rows are acquisition/provenance only until fetched text produces normalized claim kinds.
- No default-only runtime surface may silently count as strong. Default-only surfaces must be visible and must prevent `SOURCE_BACKED_STRONG`.
- ShadowPriest must preserve Darkbishop Benedictus / `SW_448` start-of-game hero-power-transform behavior while keeping `SW_448` out of opening-hand mulligan keeps unless an explicit opening-hand keep source exists.
- Use the existing research-deep acceptance loop at `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml`; do not create a parallel outline unless the existing outline cannot represent a required field.

---

## File Structure

- Create: `scripts/check_hsconfig_currentness.py`  
  Small Git preflight used by agents before source/config work. It reports branch, upstream, dirty state, and `HEAD...origin/main` counts. It never mutates files or branches.

- Test: `tests/test_currentness_check_script.py`  
  Unit tests for parsing status/ahead-behind output and detecting dirty or no-upstream states without running real Git.

- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml`  
  Add currentness and promotion fields needed by the next research-deep run.

- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml`  
  Keep the same 12 deck items, but make the focus text explicitly require current public source check plus full-text claim closure status.

- Modify: `docs/operator/source-candidate-proof-decks.json`  
  Keep candidate/proof rows aligned with `src/hsconfig/source_candidate_registry.py` and ensure context-only rows cannot claim `first_missing_source_action=none`.

- Modify: `src/hsconfig/source_candidate_registry.py`  
  Update only current candidate metadata and explicit strength ceilings. Do not add runtime behavior here.

- Modify: `tests/test_source_candidate_registry_matrix.py`  
  Assert registry/proof doc consistency, runtime-claim ceilings, context-only limits, and exact first missing source actions.

- Modify: `src/hsconfig/source_closure_optimizer.py`  
  Add a batch priority-queue builder that combines package `operator_summary.json`, candidate proof rows, optional research-deep result rows, and default-only state.

- Test: `tests/test_source_closure_priority_queue.py`  
  Focused tests for the new batch optimizer behavior.

- Modify: `docs/operator/source-backed-strong-closure.md`  
  Document the priority queue and the distinction between current decklist support and runtime-claim authority.

- Modify: `.agents/skills/hsconfig/SKILL.md`  
  Document the preflight and priority queue as operator workflow, then sync installed skill.

---

### Task 1: Add Non-Mutating Repository Currentness Preflight

**Files:**
- Create: `scripts/check_hsconfig_currentness.py`
- Create: `tests/test_currentness_check_script.py`

**Interfaces:**
- Consumes:
  - `git status --short --branch`
  - `git rev-parse --abbrev-ref --symbolic-full-name @{u}`
  - `git rev-list --left-right --count HEAD...origin/main`
- Produces:
  - `RepoCurrentness` dataclass
  - `parse_status_short(text: str) -> tuple[str, bool]`
  - `parse_ahead_behind(text: str) -> tuple[int, int]`
  - JSON CLI output with `dirty`, `ahead_origin_main`, `behind_origin_main`, `upstream`, `clean_for_runtime_work`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_currentness_check_script.py`:

```python
from scripts.check_hsconfig_currentness import (
    parse_ahead_behind,
    parse_status_short,
)


def test_parse_clean_branch_status() -> None:
    branch, dirty = parse_status_short("## codex/hsconfig-canonical-source-status-sync\n")

    assert branch == "codex/hsconfig-canonical-source-status-sync"
    assert dirty is False


def test_parse_dirty_branch_status() -> None:
    branch, dirty = parse_status_short(
        "## codex/hsconfig-canonical-source-status-sync\n M src/hsconfig/source_candidate_registry.py\n"
    )

    assert branch == "codex/hsconfig-canonical-source-status-sync"
    assert dirty is True


def test_parse_ahead_behind_counts() -> None:
    assert parse_ahead_behind("54\t0\n") == (54, 0)
    assert parse_ahead_behind("0 2\n") == (0, 2)
```

- [ ] **Step 2: Run parser tests and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_currentness_check_script.py -q
```

Expected before implementation: import failure.

- [ ] **Step 3: Implement the currentness script**

Create `scripts/check_hsconfig_currentness.py`:

```python
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import subprocess
from pathlib import Path


@dataclass(frozen=True)
class RepoCurrentness:
    cwd: str
    branch: str
    upstream: str | None
    dirty: bool
    ahead_origin_main: int
    behind_origin_main: int
    clean_for_runtime_work: bool


def parse_status_short(text: str) -> tuple[str, bool]:
    lines = [line for line in text.splitlines() if line.strip()]
    branch_line = lines[0] if lines else "## unknown"
    branch = branch_line.removeprefix("## ").split("...")[0].strip()
    dirty = any(not line.startswith("## ") for line in lines)
    return branch, dirty


def parse_ahead_behind(text: str) -> tuple[int, int]:
    parts = text.replace("\t", " ").split()
    if len(parts) < 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def build_currentness(cwd: str | Path) -> RepoCurrentness:
    root = Path(cwd)
    status = _run_git(root, "status", "--short", "--branch").stdout
    branch, dirty = parse_status_short(status)

    upstream_result = _run_git(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
        check=False,
    )
    upstream = upstream_result.stdout.strip() or None

    ahead, behind = parse_ahead_behind(
        _run_git(root, "rev-list", "--left-right", "--count", "HEAD...origin/main").stdout
    )
    return RepoCurrentness(
        cwd=str(root),
        branch=branch,
        upstream=upstream,
        dirty=dirty,
        ahead_origin_main=ahead,
        behind_origin_main=behind,
        clean_for_runtime_work=(not dirty and behind == 0),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    currentness = build_currentness(args.cwd)
    if args.json:
        print(json.dumps(asdict(currentness), indent=2, sort_keys=True))
    else:
        print(
            f"branch={currentness.branch} dirty={currentness.dirty} "
            f"ahead_origin_main={currentness.ahead_origin_main} "
            f"behind_origin_main={currentness.behind_origin_main} "
            f"clean_for_runtime_work={currentness.clean_for_runtime_work}"
        )
    return 0 if currentness.clean_for_runtime_work else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run parser tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_currentness_check_script.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Run live preflight after fetch**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune --tags
python scripts/check_hsconfig_currentness.py --cwd . --json
```

Expected for current feature branch: JSON shows `dirty=false`, `behind_origin_main=0`, and `clean_for_runtime_work=true`. `ahead_origin_main` may be greater than zero on an unmerged feature branch.

---

### Task 2: Tighten The Research-Deep Acceptance Loop

**Files:**
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml`
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml`
- Test: existing research outline readability via PowerShell here-string piped to `python -`

**Interfaces:**
- Consumes: the existing 12-deck outline.
- Produces: research fields that separate current decklist context from runtime-claim authority.

- [ ] **Step 1: Add fields for currentness and promotion boundary**

In `fields.yaml`, ensure `fields:` contains these entries:

```yaml
  currentness_sources:
    type: array
    description: Current public decklist, category, stats, or meta pages that prove current archetype/deck presence but do not prove runtime claims by themselves.
  full_text_claim_sources:
    type: array
    description: Public fetched full-text sources that contain mulligan, gameplan, combo, card-role, hero-power, or mechanic claims that can be normalized into claim kinds.
  promotion_boundary:
    type: string
    description: One of runtime_claims_possible_if_fetched_claims_close, partial_until_missing_source_action_closes, context_only_never_promotes.
  source_status_apply_blocking_expected:
    type: boolean
    description: Must remain false for all valid packages; source-quality gaps are diagnostic.
  default_only_runtime_surfaces_expected:
    type: string
    description: Must be none for generated runtime packages; any non-none value prevents SOURCE_BACKED_STRONG.
```

- [ ] **Step 2: Update each outline item focus**

For every item in `outline.yaml`, update `focus` to include this sentence:

```yaml
focus: Source closure for this Wild deck: identify current public decklist/context pages separately from fetched full-text mulligan/gameplan/combo/card-role claims, and report the first missing source action without treating source partial as apply-blocking.
```

Keep each existing `deck_code` exactly unchanged.

- [ ] **Step 3: Verify YAML parses**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
from pathlib import Path
import yaml

for path in [
    Path("docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml"),
    Path("docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml"),
]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), path
print("research acceptance loop yaml ok")
'@ | python -
```

Expected:

```text
research acceptance loop yaml ok
```

- [ ] **Step 4: Run research-deep only when executing the plan**

During execution, invoke the Codex `research-deep` skill with working directory `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop`. Let the skill read the local `outline.yaml` and `fields.yaml`.

Expected result: refreshed `results/*.json` rows for all 12 decks. If online sources are unreachable, keep the source row partial and record the failure as diagnostic.

---

### Task 3: Refresh Candidate Registry And Proof Manifest Without Over-Promotion

**Files:**
- Modify: `src/hsconfig/source_candidate_registry.py`
- Modify: `docs/operator/source-candidate-proof-decks.json`
- Modify: `tests/test_source_candidate_registry_matrix.py`

**Interfaces:**
- Consumes:
  - `source_candidates_for_deck(deck_name, deck_code=None) -> list[SourceCandidate]`
  - `docs/operator/source-candidate-proof-decks.json`
- Produces:
  - registry/proof rows where current full-text sources may have `runtime_claims_possible`
  - decklist/category/stat pages remain `context_only`
  - support seeds remain `candidate_partial` unless their fetched full text closes claims

- [ ] **Step 1: Add candidate proof policy assertions**

In `tests/test_source_candidate_registry_matrix.py`, add:

```python
def test_candidate_rows_do_not_promote_from_context_only_sources():
    proof = json.loads(PROOF_PATH.read_text(encoding="utf-8"))

    for row in proof["decks"]:
        deck_name = row["deck_name"]
        candidates = source_candidates_for_deck(deck_name)
        for candidate in candidates:
            if candidate.strength_ceiling == "context_only":
                assert candidate.expected_claim_kinds == (), candidate.url
                assert candidate.first_missing_source_action != "none", candidate.url
                assert "decklist" in candidate.source_family or "stats" in candidate.source_family


def test_runtime_claims_possible_candidates_declare_claim_kinds():
    for deck_name, deck_code in DECKS.items():
        candidates = source_candidates_for_deck(deck_name, deck_code)
        runtime_candidates = [
            candidate
            for candidate in candidates
            if candidate.strength_ceiling == "runtime_claims_possible"
        ]
        assert runtime_candidates, deck_name
        assert all(candidate.expected_claim_kinds for candidate in runtime_candidates)
```

- [ ] **Step 2: Run registry tests and confirm any mismatch**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py -q
```

Expected before metadata refresh: failures only for registry/proof mismatch or over-promoted context rows.

- [ ] **Step 3: Update registry rows conservatively**

For each of the 12 decks in `src/hsconfig/source_candidate_registry.py`, enforce this rule:

```python
if source_visibility == "decklist_only":
    strength_ceiling = "context_only"
    expected_claim_kinds = ()
    first_missing_source_action = "add_current_full_text_mulligan_or_gameplan_source"
```

For full-text guide/community-guide candidates, allow:

```python
strength_ceiling = "runtime_claims_possible"
expected_claim_kinds = (
    "gameplan_posture",
    "mulligan_keep",
    "card_role",
)
first_missing_source_action = "none"
```

Only use `first_missing_source_action="none"` when the candidate is expected to fetch enough full text to close the first missing chain.

- [ ] **Step 4: Update proof manifest to mirror registry order**

For every row in `docs/operator/source-candidate-proof-decks.json`, set:

```json
"strongness_policy": "Candidate URLs are source acquisition seeds only. SOURCE_BACKED_STRONG requires fetched full-text claims that pass source evidence policy, claim-kind normalization, surface gates, and closure profile checks."
```

For each deck, concatenate:

```text
candidate_urls + support_seed_urls + context_seed_urls
```

and ensure the result exactly matches:

```python
[candidate.url for candidate in source_candidates_for_deck(deck_name)]
```

- [ ] **Step 5: Run registry tests again**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py -q
```

Expected: pass.

---

### Task 4: Add Batch Source Closure Priority Queue

**Files:**
- Modify: `src/hsconfig/source_closure_optimizer.py`
- Create: `tests/test_source_closure_priority_queue.py`

**Interfaces:**
- Consumes:
  - package directories containing `reports/operator_summary.json`
  - optional `candidate_proof_path`
  - optional `research_results_dir`
- Produces:
  - `build_source_closure_priority_queue(package_dirs, candidate_proof_path=None, research_results_dir=None) -> dict[str, Any]`

- [ ] **Step 1: Write failing priority queue tests**

Create `tests/test_source_closure_priority_queue.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_closure_optimizer import build_source_closure_priority_queue


def _package(tmp_path: Path, deck_name: str, operator: dict) -> Path:
    package = tmp_path / deck_name / "04_package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    payload = {
        "deck": {"name": deck_name},
        "technical_status": "VALID_PACKAGE",
        "runtime_load_safe": True,
        "source_status_apply_blocking": False,
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
        "default_only_runtime_surfaces": [],
        "source_backed_strong_closure": {
            "status": "needs_source_closure",
            "promotion_ready": False,
            "first_missing_source_action": "add_card_specific_source_claim",
            "diagnostic_only": True,
            "closure_profile_closed": False,
        },
    }
    payload.update(operator)
    (reports / "operator_summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return package


def test_priority_queue_orders_partial_before_strong(tmp_path: Path) -> None:
    partial = _package(tmp_path, "BigShaman", {})
    strong = _package(
        tmp_path,
        "ShadowPriest",
        {
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_strong_closure": {
                "status": "ready",
                "promotion_ready": True,
                "first_missing_source_action": "none",
                "diagnostic_only": True,
                "closure_profile_closed": True,
            },
        },
    )

    report = build_source_closure_priority_queue([strong, partial])

    assert report["schema_version"] == 1
    assert report["authority"] == "diagnostic_only"
    assert report["summary"]["deck_count"] == 2
    assert report["summary"]["strong_count"] == 1
    assert report["summary"]["apply_blocker_count"] == 0
    assert report["summary"]["default_only_count"] == 0
    assert [row["deck_name"] for row in report["priority_rows"]] == ["BigShaman"]


def test_priority_queue_surfaces_default_only_as_strong_blocker_not_apply_blocker(tmp_path: Path) -> None:
    package = _package(
        tmp_path,
        "Synthetic",
        {
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "first_missing_source_action": "replace_default_only_runtime_surface_with_source_or_policy_claim",
        },
    )

    report = build_source_closure_priority_queue([package])

    row = report["records"][0]
    assert row["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert row["source_status_apply_blocking"] is False
    assert row["recommended_operator_action"] == (
        "replace default-only runtime surfaces with source-backed, policy-backed, or static-semantics-backed rows"
    )
```

- [ ] **Step 2: Run priority queue tests and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_closure_priority_queue.py -q
```

Expected before implementation: import failure for `build_source_closure_priority_queue`.

- [ ] **Step 3: Implement batch builder in `source_closure_optimizer.py`**

Add:

```python
def build_source_closure_priority_queue(
    package_dirs: list[str | Path],
    *,
    candidate_proof_path: str | Path | None = None,
    research_results_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = [
        build_source_closure_optimizer_report(
            package_dir,
            candidate_proof_path=candidate_proof_path,
            dossier=_research_dossier_for_package(package_dir, research_results_dir),
        )
        for package_dir in package_dirs
    ]
    priority_rows = [
        record
        for record in records
        if record["decision"] not in {"strong"}
    ]
    priority_rows.sort(
        key=lambda row: (
            _priority_bucket(row),
            str(row.get("deck_name") or ""),
        )
    )
    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "normal_apply_authority": str(OPERATOR_SUMMARY_RELATIVE_PATH),
        "summary": {
            "deck_count": len(records),
            "strong_count": sum(1 for row in records if row["decision"] == "strong"),
            "partial_count": sum(1 for row in records if row["decision"] != "strong"),
            "apply_blocker_count": sum(
                1 for row in records if row["source_status_apply_blocking"] is True
            ),
            "default_only_count": sum(
                1 for row in records if row["default_only_runtime_surfaces"]
            ),
        },
        "records": records,
        "priority_rows": priority_rows,
    }
```

Add helpers:

```python
def _priority_bucket(row: Mapping[str, Any]) -> int:
    if row.get("default_only_runtime_surfaces"):
        return 0
    if row.get("decision") == "partial_source_action_needed":
        return 1
    if row.get("decision") == "preserved_partial_stop_condition":
        return 2
    if row.get("decision") == "context_only_load_safe":
        return 3
    return 4


def _research_dossier_for_package(
    package_dir: str | Path,
    research_results_dir: str | Path | None,
) -> dict[str, Any]:
    if research_results_dir is None:
        return {}
    package_path = Path(package_dir)
    operator = _read_json(package_path / OPERATOR_SUMMARY_RELATIVE_PATH)
    deck = _deck_name(operator, package_path)
    result_path = Path(research_results_dir) / f"{deck}.json"
    if not result_path.exists():
        return {}
    return _read_json(result_path)
```

- [ ] **Step 4: Run priority queue tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_closure_priority_queue.py -q
```

Expected: pass.

---

### Task 5: Generate And Verify The 12-Deck Runtime Matrix

**Files:**
- Modify only if needed: `tests/test_universal_wild_no_block_matrix.py`
- Generated during verification only: `outputs/2026-07-18-current-source-closure-automation/all-decks-r1`
- Generated during verification only: `tmp/2026-07-18-current-source-closure-automation/all-decks-r1/matrix.json`

**Interfaces:**
- Consumes: the 12 user deck names/codes already in `tests/test_universal_wild_no_block_matrix.py`.
- Produces: verified package matrix with no default-only surfaces and no source apply blocker.

- [ ] **Step 1: Run the no-block matrix tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected: pass. If a generated package is partial, it must still be load-safe and `source_status_apply_blocking=false`.

- [ ] **Step 2: Generate fresh packages through the normal pipeline**

Use the existing CLI route used by prior matrix runs. The command must use the normal `configure` or existing source workflow command; do not hand-write CustomConfig JSON.

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m hsconfig configure --deck-name ShadowPriest --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --out outputs/2026-07-18-current-source-closure-automation/ShadowPriest-r1 --json
```

Expected: exit 0 and generated `04_package/reports/operator_summary.json`.

Repeat for the other 11 decks using the exact deck names/codes from the user request or an existing repo matrix helper if available.

- [ ] **Step 3: Build priority queue for generated packages**

Run a short Python check:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
from pathlib import Path
import json
from hsconfig.source_closure_optimizer import build_source_closure_priority_queue

root = Path("outputs/2026-07-18-current-source-closure-automation")
packages = sorted(root.glob("*/04_package"))
report = build_source_closure_priority_queue(
    packages,
    candidate_proof_path="docs/operator/source-candidate-proof-decks.json",
    research_results_dir="docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results",
)
out = Path("tmp/2026-07-18-current-source-closure-automation/all-decks-r1")
out.mkdir(parents=True, exist_ok=True)
(out / "priority_queue.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report["summary"], sort_keys=True))
'@ | python -
```

Expected summary shape:

```json
{"apply_blocker_count": 0, "deck_count": 12, "default_only_count": 0, "partial_count": 11, "strong_count": 1}
```

If more decks become strong after fetched claim closure, `strong_count` may be greater than `1`, but `apply_blocker_count` and `default_only_count` must remain `0`.

- [ ] **Step 4: Verify ShadowPriest Darkbishop canary**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_universal_wild_no_block_matrix.py::test_valid_wild_deck_produces_load_safe_warning_apply_package -q
```

Expected: pass, including the ShadowPriest assertion that `SW_448.json` keeps hero-power-transform semantics and `Mulligan.json` does not keep `SW_448`.

---

### Task 6: Update Operator Docs And Skill Text

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Verify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Test: `tests/test_operator_docs_contract_policy.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: priority queue fields and currentness preflight.
- Produces: operator docs and installed skill that say the same thing as the code.

- [ ] **Step 1: Add docs wording for currentness preflight**

In `.agents/skills/hsconfig/SKILL.md`, add:

```markdown
- Before source refresh, deck package generation, or runtime-facing apply work, run `git fetch --all --prune --tags`, then `python scripts/check_hsconfig_currentness.py --cwd . --json`. A feature branch may be ahead of `origin/main`, but it must not be behind and the worktree must be clean before runtime-facing verification.
```

- [ ] **Step 2: Add docs wording for priority queue**

In `docs/operator/source-backed-strong-closure.md`, add:

```markdown
The source closure priority queue is diagnostic-only. It combines package `operator_summary.json`, source candidate proof rows, and optional research-deep result rows to decide which source claim should be closed next. It must not write runtime config and must not set `source_status_apply_blocking=true`.
```

- [ ] **Step 3: Add docs wording for decklist/currentness boundary**

In `docs/operator/universal-wild-no-block-contract.md`, add:

```markdown
Current decklist, category, and stats pages prove current public context only. They can help choose candidate URLs, but they do not prove runtime claims by themselves. `SOURCE_BACKED_STRONG` requires fetched full-text evidence that normalizes into supported claim kinds and passes runtime-surface gates.
```

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected: installed `hsconfig` skill is synchronized.

- [ ] **Step 5: Run docs and skill tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_files.py -q
```

Expected: pass.

---

### Task 7: Final Verification And Clean Handoff

**Files:**
- Verify all modified files.

**Interfaces:**
- Consumes: all changes from Tasks 1-6.
- Produces: evidence that the implementation is current, source-contract-safe, no-block, and clean.

- [ ] **Step 1: Run focused verification**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_currentness_check_script.py tests/test_source_candidate_registry_matrix.py tests/test_source_closure_optimizer.py tests/test_source_closure_priority_queue.py tests/test_universal_wild_no_block_matrix.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the existing source/contract guard suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py tests/test_configure_online_source.py tests/test_claim_kind_runtime_contract.py tests/test_source_closure_optimizer.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Verify installed skill remains synced**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python scripts/sync_installed_skill.py --check
```

Expected: exits 0.

- [ ] **Step 4: Verify diff hygiene**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --check
git status --short --branch
python scripts/check_hsconfig_currentness.py --cwd . --json
```

Expected:

- `git diff --check` exits 0.
- `git status --short --branch` shows only intended files before commit, or clean after commit.
- currentness JSON has `dirty=false` after commit and `behind_origin_main=0`.

- [ ] **Step 5: Commit if tests pass**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add scripts/check_hsconfig_currentness.py tests/test_currentness_check_script.py src/hsconfig/source_candidate_registry.py src/hsconfig/source_closure_optimizer.py tests/test_source_candidate_registry_matrix.py tests/test_source_closure_priority_queue.py docs/operator/source-candidate-proof-decks.json docs/operator/source-backed-strong-closure.md docs/operator/universal-wild-no-block-contract.md docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml .agents/skills/hsconfig/SKILL.md
git commit -m "feat: automate current source closure queue"
```

Expected: commit succeeds. Do not push unless the user explicitly requests it.

---

## Acceptance Criteria

- [ ] Repo was refreshed before execution with `git fetch --all --prune --tags`.
- [ ] Currentness preflight exists and reports dirty/ahead/behind state without mutating the repo.
- [ ] Research-deep acceptance loop distinguishes currentness sources from full-text runtime-claim sources.
- [ ] Candidate registry and proof manifest agree exactly.
- [ ] Context-only sources cannot declare runtime claim kinds or `first_missing_source_action=none`.
- [ ] Batch source closure priority queue reports `authority=diagnostic_only`.
- [ ] Priority queue never writes runtime config.
- [ ] Valid generated Wild packages have `source_status_apply_blocking=false`.
- [ ] Valid generated Wild packages have no default-only runtime surfaces.
- [ ] ShadowPriest preserves `SW_448` hero-power-transform runtime semantics and does not keep `SW_448` in mulligan.
- [ ] Focused source/contract and docs/skill tests pass.
- [ ] Installed HSConfig skill is synced.
- [ ] Final worktree is clean after commit, or only intended files remain before commit.

## Subagent-Driven Execution Strategy

- **Explorer subagent, read-only:** inspect current `source_candidate_registry.py`, `source_closure_optimizer.py`, and proof manifest alignment before writing.
- **Research subagent, read-only:** refresh the research-deep acceptance-loop interpretation and summarize which decks have current context only versus full-text claim candidates.
- **Contract reviewer subagent, read-only:** verify no task makes source partial apply-blocking or lets context-only sources promote strong.
- **Main writer:** implement the files in Tasks 1-6, run Task 7 verification, and own all final edits.
- **Final reviewer subagent, read-only:** inspect final diff and test evidence for scope creep, dirty-worktree risk, and Darkbishop/default-only regressions.

## Execution Handoff

Plan complete. Recommended execution mode is **Subagent-Driven** because the tasks split cleanly into read-only source review, contract review, and one main writer.

After approval, execute with:

```text
Setze den Plan SubAgent Driven um
```
