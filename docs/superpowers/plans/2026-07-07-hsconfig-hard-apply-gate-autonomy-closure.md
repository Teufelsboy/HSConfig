# HSConfig Hard Apply Gate And Autonomy Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's documented `operator_summary.json` gate a hard runtime apply boundary, then annotate the fixture matrix so future source-depth work targets missing decision families instead of adding broad or redundant fixtures.

**Architecture:** Keep HSConfig lean: it remains a pre-game HearthRanger `CustomConfig` generator, not a replay, HDT, winrate, or post-run tuning tool. Add a small apply-gate module that reads `reports/operator_summary.json` and decides whether `hsconfig apply` may write. Keep source-gap and promotion reports explanatory only. Add matrix metadata that states which decision family each representative deck proves.

**Tech Stack:** Python 3.11, pytest, existing `hsconfig` package, HearthRanger VisionAI JSON package validation, existing `operator_summary.json` readiness model.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning to this repo.
- Normal runtime output remains limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete exact sequence exists.
- Do not emit `Presume.json` or `Concede.json` in the normal HSConfig path.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Every deck card must remain covered in the gameplan contract.
- Strict JSON validation must remain mandatory before runtime apply.
- Row-level provenance for generated config rows must remain visible.
- `operator_summary.json` remains the single operator-facing gate.
- Lower-level reports such as `source_claim_gap_report.json` and `strong_promotion_report.json` explain the gate; they do not grant independent apply permission.
- `hsconfig apply` must fail closed unless `reports/operator_summary.json` explicitly allows runtime writes.

---

## File Structure

- Create `src/hsconfig/apply_gate.py`: reads and evaluates `reports/operator_summary.json` before runtime writes.
- Modify `src/hsconfig/cli.py`: add `hsconfig apply --allow-source-informed`, call `evaluate_apply_gate(...)` before `apply_package(...)`, and return clear JSON errors when blocked.
- Modify `tests/test_runtime_apply.py`: add CLI-level gate tests that prove runtime writes do not happen when the gate blocks.
- Modify `docs/operator/archetype-fixture-matrix.json`: add `decision_families_proven` and `known_coverage_limits` for each of the 11 decks.
- Modify `tests/test_archetype_fixture_matrix.py`: validate the new matrix fields and minimum coverage semantics.
- Modify `README.md`, `.agents/skills/hsconfig/SKILL.md`, and `.agents/skills/hsconfig/references/workflow.md`: document that `apply` now enforces the operator gate.
- Run `scripts/sync_installed_skill.py` after skill docs change.
- Keep `docs/research/2026-07-07-hsconfig-post-promotion-skill-audit/` as the evidence package for this plan; do not modify its generated result JSON files during implementation.

---

### Task 1: Hard Apply Gate Module

**Files:**
- Create: `src/hsconfig/apply_gate.py`
- Create: `tests/test_apply_gate.py`

**Interfaces:**
- Consumes: `package_root: str | Path`, `allow_source_informed: bool = False`
- Produces: `evaluate_apply_gate(package_root: str | Path, *, allow_source_informed: bool = False) -> dict[str, Any]`

- [ ] **Step 1: Write failing tests for allowed, blocked, and escape-hatch states**

Create `tests/test_apply_gate.py`:

```python
from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import write_json


def _write_operator_summary(package: Path, payload: dict) -> None:
    write_json(package / "reports" / "operator_summary.json", payload)


def test_apply_gate_allows_source_backed_ready_package(tmp_path: Path):
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

    assert gate == {
        "status": "allowed",
        "operator_summary_path": str(package / "reports" / "operator_summary.json"),
        "mode": "source_backed_strong",
        "reasons": [],
    }


def test_apply_gate_blocks_valid_but_not_guide_strong_by_default(tmp_path: Path):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 3}],
            "generated_files": ["CustomConfig\\deck\\GlobalValues.json"],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["mode"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "operator_summary_not_ready_to_apply",
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
        }
    ]


def test_apply_gate_allows_valid_source_informed_package_only_with_explicit_escape_hatch(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 2}],
            "generated_files": ["CustomConfig\\deck\\GlobalValues.json"],
        },
    )

    gate = evaluate_apply_gate(package, allow_source_informed=True)

    assert gate["status"] == "allowed"
    assert gate["mode"] == "source_informed_with_warnings"
    assert gate["reasons"] == [
        {
            "reason": "source_informed_escape_hatch_used",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
        }
    ]


def test_apply_gate_blocks_invalid_package_even_with_escape_hatch(tmp_path: Path):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "INVALID_PACKAGE",
            "semantic_status": "NEEDS_MORE_RESEARCH",
            "next_action": "FIX_PACKAGE_BEFORE_APPLY",
            "apply_policy": "BLOCKED",
            "semantic_blockers": [],
            "generated_files": [],
        },
    )

    gate = evaluate_apply_gate(package, allow_source_informed=True)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0]["reason"] == "operator_summary_not_valid_package"


@pytest.mark.parametrize("surface", ["Presume.json", "Concede.json"])
def test_apply_gate_blocks_normal_path_optional_surfaces(tmp_path: Path, surface: str):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [f"CustomConfig\\deck\\{surface}"],
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


def test_apply_gate_blocks_missing_operator_summary(tmp_path: Path):
    gate = evaluate_apply_gate(tmp_path / "package")

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "missing_operator_summary",
            "path": str(tmp_path / "package" / "reports" / "operator_summary.json"),
        }
    ]
```

- [ ] **Step 2: Run the new tests to verify failure**

Run:

```powershell
python -m pytest tests/test_apply_gate.py -q
```

Expected: failure because `hsconfig.apply_gate` does not exist.

- [ ] **Step 3: Implement `evaluate_apply_gate`**

Create `src/hsconfig/apply_gate.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.io import read_json


OPTIONAL_NORMAL_PATH_SURFACES = ("Presume.json", "Concede.json")


def evaluate_apply_gate(
    package_root: str | Path,
    *,
    allow_source_informed: bool = False,
) -> dict[str, Any]:
    package = Path(package_root)
    operator_path = package / "reports" / "operator_summary.json"
    if not operator_path.is_file():
        return _blocked(
            operator_path,
            {
                "reason": "missing_operator_summary",
                "path": str(operator_path),
            },
        )

    summary = read_json(operator_path)
    if not isinstance(summary, dict):
        return _blocked(
            operator_path,
            {
                "reason": "invalid_operator_summary",
                "path": str(operator_path),
            },
        )

    optional_surface_reasons = _optional_surface_reasons(summary)
    if optional_surface_reasons:
        return _blocked(operator_path, *optional_surface_reasons)

    technical_status = str(summary.get("technical_status", ""))
    semantic_status = str(summary.get("semantic_status", ""))
    next_action = str(summary.get("next_action", ""))
    apply_policy = str(summary.get("apply_policy", ""))

    if technical_status != "VALID_PACKAGE":
        return _blocked(
            operator_path,
            {
                "reason": "operator_summary_not_valid_package",
                "technical_status": technical_status,
                "next_action": next_action,
                "apply_policy": apply_policy,
            },
        )

    if (
        semantic_status == "SOURCE_BACKED_STRONG"
        and next_action == "READY_TO_APPLY_OR_HANDOFF"
        and apply_policy == "ALLOWED"
        and not summary.get("semantic_blockers")
    ):
        return _allowed(operator_path, mode="source_backed_strong", reasons=[])

    if (
        allow_source_informed
        and semantic_status in {"VALID_BUT_NOT_GUIDE_STRONG", "STATIC_SEMANTICS_USABLE"}
        and apply_policy == "ALLOWED_WITH_WARNINGS"
        and next_action in {
            "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "READY_WITH_WARNINGS",
            "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG",
        }
    ):
        return _allowed(
            operator_path,
            mode="source_informed_with_warnings",
            reasons=[
                {
                    "reason": "source_informed_escape_hatch_used",
                    "semantic_status": semantic_status,
                    "next_action": next_action,
                    "apply_policy": apply_policy,
                }
            ],
        )

    return _blocked(
        operator_path,
        {
            "reason": "operator_summary_not_ready_to_apply",
            "technical_status": technical_status,
            "semantic_status": semantic_status,
            "next_action": next_action,
            "apply_policy": apply_policy,
        },
    )


def _optional_surface_reasons(summary: dict[str, Any]) -> list[dict[str, str]]:
    generated = summary.get("generated_files", [])
    if not isinstance(generated, list):
        return []
    reasons: list[dict[str, str]] = []
    for item in generated:
        generated_file = str(item)
        if generated_file.endswith(OPTIONAL_NORMAL_PATH_SURFACES):
            reasons.append(
                {
                    "reason": "normal_path_optional_surface_present",
                    "generated_file": generated_file,
                }
            )
    return reasons


def _allowed(
    operator_path: Path,
    *,
    mode: str,
    reasons: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "allowed",
        "operator_summary_path": str(operator_path),
        "mode": mode,
        "reasons": reasons,
    }


def _blocked(operator_path: Path, *reasons: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "operator_summary_path": str(operator_path),
        "mode": "blocked",
        "reasons": list(reasons),
    }
```

- [ ] **Step 4: Run the tests to verify pass**

Run:

```powershell
python -m pytest tests/test_apply_gate.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run adjacent report tests**

Run:

```powershell
python -m pytest tests/test_apply_gate.py tests/test_strong_promotion_report.py tests/test_operator_summary.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/apply_gate.py tests/test_apply_gate.py
git commit -m "feat: add operator apply gate"
```

---

### Task 2: Enforce Apply Gate In CLI

**Files:**
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_runtime_apply.py`

**Interfaces:**
- Consumes: `evaluate_apply_gate(package_root, allow_source_informed=False)`
- Produces: `hsconfig apply --allow-source-informed`

- [ ] **Step 1: Add failing CLI tests for blocked default apply**

Append to `tests/test_runtime_apply.py`:

```python
def _complete_package(tmp_path: Path, *, semantic_status: str, next_action: str, apply_policy: str):
    package = tmp_path / "package"
    deck = package / "CustomConfig" / "deck"
    write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues", "ConfigComment": "new"})
    write_json(
        deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(package / "reports" / "globalvalues_baseline.json", {"values": {}})
    write_json(package / "reports" / "globalvalues_profile.json", {"source": "test"})
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Gate Deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": semantic_status,
            "next_action": next_action,
            "apply_policy": apply_policy,
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 1}]
            if semantic_status != "SOURCE_BACKED_STRONG"
            else [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )
    return package


def test_apply_cli_blocks_valid_but_not_guide_strong_package_by_default(
    tmp_path: Path, capsys
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
        apply_policy="ALLOWED_WITH_WARNINGS",
    )
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "blocked"
    assert payload["apply_gate"]["status"] == "blocked"
    assert payload["apply_gate"]["reasons"][0]["reason"] == "operator_summary_not_ready_to_apply"
    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_cli_allows_valid_but_not_guide_strong_only_with_explicit_escape_hatch(
    tmp_path: Path, capsys
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
        apply_policy="ALLOWED_WITH_WARNINGS",
    )
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--allow-source-informed",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["apply_gate"]["mode"] == "source_informed_with_warnings"
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()


def test_apply_cli_blocks_missing_operator_summary(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = tmp_path / "package"
    deck = package / "CustomConfig" / "deck"
    write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues", "ConfigComment": "new"})
    write_json(
        deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(package / "reports" / "globalvalues_baseline.json", {"values": {}})
    write_json(package / "reports" / "globalvalues_profile.json", {"source": "test"})

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "blocked"
    assert payload["apply_gate"]["reasons"][0]["reason"] == "missing_operator_summary"
```

- [ ] **Step 2: Update existing built-package apply test expectation**

Modify `test_apply_cli_returns_json_status_for_built_package` in `tests/test_runtime_apply.py` so it writes an allowed operator summary after `build` and before `apply`:

```python
    generated_files = [
        str(path.relative_to(package)).replace("/", "\\")
        for path in sorted((package / "CustomConfig" / "apply_deck").glob("*.json"))
    ]
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": generated_files,
        },
    )
```

- [ ] **Step 3: Run runtime apply tests to verify failure**

Run:

```powershell
python -m pytest tests/test_runtime_apply.py -q
```

Expected: new tests fail because the CLI does not have `--allow-source-informed` and does not call the apply gate.

- [ ] **Step 4: Add CLI argument and gate call**

Modify imports in `src/hsconfig/cli.py`:

```python
from hsconfig.apply_gate import evaluate_apply_gate
```

Modify `_build_parser()` apply parser:

```python
    apply = subparsers.add_parser("apply")
    apply.add_argument("--package", required=True)
    apply.add_argument("--runtime-root", required=True)
    apply.add_argument("--allow-source-informed", action="store_true")
    apply.add_argument("--json", action="store_true")
```

Modify `_apply(args)` after validation passes and before `apply_package(...)`:

```python
    apply_gate = evaluate_apply_gate(
        package,
        allow_source_informed=bool(getattr(args, "allow_source_informed", False)),
    )
    if apply_gate["status"] != "allowed":
        return {
            "status": "blocked",
            "errors": ["Operator summary does not allow runtime apply."],
            "validation_report": report,
            "apply_gate": apply_gate,
        }, 1

    receipt = apply_package(package_root=package, runtime_root=args.runtime_root)
    return {"status": "applied", "apply_gate": apply_gate, "receipt": receipt}, 0
```

- [ ] **Step 5: Run runtime apply tests to verify pass**

Run:

```powershell
python -m pytest tests/test_runtime_apply.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Run adjacent CLI tests**

Run:

```powershell
python -m pytest tests/test_runtime_apply.py tests/test_cli.py tests/test_prepare_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_runtime_apply.py
git commit -m "feat: enforce operator summary on apply"
```

---

### Task 3: Matrix Decision-Family Annotation

**Files:**
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `tests/test_archetype_fixture_matrix.py`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**
- Consumes: existing matrix rows with `deck_name`, `archetype_bucket`, `primary_mechanics`, and `fixture_stage`
- Produces: each row has `decision_families_proven: list[str]` and `known_coverage_limits: list[str]`

- [ ] **Step 1: Add failing matrix-field test**

Append to `tests/test_archetype_fixture_matrix.py`:

```python
def test_each_fixture_row_documents_decision_family_and_limits():
    matrix = _load_matrix()

    expected_families = {
        "ShadowPriest": {"aggro_burn_targeting", "hero_power_transform"},
        "CtAPaladin": {"recruit_board_flood", "aura_pressure"},
        "PirateRogue": {"pirate_tempo", "weapon_pressure"},
        "BigShaman": {"big_minion_cheat", "recruit", "deathrattle"},
        "Discolock": {"discard_payoff", "hand_mutation"},
        "TreantDruid": {"token_board", "board_buff"},
        "ImbueMage": {"hero_power", "spell_generation"},
        "MechPala": {"mech_board_scaling", "magnetic"},
        "Kingslayer": {"weapon_sequence", "attack_pressure"},
        "Boarlock": {"combo_control", "resource_setup"},
        "PirateDH": {"pirate_tempo", "hero_attack"},
    }

    for deck in matrix["decks"]:
        deck_name = deck["deck_name"]
        families = set(deck.get("decision_families_proven", []))
        assert families >= expected_families[deck_name]
        assert deck.get("known_coverage_limits"), deck_name
        assert all(isinstance(item, str) and item for item in deck["known_coverage_limits"])
```

If `_load_matrix()` does not exist, use the local helper already present in the file. If no helper exists, add:

```python
def _load_matrix():
    return json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run matrix test to verify failure**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py::test_each_fixture_row_documents_decision_family_and_limits -q
```

Expected: failure because matrix rows do not contain the new fields.

- [ ] **Step 3: Add `decision_families_proven` and `known_coverage_limits` to each matrix row**

Modify `docs/operator/archetype-fixture-matrix.json` rows with these exact values:

```json
"decision_families_proven": ["aggro_burn_targeting", "hero_power_transform"],
"known_coverage_limits": ["does_not_cover_reactive_control", "does_not_cover_discover_chains"]
```

for `ShadowPriest`.

```json
"decision_families_proven": ["recruit_board_flood", "aura_pressure"],
"known_coverage_limits": ["still_source_informed_not_strong", "does_not_cover_reactive_control"]
```

for `CtAPaladin`.

```json
"decision_families_proven": ["pirate_tempo", "weapon_pressure"],
"known_coverage_limits": ["does_not_cover_reactive_control", "does_not_cover_exact_combo"]
```

for `PirateRogue`.

```json
"decision_families_proven": ["big_minion_cheat", "recruit", "deathrattle"],
"known_coverage_limits": ["does_not_cover_discover_chains", "does_not_cover_reactive_control"]
```

for `BigShaman`.

```json
"decision_families_proven": ["discard_payoff", "hand_mutation"],
"known_coverage_limits": ["still_source_informed_not_strong", "does_not_cover_exact_combo"]
```

for `Discolock`.

```json
"decision_families_proven": ["token_board", "board_buff"],
"known_coverage_limits": ["still_source_informed_not_strong", "does_not_cover_single_target_removal"]
```

for `TreantDruid`.

```json
"decision_families_proven": ["hero_power", "spell_generation"],
"known_coverage_limits": ["still_source_informed_not_strong", "does_not_cover_discover_chains"]
```

for `ImbueMage`.

```json
"decision_families_proven": ["mech_board_scaling", "magnetic"],
"known_coverage_limits": ["does_not_cover_reactive_control", "does_not_cover_exact_combo"]
```

for `MechPala`.

```json
"decision_families_proven": ["weapon_sequence", "attack_pressure"],
"known_coverage_limits": ["still_source_informed_not_strong", "does_not_cover_reactive_control"]
```

for `Kingslayer`.

```json
"decision_families_proven": ["combo_control", "resource_setup"],
"known_coverage_limits": ["still_source_informed_not_strong", "single_combo_fixture_only"]
```

for `Boarlock`.

```json
"decision_families_proven": ["pirate_tempo", "hero_attack"],
"known_coverage_limits": ["still_source_informed_not_strong", "does_not_cover_reactive_control"]
```

for `PirateDH`.

- [ ] **Step 4: Update closure doc with fixture coverage language**

In `docs/operator/source-backed-strong-closure.md`, add this paragraph after the fixture stage definitions:

```markdown
The fixture matrix also documents `decision_families_proven` and `known_coverage_limits`. These fields describe what a fixture proves for HSConfig's pre-game config compiler. They are not gameplay-quality claims and they do not imply post-run optimization coverage.
```

- [ ] **Step 5: Run matrix and fixture tests**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py tests/test_fixture_stage_semantics.py tests/test_strong_fixture_closure.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md tests/test_archetype_fixture_matrix.py
git commit -m "docs: annotate fixture decision coverage"
```

---

### Task 4: Operator Docs And Skill Sync For Apply Gate

**Files:**
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Run: `scripts/sync_installed_skill.py`

**Interfaces:**
- Consumes: CLI behavior from Task 2: `hsconfig apply --allow-source-informed`
- Produces: synchronized installed skill at `C:\Users\darbo\.codex\skills\hsconfig`

- [ ] **Step 1: Update README apply paragraph**

In `README.md`, replace:

```markdown
Run `apply` only when the user or task requests runtime writes and `operator_summary.json` allows it through `next_action` and `apply_policy`.
```

with:

```markdown
Run `apply` only when runtime writes are intended. The command enforces `reports/operator_summary.json`: by default it writes only when `technical_status=VALID_PACKAGE`, `semantic_status=SOURCE_BACKED_STRONG`, `next_action=READY_TO_APPLY_OR_HANDOFF`, and `apply_policy=ALLOWED`. Use `--allow-source-informed` only when intentionally applying a valid package that still needs more guide depth.
```

- [ ] **Step 2: Update skill workflow step 7**

In `.agents/skills/hsconfig/SKILL.md`, replace workflow step 7 with:

```markdown
7. Run `hsconfig apply ...` only when runtime writes are intended. The CLI enforces `reports/operator_summary.json` and fails closed unless the package is source-backed ready; use `--allow-source-informed` only for an intentional valid-but-not-strong handoff.
```

- [ ] **Step 3: Update workflow reference apply paragraph**

In `.agents/skills/hsconfig/references/workflow.md`, replace the final apply sentence with:

```markdown
Use `hsconfig validate` before handoff or apply. Use `hsconfig apply` only when runtime writes are intended; it enforces `reports/operator_summary.json` and blocks by default unless the package is source-backed ready. Use `--allow-source-informed` only for intentional valid-but-not-strong packages.
```

- [ ] **Step 4: Update guide research policy boundary**

In `.agents/skills/hsconfig/references/guide-research-policy.md`, add after the paragraph that says not to infer replay performance:

```markdown
`hsconfig apply` enforces this boundary. A valid package that is not `SOURCE_BACKED_STRONG` requires the explicit `--allow-source-informed` flag before runtime files are written.
```

- [ ] **Step 5: Sync installed skill and run skill tests**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
python -m pytest tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

and all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/references/guide-research-policy.md
git commit -m "docs: document enforced apply gate"
```

If Git refuses to stage the installed skill path because it is outside the repository, stage only repo files and confirm `scripts\sync_installed_skill.py --check` passed.

---

### Task 5: Source Autonomy Follow-Up Contract

**Files:**
- Create: `docs/operator/autonomous-source-builder-next.md`
- Modify: `docs/operator/guide-research-policy.md`

**Interfaces:**
- Consumes: `source_claim_gap_report.json`, `strong_promotion_report.json`, `docs/research/2026-07-07-hsconfig-post-promotion-skill-audit/results/*.json`
- Produces: a documented next-wave contract for source acquisition; no new web scraper, no new runtime behavior

- [ ] **Step 1: Create the next-wave source autonomy doc**

Create `docs/operator/autonomous-source-builder-next.md`:

```markdown
# Autonomous Source Builder Next Wave

HSConfig can already build a valid initial package from deck input. It reaches `SOURCE_BACKED_STRONG` when current structured guide sources provide enough card-specific, runtime-lowerable claims.

The next autonomy improvement is not another runtime surface. It is stronger source acquisition before `research-deck` and `prepare`.

## Input

- deck name
- deck code
- optional HS deck id
- optional HDT deck id

## Required Output

The source builder must emit `source_documents.json` with:

- `card_role` claims for every deck card that would otherwise be `generic_low_confidence`
- `mulligan_keep` or explicit non-keep evidence for mulligan anchors
- `targeting_rule` claims for cards whose expected target can be source-backed
- `mechanic_usage` claims only when the mechanic and runtime block are documented and source-supported
- `combo_sequence` claims only for exact sequence evidence
- `globalvalue_*` claims only when they are pre-game posture claims, not runtime performance tuning

## Fail-Closed Rules

- Do not infer gameplay improvement.
- Do not infer replay, winrate, or post-run tuning.
- Do not lower vague guide text into runtime config.
- Do not emit normal-path `Presume.json` or `Concede.json`.
- Keep unsupported claims visible in reports rather than silently applying them.

## Success Criteria

- `hsconfig research-deck` consumes the generated source documents without schema errors.
- `hsconfig prepare` produces `VALID_PACKAGE`.
- `source_claim_gap_report.json` has fewer blocked cards than deck-only static semantics.
- `strong_promotion_report.json` explains whether the package is ready or which card/source link is missing first.
```

- [ ] **Step 2: Link from guide research policy**

Append to `docs/operator/guide-research-policy.md`:

```markdown
## Next-Wave Source Autonomy

See `docs/operator/autonomous-source-builder-next.md` for the source-acquisition contract that should feed `research-deck` before future deck-only autonomy work. This document is intentionally a contract, not an implementation of web browsing or scraping.
```

- [ ] **Step 3: Run docs scan tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_research_audit_schema.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```powershell
git add docs/operator/autonomous-source-builder-next.md docs/operator/guide-research-policy.md
git commit -m "docs: define autonomous source builder contract"
```

---

### Task 6: Verification And GitHub Update

**Files:**
- Verify only unless a previous task introduced a failure.

**Interfaces:**
- Consumes: all previous tasks
- Produces: green local verification, synced installed skill, clean git status, pushed `origin/main`

- [ ] **Step 1: Run focused gate and docs tests**

Run:

```powershell
python -m pytest tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_archetype_fixture_matrix.py tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run 11-deck fixture coverage tests**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_e2e.py tests/test_strong_fixture_closure.py tests/test_depth_matrix_e2e.py -q
```

Expected: all tests pass or preserve existing intentional skips.

- [ ] **Step 3: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 4: Verify installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 5: Check git hygiene**

Run:

```powershell
git status --short --branch
git ls-files .superpowers
```

Expected:

```text
## main...origin/main [ahead N]
```

and no tracked `.superpowers` files.

- [ ] **Step 6: Push main**

Run:

```powershell
git push origin main
```

Expected:

```text
main -> main
```

---

## Self-Review

- Spec coverage: The plan covers the audited top gap (`hsconfig apply` does not enforce `operator_summary.json`), the matrix-annotation recommendation, docs/skill sync, and a bounded next-wave source-autonomy contract.
- Scope check: The plan deliberately does not implement a live web guide-source builder. That is a separate larger wave after hard apply gating is true.
- Placeholder scan: No `TBD`, `TODO`, or "write tests for the above" placeholders remain.
- Type consistency: `evaluate_apply_gate(package_root: str | Path, *, allow_source_informed: bool = False) -> dict[str, Any]` is defined in Task 1 and consumed by Task 2.
- Boundary check: No replay, HDT, winrate, candidate promotion, post-run tuning, normal-path `Presume.json`, or normal-path `Concede.json` is added.
