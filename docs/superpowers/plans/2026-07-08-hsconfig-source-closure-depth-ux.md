# HSConfig Source Closure And Source-Depth UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close or explicitly preserve the remaining Boarlock and Kingslayer source-informed rows, make per-card source-depth state visible, and add one full-chain CLI proof without widening HSConfig scope.

**Architecture:** Keep HSConfig as a pre-run HearthRanger VisionAI CustomConfig compiler. Treat Boarlock and Kingslayer as the only current representative source-informed closure targets, expose the first missing source/runtime link per card, and prove the documented command path from source manifest through guarded apply. Do not add replay, winrate, post-run tuning, HSTuner, Presume, or Concede behavior.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig CLI, existing JSON report builders, existing representative fixture matrix.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add dependencies.
- Do not widen `docs/operator/archetype-fixture-matrix.json`.
- Keep `CuteWarrior` in `docs/operator/supplemental-proof-decks.json`; do not promote it into the representative matrix.
- Do not invent source-backed claims for `WW_092` / `Fracking` or `DEEP_014` / `Quick Pick`.
- Do not relax `SOURCE_BACKED_STRONG` promotion gates.
- Do not add normal-path `Presume.json` or `Concede.json`.
- Do not add post-run, winrate, replay, HSTuner, or runtime-log tuning behavior to HSConfig.
- Runtime apply remains guarded by `reports/operator_summary.json`.
- Source-informed apply remains weaker than `SOURCE_BACKED_STRONG` and must stay explicit.

---

## File Structure

- Modify `src/hsconfig/source_depth_closure_index.py`
  - Add summary-level closure ordering so the operator can see `Boarlock -> Kingslayer`.
  - Keep existing per-deck closure details.

- Modify `src/hsconfig/config_readiness.py`
  - Add a derived `source_depth_lane` field to every per-card readiness row.
  - The field must be an alias over existing readiness and missing-link state, not a new promotion gate.

- Modify `src/hsconfig/source_claim_gap_report.py`
  - Thread `source_depth_lane` into card rows and the canonical `first_missing_chain`.
  - Keep priority scoring based on existing first missing links.

- Modify or add tests:
  - `tests/test_source_depth_closure_index.py`
  - `tests/test_source_informed_closure_contract.py`
  - `tests/test_config_readiness.py`
  - `tests/test_source_claim_gap_report.py`
  - `tests/test_full_chain_cli_integration.py`

- Modify docs:
  - `docs/operator/README.md`
  - `docs/operator/source-backed-strong-closure.md`

- Sync installed skill after docs changes:
  - `scripts/sync_installed_skill.py --check`
  - `scripts/sync_installed_skill.py`

---

### Task 1: Source-Informed Closure Order

**Files:**
- Modify: `src/hsconfig/source_depth_closure_index.py`
- Modify: `tests/test_source_depth_closure_index.py`
- Modify: `tests/test_boarlock_closure_wave.py`

**Interfaces:**
- Consumes: `build_source_depth_closure_index(matrix: dict[str, Any], deck_reports: dict[str, dict[str, Any]]) -> dict[str, Any]`
- Produces: `report["summary"]["next_closure_target"]`, `report["summary"]["closure_sequence"]`, and `report["summary"]["preserved_source_informed_targets"]`

- [ ] **Step 1: Write the failing source-closure summary test**

Add this test to `tests/test_source_depth_closure_index.py`:

```python
def test_index_exposes_ordered_source_informed_closure_targets():
    matrix = {
        "decks": [
            {
                "deck_name": "ShadowPriest",
                "fixture_stage": "core_source_backed_fixture",
                "strongness_visibility": {"closure_priority": 0},
            },
            {
                "deck_name": "Kingslayer",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 2,
                    "source_informed_blocking_reasons": ["unsupported_conditions_present"],
                    "operator_action": "close_existing_source_informed_fixture",
                },
            },
            {
                "deck_name": "Boarlock",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 1,
                    "source_informed_blocking_reasons": [
                        "cards_need_runtime_surface",
                        "generic_low_confidence_cards",
                    ],
                    "operator_action": "preserve_source_informed_with_explicit_stop_condition",
                    "stop_condition": "exact_boarlock_fracking_mulligan_source_unavailable",
                },
            },
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    assert report["summary"]["next_closure_target"] == "Boarlock"
    assert report["summary"]["closure_sequence"] == ["Boarlock", "Kingslayer"]
    assert report["summary"]["preserved_source_informed_targets"] == ["Boarlock"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_source_depth_closure_index.py::test_index_exposes_ordered_source_informed_closure_targets -q
```

Expected: FAIL because summary-level closure ordering is not present.

- [ ] **Step 3: Implement closure ordering**

In `src/hsconfig/source_depth_closure_index.py`, add helpers:

```python
def _closure_priority(row: dict[str, Any]) -> int:
    visibility = row.get("strongness_visibility", {})
    if not isinstance(visibility, dict):
        return 0
    try:
        return int(visibility.get("closure_priority", 0))
    except (TypeError, ValueError):
        return 0


def _source_informed_closure_sequence(rows: list[dict[str, Any]]) -> list[str]:
    targets = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("fixture_stage") == "source_informed_valid_fixture"
        and _closure_priority(row) > 0
    ]
    targets.sort(key=lambda row: (_closure_priority(row), str(row.get("deck_name", ""))))
    return [str(row["deck_name"]) for row in targets if row.get("deck_name")]


def _preserved_source_informed_targets(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        visibility = row.get("strongness_visibility", {})
        if not isinstance(visibility, dict):
            continue
        if visibility.get("operator_action") == "preserve_source_informed_with_explicit_stop_condition":
            names.append(str(row.get("deck_name", "")))
    return [name for name in names if name]
```

Then add these fields to the returned `summary`:

```python
closure_sequence = _source_informed_closure_sequence(rows)
preserved_targets = _preserved_source_informed_targets(rows)

"next_closure_target": closure_sequence[0] if closure_sequence else None,
"closure_sequence": closure_sequence,
"preserved_source_informed_targets": preserved_targets,
```

- [ ] **Step 4: Run source-closure tests**

Run:

```powershell
python -m pytest tests/test_source_depth_closure_index.py tests/test_boarlock_closure_wave.py tests/test_matrix_visibility.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/source_depth_closure_index.py tests/test_source_depth_closure_index.py tests/test_boarlock_closure_wave.py
git commit -m "feat: expose source-informed closure order"
```

---

### Task 2: Per-Card Source-Depth Lane

**Files:**
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `src/hsconfig/source_claim_gap_report.py`
- Modify: `tests/test_config_readiness.py`
- Modify: `tests/test_source_claim_gap_report.py`

**Interfaces:**
- Consumes: existing `readiness_lane` and `first_missing_link`
- Produces: `source_depth_lane: str` in `per_card_config_readiness_report.json`, `source_claim_gap_report.json`, and `summary.first_missing_chain`

- [ ] **Step 1: Write failing readiness tests**

Add these assertions to the closest existing tests in `tests/test_config_readiness.py`:

```python
def test_readiness_row_exposes_source_depth_lane_for_mulligan_gap():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Kingslayer",
            "cards": [{"card_id": "DEEP_014", "name": "Quick Pick", "count": 2}],
        },
        claim_coverage={
            "cards": {
                "DEEP_014": {
                    "coverage_status": "source_backed",
                    "source_claim_ids": ["claim_quick_pick"],
                }
            },
            "uncovered_cards": [],
        },
        gameplan_contract={
            "deck_name": "Kingslayer",
            "cards": {
                "DEEP_014": {
                    "card_id": "DEEP_014",
                    "name": "Quick Pick",
                    "roles": ["mulligan_anchor"],
                    "coverage_status": "source_backed",
                    "source_claim_ids": ["claim_quick_pick"],
                }
            },
        },
        mulligan_plan={"rules": [], "suppressed_rules": [{"card": "DEEP_014", "reason": "claim_not_runtime_lowerable"}]},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files=[],
    )

    row = report["cards"]["DEEP_014"]
    assert row["first_missing_link"] == "needs_mulligan_claim"
    assert row["source_depth_lane"] == "mulligan_claim_gap"
```

Add this generic low-confidence check near the existing generic readiness tests:

```python
def test_readiness_row_exposes_source_depth_lane_for_source_gap():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "GenericDeck",
            "cards": [{"card_id": "CARD_A", "name": "Unproven Card", "count": 2}],
        },
        claim_coverage={
            "cards": {"CARD_A": {"coverage_status": "generic_low_confidence", "source_claim_ids": []}},
            "uncovered_cards": ["CARD_A"],
        },
        gameplan_contract={
            "deck_name": "GenericDeck",
            "cards": {
                "CARD_A": {
                    "card_id": "CARD_A",
                    "name": "Unproven Card",
                    "roles": ["tempo"],
                    "coverage_status": "generic_low_confidence",
                    "source_claim_ids": [],
                }
            },
        },
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files=[],
    )

    row = report["cards"]["CARD_A"]
    assert row["first_missing_link"] == "needs_guide_claim"
    assert row["source_depth_lane"] == "source_claim_gap"
```

- [ ] **Step 2: Run readiness tests to verify failure**

Run:

```powershell
python -m pytest tests/test_config_readiness.py -q
```

Expected: FAIL because `source_depth_lane` does not exist.

- [ ] **Step 3: Add the derived lane in config readiness**

In `src/hsconfig/config_readiness.py`, add:

```python
SOURCE_DEPTH_LANE_BY_MISSING_LINK = {
    "none": "closed",
    "needs_guide_claim": "source_claim_gap",
    "needs_runtime_surface": "runtime_surface_gap",
    "needs_mulligan_claim": "mulligan_claim_gap",
    "needs_combo_sequence": "combo_sequence_gap",
    "needs_condition_lowering": "condition_lowering_gap",
    "needs_mechanic_lowering": "mechanic_lowering_gap",
}


def _source_depth_lane(first_missing_link: str) -> str:
    return SOURCE_DEPTH_LANE_BY_MISSING_LINK.get(first_missing_link, "inspect_card_gap")
```

Then add the field to each card row:

```python
"source_depth_lane": _source_depth_lane(missing),
```

- [ ] **Step 4: Thread the lane into source claim gap report**

Add this assertion to `tests/test_source_claim_gap_report.py`:

```python
def test_gap_report_threads_source_depth_lane_into_first_missing_chain():
    report = build_source_claim_gap_report(
        deck_name="Kingslayer",
        config_readiness_report={
            "cards": {
                "DEEP_014": {
                    "card_id": "DEEP_014",
                    "name": "Quick Pick",
                    "readiness_lane": "report_only_supported",
                    "source_depth_lane": "mulligan_claim_gap",
                    "first_missing_link": "needs_mulligan_claim",
                    "runtime_surfaces": [],
                }
            }
        },
        claim_coverage_report={
            "cards": {
                "DEEP_014": {
                    "coverage_status": "source_backed",
                    "source_claim_ids": ["claim_quick_pick"],
                }
            }
        },
        card_behavior_plan={"rows": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    row = report["cards"]["DEEP_014"]
    assert row["source_depth_lane"] == "mulligan_claim_gap"
    assert report["summary"]["first_missing_chain"]["source_depth_lane"] == "mulligan_claim_gap"
```

In `src/hsconfig/source_claim_gap_report.py`, add `source_depth_lane` to each row:

```python
source_depth_lane = str(row.get("source_depth_lane", _source_depth_lane_from_missing_link(missing_link)))
```

Add helper:

```python
def _source_depth_lane_from_missing_link(missing_link: str) -> str:
    return {
        "none": "closed",
        "needs_guide_claim": "source_claim_gap",
        "needs_runtime_surface": "runtime_surface_gap",
        "needs_mulligan_claim": "mulligan_claim_gap",
        "needs_combo_sequence": "combo_sequence_gap",
        "needs_condition_lowering": "condition_lowering_gap",
        "needs_mechanic_lowering": "mechanic_lowering_gap",
    }.get(missing_link, "inspect_card_gap")
```

Include it in card rows and `_first_missing_chain()` output:

```python
"source_depth_lane": source_depth_lane,
```

```python
"source_depth_lane": selected["source_depth_lane"],
```

- [ ] **Step 5: Run source-depth tests**

Run:

```powershell
python -m pytest tests/test_config_readiness.py tests/test_source_claim_gap_report.py tests/test_source_informed_closure_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/hsconfig/config_readiness.py src/hsconfig/source_claim_gap_report.py tests/test_config_readiness.py tests/test_source_claim_gap_report.py tests/test_source_informed_closure_contract.py
git commit -m "feat: expose per-card source depth lanes"
```

---

### Task 3: Boarlock And Kingslayer Closure Contract Hardening

**Files:**
- Modify: `tests/test_source_informed_closure_contract.py`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/archetype-fixture-matrix.json` only if the current visible blocker fields drift from the test expectations

**Interfaces:**
- Consumes: `prepare_fixture_deck(tmp_path, deck) -> dict[str, Any]`
- Produces: stronger regression coverage for `Boarlock` and `Kingslayer` blocked-source behavior

- [ ] **Step 1: Strengthen the target contract test**

In `tests/test_source_informed_closure_contract.py`, extend `TARGETS`:

```python
TARGETS = {
    "Boarlock": {
        "first_card_id": "WW_092",
        "first_card_name": "Fracking",
        "expected_source_depth_lane": "mulligan_claim_gap",
        "expected_stop_condition": "exact_boarlock_fracking_mulligan_source_unavailable",
        "expected_runtime_surfaces": {
            "GlobalValues.json",
            "Mulligan.json",
            "Combo.json",
        },
        "forbidden_surfaces": {"Presume.json", "Concede.json"},
    },
    "Kingslayer": {
        "first_card_id": "DEEP_014",
        "first_card_name": "Quick Pick",
        "expected_source_depth_lane": "mulligan_claim_gap",
        "expected_stop_condition": None,
        "expected_runtime_surfaces": {
            "GlobalValues.json",
            "Mulligan.json",
        },
        "forbidden_surfaces": {"Presume.json", "Concede.json", "Combo.json"},
    },
}
```

Add these assertions after `first_chain` is read:

```python
assert first_chain["source_depth_lane"] == target["expected_source_depth_lane"]
assert first_chain["recommended_source_claim_kind"] == "mulligan_keep"
```

Add matrix visibility assertions in the same test:

```python
visibility = deck["strongness_visibility"]
if target["expected_stop_condition"] is not None:
    assert visibility["stop_condition"] == target["expected_stop_condition"]
assert visibility["closure_state"] == "source_informed_blocked"
assert visibility["source_informed_apply_readiness"] == "blocked"
```

- [ ] **Step 2: Run target test**

Run:

```powershell
python -m pytest tests/test_source_informed_closure_contract.py -q
```

Expected: FAIL until Task 2 has threaded `source_depth_lane` into `first_missing_chain`; PASS after Task 2.

- [ ] **Step 3: Ensure docs match the tested closure state**

In `docs/operator/source-backed-strong-closure.md`, keep these exact meanings:

```markdown
- `Boarlock` remains source-informed with explicit stop condition `exact_boarlock_fracking_mulligan_source_unavailable` unless an exact Boarlock-relevant Fracking mulligan source is added.
- `Kingslayer` remains source-informed until `DEEP_014` / `Quick Pick` receives an exact deck-specific keep or discard source claim.
- Adjacent archetype advice is not source-backed evidence for these two rows.
```

- [ ] **Step 4: Run closure tests**

Run:

```powershell
python -m pytest tests/test_source_informed_closure_contract.py tests/test_fixture_source_depth_closure.py tests/test_matrix_visibility.py tests/test_matrix_current_truth.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
git add tests/test_source_informed_closure_contract.py docs/operator/source-backed-strong-closure.md docs/operator/archetype-fixture-matrix.json
git commit -m "test: harden source-informed closure targets"
```

---

### Task 4: Full-Chain CLI Integration Test

**Files:**
- Create: `tests/test_full_chain_cli_integration.py`
- No production code should change unless the new test exposes an actual command-chain bug.

**Interfaces:**
- Consumes: `hsconfig.cli.main(argv: list[str] | None) -> int`
- Produces: one black-box-style proof for `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply --fake -> apply`

- [ ] **Step 1: Write the full-chain test**

Create `tests/test_full_chain_cli_integration.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_documented_operator_chain_reaches_guarded_apply(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    runtime_root = tmp_path / "runtime"
    manifest_out = tmp_path / "01_manifest"
    draft_out = tmp_path / "02_draft"
    research_out = tmp_path / "03_research"
    package_out = tmp_path / "04_package"
    evidence_json = tmp_path / "source_evidence.json"

    _write_json(
        evidence_json,
        {
            "evidence_rows": [
                {
                    "source_url": "https://example.invalid/shadowpriest-guide",
                    "source_title": "ShadowPriest Guide",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-08T00:00:00Z",
                    "deck_name": "ShadowPriest",
                    "archetype": "aggro_burn_hero_power_transform",
                    "scope": "deck",
                    "claim_kind": "gameplan_posture",
                    "stance": "aggressive_burn",
                    "evidence_text_short": "ShadowPriest pressures face damage and burn.",
                    "source_confidence": "high",
                }
            ]
        },
    )

    assert main(
        [
            "source-manifest",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(manifest_out),
            "--json",
        ]
    ) == 0
    assert (manifest_out / "source_research_manifest.json").exists()

    assert main(
        [
            "draft-source-documents",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--source-evidence-json",
            str(evidence_json),
            "--out",
            str(draft_out),
            "--json",
        ]
    ) == 0
    source_documents = draft_out / "source_documents.json"
    assert source_documents.exists()

    assert main(
        [
            "research-deck",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--source-documents-json",
            str(source_documents),
            "--out",
            str(research_out),
            "--json",
        ]
    ) == 0
    guide_sources = research_out / "guide_sources.json"
    assert guide_sources.exists()

    assert main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(package_out),
            "--guide-sources-json",
            str(guide_sources),
            "--json",
        ]
    ) == 0

    operator = _read_json(package_out / "reports" / "operator_summary.json")
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert "runtime_apply_mode" in operator
    assert "generated_files" in operator

    assert main(["validate", "--package", str(package_out), "--json"]) == 0

    fake_code = main(
        [
            "apply",
            "--package",
            str(package_out),
            "--runtime-root",
            str(runtime_root),
            "--fake",
            "--json",
        ]
    )
    if operator["apply_policy"] == "ALLOWED":
        assert fake_code == 0
        assert not list(runtime_root.rglob("*.json"))
        assert main(
            [
                "apply",
                "--package",
                str(package_out),
                "--runtime-root",
                str(runtime_root),
                "--json",
            ]
        ) == 0
        assert list(runtime_root.rglob("*.json"))
    else:
        assert fake_code == 1
        assert not list(runtime_root.rglob("*.json"))
```

- [ ] **Step 2: Run the new test**

Run:

```powershell
python -m pytest tests/test_full_chain_cli_integration.py -q
```

Expected: PASS if the current documented chain is coherent. If it fails, fix only the command-chain bug shown by the failure.

- [ ] **Step 3: Run related command tests**

Run:

```powershell
python -m pytest tests/test_source_manifest_cli.py tests/test_draft_source_documents_cli.py tests/test_research_deck_cli.py tests/test_prepare_cli.py tests/test_runtime_apply.py tests/test_full_chain_cli_integration.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit Task 4**

```powershell
git add tests/test_full_chain_cli_integration.py
git commit -m "test: prove documented hsconfig cli chain"
```

---

### Task 5: Operator Docs And Installed Skill Sync

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` through `scripts/sync_installed_skill.py`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\references\workflow.md` through `scripts/sync_installed_skill.py`

**Interfaces:**
- Consumes: current docs and generated source-depth fields
- Produces: one consistent operator explanation for `source_depth_lane`, closure order, and source-informed limits

- [ ] **Step 1: Add a short source-depth lane explanation**

In `docs/operator/README.md`, add under `Report Ownership`:

```markdown
`source_depth_lane` is a readable alias for the first missing source/runtime link:
`closed`, `source_claim_gap`, `mulligan_claim_gap`, `runtime_surface_gap`,
`combo_sequence_gap`, `condition_lowering_gap`, or `mechanic_lowering_gap`.
It does not grant apply permission. Use `reports/operator_summary.json` as the gate.
```

- [ ] **Step 2: Add closure-order wording**

In `docs/operator/source-backed-strong-closure.md`, add:

```markdown
Current closure order is Boarlock first, Kingslayer second. Boarlock stays first
because it is the only representative Combo.json control row. Kingslayer follows
because its remaining gap is narrower and tied to `DEEP_014` / `Quick Pick`.
```

- [ ] **Step 3: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected: the check reports that the installed skill is in sync.

- [ ] **Step 4: Run docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_report_ownership.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```powershell
git add docs/operator/README.md docs/operator/source-backed-strong-closure.md C:/Users/darbo/.codex/skills/hsconfig/SKILL.md C:/Users/darbo/.codex/skills/hsconfig/references/workflow.md
git commit -m "docs: explain source depth lane closure"
```

If git refuses to stage files outside the repository, rerun `python scripts/sync_installed_skill.py --check` and commit only the repo-side source files that drive the installed skill sync.

---

### Task 6: Final Verification And Repo State

**Files:**
- No production edits.
- Inspect all diffs before final status.

**Interfaces:**
- Consumes: all prior tasks
- Produces: verified branch ready for user-requested Subagent-Driven execution completion

- [ ] **Step 1: Run focused closure suite**

Run:

```powershell
python -m pytest tests/test_source_depth_closure_index.py tests/test_source_informed_closure_contract.py tests/test_config_readiness.py tests/test_source_claim_gap_report.py tests/test_full_chain_cli_integration.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with the existing skipped tests only.

- [ ] **Step 3: Check installed skill sync**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected: sync check passes.

- [ ] **Step 4: Inspect diff and status**

Run:

```powershell
git diff --stat
git status --short --branch
```

Expected:

- Only intended source, tests, docs, and installed-skill sync files are changed.
- No raw runtime evidence is tracked.
- `docs/research/2026-07-08-hsconfig-skill-optimality-audit-v2/` may remain untracked unless the user explicitly wants the audit research committed.

- [ ] **Step 5: Commit final cleanup if needed**

If Task 6 required small doc or test cleanup, stage only the concrete files shown by `git status --short`. Do not use wildcard staging. A typical cleanup commit after this plan should stage only files under `src/hsconfig/`, `tests/`, `docs/operator/`, or `docs/superpowers/plans/`.

```powershell
git status --short
git commit -m "chore: verify source closure depth workflow"
```

Do not commit private runtime evidence or raw HearthRanger/HDT logs.

---

## Self-Review

- Spec coverage: The plan covers Boarlock first, Kingslayer second, source-depth lane visibility, full-chain CLI proof, docs sync, and final verification.
- Scope check: The plan keeps HSConfig pre-run only and avoids HSTuner, replay, winrate, Presume, and Concede expansion.
- Placeholder scan: No task relies on unspecified future details. Source promotion is allowed only if exact evidence exists; otherwise rows remain blocked or preserved.
- Type consistency: New fields are strings: `source_depth_lane`, `next_closure_target`; ordered target fields are string lists: `closure_sequence`, `preserved_source_informed_targets`.
- Testability: Each task has targeted pytest commands and expected outcomes.
