# HSConfig Sync No-Block Visibility Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig provably current, no-block for valid decks, and broader across Wild mechanic visibility without adding post-run HSTuner scope.

**Architecture:** Keep HSConfig pre-run only. `reports/operator_summary.json` remains the single runtime-apply gate, `hsconfig acceptance-matrix` remains read-only diagnostics, and supplemental Wild decks improve visibility without widening the representative source-depth matrix.

**Tech Stack:** Python 3, pytest, local CLI module `hsconfig`, JSON operator artifacts, repo-owned Codex skill under `.agents/skills/hsconfig`, installed skill under `C:\Users\darbo\.codex\skills\hsconfig`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add replay parsing, HDT parsing, Power.log parsing, winrate analysis, candidate promotion, or post-run tuning to HSConfig.
- Do not make `acceptance_matrix` a runtime apply gate; it is diagnostic only.
- Do not split runtime permission across multiple reports; `reports/operator_summary.json` remains the single operator gate.
- Do not emit `Concede.json` or `Presume.json` in normal HSConfig output.
- `GlobalValues.json` and `Mulligan.json` remain the minimal load-safe runtime files.
- Warning-only, partial, future, or unknown mechanics must not block `load_safe_apply` when `technical_status=VALID_PACKAGE`.
- Supplemental visibility decks must not be counted as representative source-depth rows.
- No raw HearthRanger runtime logs, HDT files, Power.log, or private runtime evidence belongs in this repo.

---

## File Structure

- `scripts/sync_installed_skill.py`
  - Existing sync authority. No code change expected unless verification exposes a new edge case.
- `tests/test_skill_sync.py`
  - Existing tests for exact installed-skill sync and normalized-text drift messaging.
- `src/hsconfig/acceptance_matrix.py`
  - Add row-level matrix status clarity and top-level status authority metadata.
- `tests/test_acceptance_matrix.py`
  - Add/adjust tests that prove detail fields cannot override top-level matrix status.
- `docs/operator/README.md`
  - Clarify how to read `acceptance-matrix` status versus detail fields.
- `docs/operator/universal-wild-no-block-contract.md`
  - Clarify supplemental visibility decks and matrix status authority.
- `docs/operator/supplemental-proof-decks.json`
  - Add SecretMage and HighlanderPriest as supplemental visibility-only proof decks.
- `tests/test_supplemental_visibility_decks.py`
  - New test file proving supplemental visibility decks are non-representative, load-safe, and no-block.
- `.agents/skills/hsconfig/SKILL.md`
  - Only touch if Task 4 docs need one concise operator-facing note; otherwise leave unchanged and simply sync installed copy.

---

### Task 1: Exact Installed Skill Sync

**Files:**
- Read: `scripts/sync_installed_skill.py`
- Read: `tests/test_skill_sync.py`
- Runtime write outside repo: `C:\Users\darbo\.codex\skills\hsconfig`
- No versioned repo file should change in this task.

**Interfaces:**
- Consumes: existing `sync_skill(install_root: Path) -> Path` and CLI flags `--check`, `--install-root`.
- Produces: installed HSConfig skill byte-identical to `.agents/skills/hsconfig`.

- [ ] **Step 1: Confirm current drift before fixing**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected now:

```text
HSConfig skill drift detected: C:\Users\darbo\.codex\skills\hsconfig
- references/workflow.md: bytes_differ (normalized text matches; run without --check to re-sync exact bytes)
- SKILL.md: bytes_differ (normalized text matches; run without --check to re-sync exact bytes)
```

- [ ] **Step 2: Re-sync installed skill from repo-owned source**

Run:

```powershell
python scripts\sync_installed_skill.py
```

Expected:

```text
Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 3: Verify exact-byte sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Verify existing sync tests still pass**

Run:

```powershell
python -m pytest tests/test_skill_sync.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Confirm no repo mutation from runtime sync**

Run:

```powershell
git status --short
```

Expected: no versioned changes from this task.

No commit is needed for Task 1 because the only write is the installed local skill copy outside the repository.

---

### Task 2: Acceptance Matrix Status Authority Clarity

**Files:**
- Modify: `src/hsconfig/acceptance_matrix.py`
- Modify: `tests/test_acceptance_matrix.py`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`

**Interfaces:**
- Consumes: `build_acceptance_matrix(package_paths: Sequence[str | Path]) -> dict[str, Any]`
- Produces: matrix payload with explicit `status_authority`, per-row `matrix_row_status`, and per-row `matrix_row_failure_reasons`.

- [ ] **Step 1: Write failing tests for status authority and row failure reasons**

Append to `tests/test_acceptance_matrix.py`:

```python
def test_acceptance_matrix_status_is_authoritative_when_detail_fields_conflict(
    tmp_path: Path,
):
    package = tmp_path / "missing-baseline"
    deck_dir = package / "CustomConfig" / "deck"
    reports = package / "reports"
    write_json(
        deck_dir / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        deck_dir / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(reports / "input_manifest.json", {"deck_name": "deck"})
    write_json(
        reports / "operator_summary.json",
        {
            "deck": {"name": "MissingBaseline"},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
            "config_usefulness": {"status": "guide_aligned"},
            "no_block_failure_mode_summary": {
                "categories": {"technical_hard_block": []}
            },
        },
    )

    matrix = build_acceptance_matrix([package])
    row = matrix["packages"][0]

    assert matrix["status"] == "failed"
    assert matrix["status_authority"]["field"] == "status"
    assert matrix["status_authority"]["detail_fields_are_diagnostic"] is True
    assert row["apply_gate_allowed"] is True
    assert row["matrix_row_status"] == "failed"
    assert "validation_not_passed" in row["matrix_row_failure_reasons"]
    assert row["matrix_row_interpretation"].startswith(
        "Row failed matrix acceptance"
    )
```

Append a second test for a passing package:

```python
def test_acceptance_matrix_passing_row_has_empty_failure_reasons(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    package = _prepare_package(tmp_path, "ShadowPriest", SHADOWPRIEST_CODE)

    matrix = build_acceptance_matrix([package])
    row = matrix["packages"][0]

    assert matrix["status"] == "passed"
    assert row["matrix_row_status"] == "passed"
    assert row["matrix_row_failure_reasons"] == []
    assert row["matrix_row_interpretation"] == (
        "Row passed matrix acceptance; detail fields remain diagnostic."
    )
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_acceptance_matrix.py::test_acceptance_matrix_status_is_authoritative_when_detail_fields_conflict tests/test_acceptance_matrix.py::test_acceptance_matrix_passing_row_has_empty_failure_reasons -q
```

Expected: fail with missing `status_authority` or missing `matrix_row_status`.

- [ ] **Step 3: Implement row-status helpers**

Modify `src/hsconfig/acceptance_matrix.py`.

Add helper functions after `build_acceptance_matrix()`:

```python
def _with_matrix_row_status(row: dict[str, Any]) -> dict[str, Any]:
    reasons = _matrix_row_failure_reasons(row)
    enriched = dict(row)
    enriched["matrix_row_status"] = "passed" if not reasons else "failed"
    enriched["matrix_row_failure_reasons"] = reasons
    enriched["matrix_row_interpretation"] = (
        "Row passed matrix acceptance; detail fields remain diagnostic."
        if not reasons
        else "Row failed matrix acceptance; inspect matrix_row_failure_reasons before detail fields."
    )
    return enriched


def _matrix_row_failure_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if row.get("technical_status") != "VALID_PACKAGE":
        reasons.append("technical_status_not_valid")
    if row.get("runtime_apply_mode") != "load_safe_apply":
        reasons.append("runtime_apply_mode_not_load_safe_apply")
    if row.get("validation_status") != "passed":
        reasons.append("validation_not_passed")
    if row.get("apply_gate_allowed") is not True:
        reasons.append("apply_gate_not_allowed")
    if int(row.get("technical_hard_block_count", 0)) > 0:
        reasons.append("technical_hard_block_present")
    return reasons
```

In `build_acceptance_matrix()`, replace:

```python
rows = [_inspect_package(Path(package_path)) for package_path in package_paths]
```

with:

```python
rows = [
    _with_matrix_row_status(_inspect_package(Path(package_path)))
    for package_path in package_paths
]
```

In the returned payload, add after `"status": status,`:

```python
"status_authority": {
    "field": "status",
    "passed_meaning": (
        "Every row is technically valid, validation passed, "
        "runtime_apply_mode is load_safe_apply, and apply_gate_allowed is true."
    ),
    "failed_meaning": (
        "At least one row failed matrix acceptance; row detail fields are diagnostic "
        "and do not override the matrix status."
    ),
    "detail_fields_are_diagnostic": True,
},
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_acceptance_matrix.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 5: Update operator docs**

In `docs/operator/README.md`, under `## Optional Acceptance Matrix`, add:

```markdown
Read `status` first. The matrix-level `status` is authoritative for the
matrix diagnostic. Row fields such as `apply_gate_allowed`,
`runtime_apply_mode`, and `validation_status` explain why a package passed or
failed, but they do not override `status` or `matrix_row_status`.
```

In `docs/operator/universal-wild-no-block-contract.md`, under `## Acceptance Matrix Diagnostic`, add:

```markdown
The matrix-level `status` is the diagnostic authority for the matrix output.
Per-row fields are intentionally verbose so a failed matrix can still show
which lower-level checks were already true. Detail fields never override
`status` or `matrix_row_status`.
```

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add src\hsconfig\acceptance_matrix.py tests\test_acceptance_matrix.py docs\operator\README.md docs\operator\universal-wild-no-block-contract.md
git commit -m "clarify hsconfig acceptance matrix status authority"
```

Expected: commit succeeds.

---

### Task 3: Supplemental Wild Visibility Decks

**Files:**
- Modify: `docs/operator/supplemental-proof-decks.json`
- Create: `tests/test_supplemental_visibility_decks.py`
- No changes to `docs/operator/archetype-fixture-matrix.json`.

**Interfaces:**
- Consumes: `hsconfig.cli.main(argv: list[str]) -> int`
- Produces: SecretMage and HighlanderPriest supplemental visibility-only rows that prove no-block load-safe prepare without widening representative source-depth closure.

**Deck Inputs:**

SecretMage source: HSGuru Secret Mage Wild deck page, deck code from page body.

```text
Deckname: SecretMage
Deckcode: AAEBAf0EAA/3Dde2Auu6Aoe9Ar6kA/SrA5HhA+efBMagBKPkBP7sBLztBP+SBduhBejoBQAA
Source: https://www.hsguru.com/deck/6999689
```

HighlanderPriest source: HSGuru Highlander Priest Wild deck page, deck code from page body.

```text
Deckname: HighlanderPriest
Deckcode: AAEBAa0GHvcTg7sCtbsC1cECkNMC/KMDlc0D184D+OMDn+sDrfcDvp8EhKMEi6ME5bAEx7IEmtQEhoMF4qQF/cQF5uQF44AG7YAGhY4Gw5wGxpwGzZ4G0Z4G054GvqIGAAABA9fOA/3EBfnbBP3EBcChBv3EBQAA
Source: https://www.hsguru.com/deck/9614974
```

- [ ] **Step 1: Write failing metadata tests**

Create `tests/test_supplemental_visibility_decks.py`:

```python
import json
from pathlib import Path

import pytest

from hsconfig.cli import main


SUPPLEMENTAL_PATH = Path("docs/operator/supplemental-proof-decks.json")


VISIBILITY_DECKS = {
    "SecretMage": {
        "deck_code": "AAEBAf0EAA/3Dde2Auu6Aoe9Ar6kA/SrA5HhA+efBMagBKPkBP7sBLztBP+SBduhBejoBQAA",
        "expected_mechanics": {"secret", "secret_timing"},
    },
    "HighlanderPriest": {
        "deck_code": "AAEBAa0GHvcTg7sCtbsC1cECkNMC/KMDlc0D184D+OMDn+sDrfcDvp8EhKMEi6ME5bAEx7IEmtQEhoMF4qQF/cQF5uQF44AG7YAGhY4Gw5wGxpwGzZ4G0Z4G054GvqIGAAABA9fOA/3EBfnbBP3EBcChBv3EBQAA",
        "expected_mechanics": {"highlander", "location", "silence", "destroy"},
    },
}


def _supplemental_decks() -> dict[str, dict]:
    payload = json.loads(SUPPLEMENTAL_PATH.read_text(encoding="utf-8"))
    return {row["deck_name"]: row for row in payload["decks"]}


def test_supplemental_visibility_decks_are_not_representative_rows():
    rows = _supplemental_decks()

    for deck_name, expected in VISIBILITY_DECKS.items():
        row = rows[deck_name]
        assert row["proof_scope"] == "supplemental_visibility_only"
        assert row["representative_output_competence"] is False
        assert row["matrix_policy"] == "not_representative_visibility_only"
        assert set(row["primary_mechanics"]) >= expected["expected_mechanics"]
        assert row["deck_code"] == expected["deck_code"]
        assert row["operator_action"] == "keep_supplemental_visibility"


@pytest.mark.parametrize("deck_name", sorted(VISIBILITY_DECKS))
def test_supplemental_visibility_deck_prepare_is_load_safe(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck_name: str,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    deck_code = VISIBILITY_DECKS[deck_name]["deck_code"]
    out = tmp_path / deck_name

    code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    deck_dirs = [path for path in (out / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["mechanic_visibility_summary"]["non_blocking"] is True
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
```

- [ ] **Step 2: Run tests and verify metadata failure**

Run:

```powershell
python -m pytest tests/test_supplemental_visibility_decks.py::test_supplemental_visibility_decks_are_not_representative_rows -q
```

Expected: fail because `SecretMage` and `HighlanderPriest` are missing.

- [ ] **Step 3: Add supplemental visibility rows**

Modify `docs/operator/supplemental-proof-decks.json`.

Append these two rows inside `decks` after `CuteWarrior`:

```json
{
  "deck_name": "SecretMage",
  "deck_code": "AAEBAf0EAA/3Dde2Auu6Aoe9Ar6kA/SrA5HhA+efBMagBKPkBP7sBLztBP+SBduhBejoBQAA",
  "source_url": "https://www.hsguru.com/deck/6999689",
  "proof_role": "supplemental_wild_visibility_prepare_proof",
  "proof_scope": "supplemental_visibility_only",
  "representative_output_competence": false,
  "primary_mechanics": ["secret", "secret_timing", "burn", "tempo"],
  "matrix_policy": "not_representative_visibility_only",
  "operator_action": "keep_supplemental_visibility",
  "known_limits": [
    "does_not_change_representative_matrix_count",
    "does_not_close_kingslayer_quick_pick_gap",
    "does_not_close_boarlock_fracking_gap",
    "secret_timing_remains_warning_only"
  ]
}
```

```json
{
  "deck_name": "HighlanderPriest",
  "deck_code": "AAEBAa0GHvcTg7sCtbsC1cECkNMC/KMDlc0D184D+OMDn+sDrfcDvp8EhKMEi6ME5bAEx7IEmtQEhoMF4qQF/cQF5uQF44AG7YAGhY4Gw5wGxpwGzZ4G0Z4G054GvqIGAAABA9fOA/3EBfnbBP3EBcChBv3EBQAA",
  "source_url": "https://www.hsguru.com/deck/9614974",
  "proof_role": "supplemental_wild_visibility_prepare_proof",
  "proof_scope": "supplemental_visibility_only",
  "representative_output_competence": false,
  "primary_mechanics": ["highlander", "location", "silence", "destroy", "hero_power_transform"],
  "matrix_policy": "not_representative_visibility_only",
  "operator_action": "keep_supplemental_visibility",
  "known_limits": [
    "does_not_change_representative_matrix_count",
    "does_not_close_kingslayer_quick_pick_gap",
    "does_not_close_boarlock_fracking_gap",
    "highlander_location_control_remains_visibility_only"
  ]
}
```

Ensure the JSON remains valid with commas in the surrounding array.

- [ ] **Step 4: Run supplemental tests**

Run:

```powershell
python -m pytest tests/test_supplemental_visibility_decks.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Verify representative matrix was not widened**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add docs\operator\supplemental-proof-decks.json tests\test_supplemental_visibility_decks.py
git commit -m "add hsconfig supplemental wild visibility decks"
```

Expected: commit succeeds.

---

### Task 4: No-Block Mechanic Documentation And Final Sync

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Optional modify: `.agents/skills/hsconfig/SKILL.md`
- Runtime write outside repo: `C:\Users\darbo\.codex\skills\hsconfig`

**Interfaces:**
- Consumes: Task 2 matrix status fields and Task 3 supplemental visibility rows.
- Produces: operator docs and installed skill aligned with the final no-block behavior.

- [ ] **Step 1: Add supplemental visibility note to operator docs**

In `docs/operator/README.md`, under `## Supplemental Proof Decks`, append:

```markdown
SecretMage and HighlanderPriest are supplemental visibility-only decks. They
prove that current Wild secret/highlander/location control surfaces still
produce load-safe packages, but they do not widen the representative matrix and
do not close Boarlock or Kingslayer source-depth stop conditions.
```

In `docs/operator/universal-wild-no-block-contract.md`, under `## Proof Matrix`, append:

```markdown
Supplemental visibility decks may broaden Wild mechanic coverage without
becoming representative source-depth rows. They must still obey the same
runtime promise: a valid package remains `load_safe_apply`, warning-only
mechanics stay descriptive, and normal output must not emit `Presume.json` or
`Concede.json`.
```

- [ ] **Step 2: Decide whether the deployed skill text needs one concise note**

Run:

```powershell
rg -n "Supplemental Proof Decks|supplemental visibility|SecretMage|HighlanderPriest" .agents\skills\hsconfig docs\operator
```

Expected before edit: operator docs mention supplemental visibility after Step 1; `.agents\skills\hsconfig` may not.

If `.agents\skills\hsconfig\SKILL.md` does not mention supplemental visibility and the docs change would otherwise be invisible to the installed skill, add this sentence under `Fixture stage meaning:`:

```markdown
Supplemental visibility decks can broaden Wild mechanic proof without becoming representative source-depth rows or changing runtime apply permission.
```

Do not add deck codes or long runbooks to `SKILL.md`.

- [ ] **Step 3: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_scope_boundaries.py tests/test_skill_sync.py tests/test_universal_wild_no_block_matrix.py tests/test_supplemental_cute_warrior_load_safe.py tests/test_supplemental_visibility_decks.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Sync installed skill after any skill text change**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 5: Commit Task 4**

If `.agents\skills\hsconfig\SKILL.md` changed:

```powershell
git add docs\operator\README.md docs\operator\universal-wild-no-block-contract.md .agents\skills\hsconfig\SKILL.md
git commit -m "document hsconfig supplemental visibility no-block policy"
```

If only docs changed:

```powershell
git add docs\operator\README.md docs\operator\universal-wild-no-block-contract.md
git commit -m "document hsconfig supplemental visibility no-block policy"
```

Expected: commit succeeds.

---

### Task 5: Final Verification And Push

**Files:**
- Verify all changed files.
- No new implementation files expected beyond Task 3 test file.

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: green test evidence, clean git status except pushed commits, and up-to-date `origin/main`.

- [ ] **Step 1: Run targeted verification**

Run:

```powershell
python -m pytest tests/test_skill_sync.py tests/test_acceptance_matrix.py tests/test_universal_wild_no_block_matrix.py tests/test_supplemental_cute_warrior_load_safe.py tests/test_supplemental_visibility_decks.py tests/test_archetype_fixture_matrix.py tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_mechanic_lowering_parity.py tests/test_config_usefulness.py tests/test_operator_summary.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full suite if targeted verification passes**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes. If it times out or fails on an unrelated pre-existing issue, capture the exact failing test and do not claim full-suite green.

- [ ] **Step 3: Verify installed skill sync one final time**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Verify no accidental HSTuner scope entered HSConfig**

Run:

```powershell
rg -n "Power\.log|HDT|hsreplay|winrate|candidate promotion|post-run tuning|analyze-step2" src tests .agents\skills\hsconfig docs\operator
```

Expected: no new HSConfig operator or skill claims that add replay parsing, HDT parsing, winrate analysis, candidate promotion, or post-run tuning to HSConfig. Existing boundary text saying those tasks belong to HSTuner is acceptable.

- [ ] **Step 5: Inspect diff**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: no whitespace errors. Branch is `main...origin/main` plus local commits if Task 2-4 committed.

- [ ] **Step 6: Push to GitHub**

Run:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review Checklist

- Spec coverage:
  - Installed skill drift is handled by Task 1 and rechecked in Task 5.
  - Acceptance matrix confusion is handled by Task 2.
  - Universal no-block promise remains intact through Task 2, Task 3, and Task 5.
  - Wild mechanic breadth is addressed through SecretMage and HighlanderPriest as supplemental visibility-only rows in Task 3.
  - Anti-bloat boundary is enforced in Global Constraints and Task 5.
- Placeholder scan:
  - No placeholder marker or unspecified implementation step is present.
  - Deck codes, file paths, commands, and expected outcomes are explicit.
- Type consistency:
  - New acceptance matrix fields are `status_authority`, `matrix_row_status`, `matrix_row_failure_reasons`, and `matrix_row_interpretation`.
  - Supplemental deck proof scope is `supplemental_visibility_only`.
  - Representative matrix remains unchanged.
