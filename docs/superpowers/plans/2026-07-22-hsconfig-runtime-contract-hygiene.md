# HSConfig Runtime Contract Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten HSConfig's source/contract/runtime hygiene with four narrow fixes: token-safe intent matching, one shared modern-mechanic visibility source, report-only suppression precedence, and lean runtime JSON checks for special normal surfaces.

**Architecture:** Keep `hsconfig configure` and existing report builders as the normal path. The change is diagnostic and lint-oriented: it improves what the existing contract reports can prove, without adding gameplay sequencing, HSTuner, replay parsing, a second apply authority, or new runtime surfaces. `reports/operator_summary.json` remains the only normal runtime apply authority, and all source/status diagnostics stay non-blocking.

**Tech Stack:** Python 3, pytest, existing HSConfig modules under `src/hsconfig`, existing CLI checks and skill-sync scripts.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before implementation, run:

```powershell
git fetch --all --prune --tags
git remote prune origin
python scripts\check_hsconfig_currentness.py --cwd . --json
```

- Start and finish from a clean worktree; no dirty state may remain after commits.
- Do not create backups, temp checkouts, generated runtime output commits, or shadow workspaces.
- Do not inspect gameplay logs for this plan.
- Do not use or propose HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-game tuning.
- Do not add gameplay sequencing logic such as attack order, spell order, location activation order, lethal calculation, or turn planning.
- Do not add a new runtime surface. Normal output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for complete source-backed combo claims.
- Do not change `hsconfig apply`, runtime writer semantics, or runtime receipts.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG`, source status, config quality, mechanic visibility, config intent, and semantic intent remain diagnostic labels, not apply gates.
- `source_status_apply_blocking` must remain `false` for source-quality gaps.
- The output must stay useful for any Wild deck: report unsupported or report-only mechanics visibly, but never block package creation just because a deck contains an unmapped or modern mechanic.

---

## File Structure

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_intent_taxonomy.py`
  - Make only natural-language phrase probes token-aware where substring collisions matter.

- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_card_intent_taxonomy.py`
  - Add a false-positive regression for `surface` containing `face`.
  - Keep phrase-level positive coverage for real face/enemy-hero burn signals.

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\static_semantics.py`
  - Reuse `mechanic_drift.TEXT_MECHANIC_PATTERNS` as the primary modern-mechanic text registry.
  - Use `mechanic_report_only_reason()` to compute warning-only families instead of relying only on a local partial set.

- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_static_semantics.py`
  - Add coverage proving modern mechanics from drift visibility are also seen by static semantics.

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_behavior_surface_router.py`
  - Route report-only mechanic policies before explicit-runtime-block requirements.
  - Keep explicit-block requirements only for lowerable partial mechanics that are unsafe to lower generically.

- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_card_behavior_router.py`
  - Add coverage for `generic_spell_target` suppression reason and ensure no runtime row is emitted.

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`
  - Extend metadata-leak checking to `GlobalValues.json`, `Mulligan.json`, and `Combo.json` with surface-specific allowed runtime row keys.

- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`
  - Add clean and attention coverage for special runtime surface metadata linting.

- Optionally modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Only if wording must be updated after implementation; keep this small and covered by existing skill sync tests.

- Optionally modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
  - Only if wording must be mirrored after implementation.

---

### Task 0: Preflight Currentness And Boundaries

**Files:**
- No source edits.

**Interfaces:**
- Consumes: Git remote state, current worktree state, current HSConfig contract checks.
- Produces: evidence that implementation starts from current, clean local state.

- [ ] **Step 1: Fetch and prune remotes**

Run:

```powershell
git fetch --all --prune --tags
git remote prune origin
```

Expected: commands complete without errors.

- [ ] **Step 2: Confirm currentness**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected JSON fields:

```json
{
  "dirty": false,
  "behind_origin_main": 0,
  "clean_for_runtime_work": true
}
```

If `dirty` is true, stop implementation and inspect with:

```powershell
git status --short
```

Do not overwrite unrelated user changes. If the dirty files are generated caches or test artifacts from this task, remove only those generated files after confirming their path.

- [ ] **Step 3: Confirm current contract baseline**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected:

```json
{
  "status": "PASS",
  "source_status_apply_blocking": false,
  "runtime_apply_authority": "reports/operator_summary.json"
}
```

---

### Task 1: Token-Safe Card Intent Matching

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_card_intent_taxonomy.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_intent_taxonomy.py`

**Interfaces:**
- Consumes: `classify_card_intent(text: str, *, value_default: str = "6")`.
- Preserves: `CardIntentClassification(reason, value, band, matched_signals)`.
- Produces: direct burn classification only when `face`, `enemy hero`, `hero damage`, or `prefer_enemy_hero` appear as real tokens/phrases, not as substrings inside other words.

- [ ] **Step 1: Add the false-positive regression test**

Append this test to `tests/test_card_intent_taxonomy.py`:

```python
def test_direct_burn_does_not_match_face_inside_surface_word():
    classification = classify_card_intent(
        "Card behavior surface damage row without targeting guidance."
    )

    assert classification.reason == "semantic_default"
    assert classification.value == "6"
    assert classification.band == "default"
```

This currently protects against the exact bad match where `surface` contains the substring `face` and the same text contains `damage`.

- [ ] **Step 2: Add positive phrase coverage**

Append this test to `tests/test_card_intent_taxonomy.py`:

```python
def test_direct_burn_still_matches_real_enemy_hero_and_face_phrases():
    for text in (
        "Prefer enemy hero face damage burn.",
        "prefer_enemy_hero damage plan",
        "Deal hero damage directly.",
        "Send face damage now.",
    ):
        classification = classify_card_intent(text)
        assert classification.reason == "direct_enemy_hero_burn"
        assert classification.value == "12"
        assert classification.band == "critical"
```

- [ ] **Step 3: Run focused taxonomy tests and confirm the regression fails first**

Run:

```powershell
python -m pytest tests\test_card_intent_taxonomy.py::test_direct_burn_does_not_match_face_inside_surface_word tests\test_card_intent_taxonomy.py::test_direct_burn_still_matches_real_enemy_hero_and_face_phrases -q -p no:cacheprovider
```

Expected before implementation: the false-positive test fails with `direct_enemy_hero_burn`.

- [ ] **Step 4: Add token-aware phrase helper**

In `src/hsconfig/card_intent_taxonomy.py`, add this helper after `_has_any()`:

```python
def _has_phrase_or_token(text: str, needle: str) -> bool:
    if "_" in needle or " " in needle:
        return needle in text
    return _has_token(text, needle)
```

Then change `_has_direct_enemy_hero_burn()` to:

```python
def _has_direct_enemy_hero_burn(text: str) -> bool:
    return any(
        _has_phrase_or_token(text, needle)
        for needle in ("prefer_enemy_hero", "enemy hero", "face", "hero damage")
    ) and _has_damage_wording(text)
```

Keep `_has_any()` unchanged for broad lexical categories where substring matching is already intentional.

- [ ] **Step 5: Run taxonomy tests**

Run:

```powershell
python -m pytest tests\test_card_intent_taxonomy.py -q -p no:cacheprovider
```

Expected: all taxonomy tests pass.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add src\hsconfig\card_intent_taxonomy.py tests\test_card_intent_taxonomy.py
git commit -m "fix: make direct burn intent token safe"
```

Expected: commit succeeds and does not stage unrelated files.

---

### Task 2: Share Modern Mechanic Text Visibility

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_static_semantics.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\static_semantics.py`

**Interfaces:**
- Consumes: `infer_static_semantics(card: Mapping[str, Any]) -> dict[str, Any]`.
- Consumes: `TEXT_MECHANIC_PATTERNS` from `hsconfig.mechanic_drift`.
- Consumes: `mechanic_report_only_reason(mechanic: str) -> str`.
- Produces: static semantic families that are aligned with the drift scanner's modern text registry.
- Guarantees: warning-only status is derived from registered lowering policy where possible and remains diagnostic-only.

- [ ] **Step 1: Add drift-registry coverage to static semantics tests**

Append this test to `tests/test_static_semantics.py`:

```python
def test_static_semantics_uses_drift_text_registry_for_modern_mechanics():
    result = infer_static_semantics(
        {
            "id": "MODERN_001",
            "type": "SPELL",
            "text": (
                "Rewind. Prepare. Miniaturize. Honorable Kill. "
                "Elusive. Poisonous. Kindred."
            ),
        }
    )

    families = set(result["families"])
    assert {
        "rewind",
        "prepare",
        "miniaturize",
        "honorable_kill",
        "elusive",
        "poisonous",
        "kindred",
    } <= families
    assert {"rewind", "prepare", "kindred"} <= set(result["warning_only"])
```

- [ ] **Step 2: Run focused static-semantics test and confirm it fails**

Run:

```powershell
python -m pytest tests\test_static_semantics.py::test_static_semantics_uses_drift_text_registry_for_modern_mechanics -q -p no:cacheprovider
```

Expected before implementation: at least one of `rewind`, `prepare`, `miniaturize`, `honorable_kill`, `elusive`, `poisonous`, or `kindred` is missing from `families`.

- [ ] **Step 3: Import the drift text registry**

In `src/hsconfig/static_semantics.py`, add this import:

```python
from hsconfig.mechanic_drift import TEXT_MECHANIC_PATTERNS as DRIFT_TEXT_MECHANIC_PATTERNS
```

Keep the existing `mechanic_report_only_reason` import from `hsconfig.mechanic_support`.

- [ ] **Step 4: Add merged text-pattern helper**

Add this helper after `SOURCE_TYPE`:

```python
def _text_patterns() -> dict[str, tuple[str, ...]]:
    merged = {
        family: tuple(patterns)
        for family, patterns in DRIFT_TEXT_MECHANIC_PATTERNS.items()
    }
    for family, patterns in TEXT_PATTERNS.items():
        merged[family] = tuple(dict.fromkeys((*merged.get(family, ()), *patterns)))
    return merged
```

- [ ] **Step 5: Route text matching through the merged registry**

In `infer_static_semantics()`, replace:

```python
    for family, patterns in TEXT_PATTERNS.items():
```

with:

```python
    for family, patterns in _text_patterns().items():
```

Keep `MODERN_WARNING_ONLY_KEYWORDS` for backward-compatible explicit keyword handling during this task; it becomes redundant but harmless.

- [ ] **Step 6: Derive warning-only from lowering policy**

Add this helper near the other local semantic helpers:

```python
def _is_warning_only_family(family: str) -> bool:
    return family in WARNING_ONLY_MECHANICS or bool(mechanic_report_only_reason(family))
```

Then replace the return field:

```python
        "warning_only": sorted(families & WARNING_ONLY_MECHANICS),
```

with:

```python
        "warning_only": sorted(
            family for family in families if _is_warning_only_family(family)
        ),
```

- [ ] **Step 7: Run static semantics tests**

Run:

```powershell
python -m pytest tests\test_static_semantics.py -q -p no:cacheprovider
```

Expected: all static semantics tests pass.

- [ ] **Step 8: Run drift/semantics adjacent tests**

Run:

```powershell
python -m pytest tests\test_static_semantics.py tests\test_mechanic_drift.py tests\test_mechanic_support.py -q -p no:cacheprovider
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 2**

Run:

```powershell
git add src\hsconfig\static_semantics.py tests\test_static_semantics.py
git commit -m "fix: align static semantics with mechanic drift registry"
```

Expected: commit succeeds and does not stage unrelated files.

---

### Task 3: Prefer Report-Only Policy Suppression

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_card_behavior_router.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_behavior_surface_router.py`

**Interfaces:**
- Consumes: `route_card_behavior_surfaces(claims: list[dict[str, Any]], identity_links: dict[str, Any] | None = None) -> dict[str, Any]`.
- Consumes: `mechanic_lowering_policy("generic_spell_target")`.
- Produces: report-only mechanics always suppress with their registered report-only reason before any explicit-runtime-block requirement is considered.
- Guarantees: no `generic_spell_target` row is emitted without documented card-specific target support.

- [ ] **Step 1: Add report-only precedence regression**

Append this test near the other report-only router tests in `tests/test_card_behavior_router.py`:

```python
def test_generic_spell_target_uses_report_only_policy_reason_before_explicit_block_requirement():
    result = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_generic_spell_target",
                "claim_kind": "mechanic_usage",
                "cards": ["SPELL_TARGET_001"],
                "mechanic": "generic_spell_target",
                "claim_readiness": "source_backed_static_semantics",
            }
        ]
    )

    assert result["rows"] == []
    assert result["suppressed"] == [
        {
            "claim_id": "claim_generic_spell_target",
            "claim_kind": "mechanic_usage",
            "cards": ["SPELL_TARGET_001"],
            "reason": "generic_spell_target_has_no_documented_runtime_block",
            "mechanic": "generic_spell_target",
            "lowering_policy": "report_only",
        }
    ]
```

- [ ] **Step 2: Run focused router test and confirm it fails**

Run:

```powershell
python -m pytest tests\test_card_behavior_router.py::test_generic_spell_target_uses_report_only_policy_reason_before_explicit_block_requirement -q -p no:cacheprovider
```

Expected before implementation: failure because the current reason is `generic_spell_target_requires_explicit_runtime_block`.

- [ ] **Step 3: Move report-only suppression before explicit-block requirement**

In `src/hsconfig/card_behavior_surface_router.py`, inside the `if claim_kind == "mechanic_usage":` block, move the full `if policy_name == "report_only":` branch above:

```python
            if mechanic in MECHANIC_USAGE_REQUIRES_EXPLICIT_RUNTIME_BLOCK and explicit_block is None:
```

The new order must be:

```python
            policy = mechanic_lowering_policy(mechanic)
            policy_name = str(policy["policy"])
            if policy_name == "report_only":
                reason = (
                    "requires_supported_cardid_surface"
                    if mechanic == "generated_entity_random_pool"
                    else str(policy["suppression_reason"])
                )
                suppressed.append(
                    {
                        **_suppressed_row(
                            claim,
                            claim_kind,
                            cards,
                            reason,
                        ),
                        "mechanic": mechanic,
                        "lowering_policy": policy_name,
                    }
                )
                continue
            if mechanic in MECHANIC_USAGE_REQUIRES_EXPLICIT_RUNTIME_BLOCK and explicit_block is None:
                ...
```

Do not remove `MECHANIC_USAGE_REQUIRES_EXPLICIT_RUNTIME_BLOCK`; it is still useful for lowerable partial mechanics such as `destroy`, `hero_power`, `silence`, and `transform`.

- [ ] **Step 4: Run focused router test**

Run:

```powershell
python -m pytest tests\test_card_behavior_router.py::test_generic_spell_target_uses_report_only_policy_reason_before_explicit_block_requirement -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 5: Run card behavior router suite**

Run:

```powershell
python -m pytest tests\test_card_behavior_router.py -q -p no:cacheprovider
```

Expected: all router tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add src\hsconfig\card_behavior_surface_router.py tests\test_card_behavior_router.py
git commit -m "fix: prefer report-only mechanic suppression reasons"
```

Expected: commit succeeds and does not stage unrelated files.

---

### Task 4: Lint Special Runtime Surface Rows For Metadata Leaks

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`

**Interfaces:**
- Consumes: `build_config_quality_report(package: str | Path) -> dict[str, Any]`.
- Produces: `report["checks"]["runtime_json"]["metadata_leaks"]` for extra row keys in `GlobalValues.json`, `Mulligan.json`, `Combo.json`, and per-card runtime JSON.
- Guarantees: metadata leak findings remain diagnostic-only; `report["apply_blocking"]` stays `False`.

- [ ] **Step 1: Add clean special-surface coverage**

In `tests/test_config_quality_contract.py`, append:

```python
def test_config_quality_allows_lean_special_runtime_surfaces(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "DeckStrategy": {
                "values": [
                    {
                        "comment": "ShadowPriest: pressure posture",
                        "condition": "*",
                        "value": "9",
                    }
                ]
            },
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "Mulligan": {
                "values": [
                    {
                        "comment": "ShadowPriest: keep one-drop pressure",
                        "condition": "*",
                        "mulligan": "CORE_CS2_235",
                        "value": "hold",
                    }
                ]
            },
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Combo.json",
        {
            "GameCardId": "Combo",
            "Combos": [
                {
                    "comment": "ShadowPriest: source-backed sequence",
                    "condition": "*",
                    "combo": ["CARD_A", "CARD_B"],
                    "value": "10",
                }
            ],
        },
    )

    report = build_config_quality_report(package)

    assert report["checks"]["runtime_json"]["metadata_leaks"] == []
    assert report["apply_blocking"] is False
```

- [ ] **Step 2: Add metadata leak attention coverage for special surfaces**

Append:

```python
def test_config_quality_flags_special_runtime_surface_metadata_leaks(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "Mulligan": {
                "values": [
                    {
                        "comment": "bad metadata row",
                        "condition": "*",
                        "mulligan": "CARD_A",
                        "value": "hold",
                        "source_claim_ids": ["claim_a"],
                    }
                ]
            },
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Combo.json",
        {
            "GameCardId": "Combo",
            "Combos": [
                {
                    "comment": "bad combo metadata row",
                    "condition": "*",
                    "combo": ["CARD_A", "CARD_B"],
                    "value": "10",
                    "claim_id": "claim_combo",
                }
            ],
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["runtime_json"]["metadata_leaks"] == [
        {
            "file": "CustomConfig/shadowpriest/Combo.json",
            "block": "Combos",
            "row_index": 0,
            "extra_keys": ["claim_id"],
        },
        {
            "file": "CustomConfig/shadowpriest/Mulligan.json",
            "block": "Mulligan",
            "row_index": 0,
            "extra_keys": ["source_claim_ids"],
        },
    ]
    assert report["apply_blocking"] is False
```

- [ ] **Step 3: Run focused tests and confirm the leak test fails**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py::test_config_quality_allows_lean_special_runtime_surfaces tests\test_config_quality_contract.py::test_config_quality_flags_special_runtime_surface_metadata_leaks -q -p no:cacheprovider
```

Expected before implementation: the metadata leak test fails because special runtime files are currently skipped in `_runtime_json_check()`.

- [ ] **Step 4: Add surface-specific row-key constants**

In `src/hsconfig/config_quality_contract.py`, replace:

```python
RUNTIME_VALUE_ROW_KEYS = {"comment", "condition", "value"}
```

with:

```python
CARDID_RUNTIME_VALUE_ROW_KEYS = {"comment", "condition", "value"}
SPECIAL_RUNTIME_VALUE_ROW_KEYS = {
    "GlobalValues.json": {"comment", "condition", "value"},
    "Mulligan.json": {"comment", "condition", "mulligan", "value"},
    "Combo.json": {"comment", "condition", "combo", "value"},
}
RUNTIME_VALUE_ROW_KEYS = CARDID_RUNTIME_VALUE_ROW_KEYS
```

Keeping `RUNTIME_VALUE_ROW_KEYS` as an alias preserves any local tests or imports that still reference it.

- [ ] **Step 5: Add a row-key helper**

Add this helper near `_file_card_id()`:

```python
def _runtime_value_row_keys(file_name: str) -> set[str]:
    return set(
        SPECIAL_RUNTIME_VALUE_ROW_KEYS.get(file_name, CARDID_RUNTIME_VALUE_ROW_KEYS)
    )
```

- [ ] **Step 6: Include special files in metadata-leak scanning**

In `_runtime_json_check()`, remove this early skip:

```python
            if path.name in SPECIAL_RUNTIME_FILES:
                continue
```

Then change the stray-card check to skip only the stray-card part for special files:

```python
            if path.name not in SPECIAL_RUNTIME_FILES:
                file_card_id = _file_card_id(path.name)
                if file_card_id and file_card_id not in expected_card_ids:
                    stray_cardid_files.append(_relative(path, package))
```

Finally replace:

```python
                    extra_keys = sorted(set(value_row) - RUNTIME_VALUE_ROW_KEYS)
```

with:

```python
                    extra_keys = sorted(
                        set(value_row) - _runtime_value_row_keys(path.name)
                    )
```

- [ ] **Step 7: Run focused config-quality tests**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py::test_config_quality_allows_lean_special_runtime_surfaces tests\test_config_quality_contract.py::test_config_quality_flags_special_runtime_surface_metadata_leaks -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 8: Run full config-quality suite**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py -q -p no:cacheprovider
```

Expected: all config-quality tests pass.

- [ ] **Step 9: Commit Task 4**

Run:

```powershell
git add src\hsconfig\config_quality_contract.py tests\test_config_quality_contract.py
git commit -m "fix: lint special runtime surface metadata"
```

Expected: commit succeeds and does not stage unrelated files.

---

### Task 5: Optional Skill Text Sync If Needed

**Files:**
- Modify only if implementation changed operator wording:
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`

**Interfaces:**
- Consumes: repo-local source skill files.
- Produces: installed `C:\Users\darbo\.codex\skills\hsconfig` copy in sync.

- [ ] **Step 1: Decide whether wording changed**

Run:

```powershell
git diff -- .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md
```

Expected: if no docs were changed by Tasks 1-4, skip to Task 6.

- [ ] **Step 2: If docs changed, add focused docs test**

If wording changed, update or add a single assertion in `tests/test_skill_files.py` that protects the new wording. The assertion must be exact-string and must not mention gameplay logs or HSTuner.

- [ ] **Step 3: Run skill-file tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_skill_sync.py -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py --install-root "C:\Users\darbo\.codex\skills"
python scripts\sync_installed_skill.py --check --install-root "C:\Users\darbo\.codex\skills"
```

Expected final line:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 5: Commit Task 5 only if files changed**

Run:

```powershell
git add .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_files.py tests\test_skill_sync.py
git commit -m "docs: clarify runtime contract hygiene"
```

Expected: commit succeeds if files changed. If Git reports `nothing to commit, working tree clean`, skip the commit.

---

### Task 6: Final Verification, Currentness, And Clean Worktree

**Files:**
- No source edits expected.

**Interfaces:**
- Consumes: commits from Tasks 1-5.
- Produces: local and remote-current clean branch evidence.

- [ ] **Step 1: Run focused regression suite**

Run:

```powershell
python -m pytest tests\test_card_intent_taxonomy.py tests\test_static_semantics.py tests\test_mechanic_drift.py tests\test_mechanic_support.py tests\test_card_behavior_router.py tests\test_config_quality_contract.py tests\test_contract_preflight.py tests\test_apply_authority_boundary.py -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 2: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected JSON fields:

```json
{
  "status": "PASS",
  "source_status_apply_blocking": false,
  "runtime_apply_authority": "reports/operator_summary.json"
}
```

- [ ] **Step 3: Run contract spine sentinel**

Run:

```powershell
python -m hsconfig.cli contract-spine-sentinel --json
```

Expected JSON fields:

```json
{
  "status": "clean",
  "authority": "diagnostic_only",
  "apply_blocking": false
}
```

- [ ] **Step 4: Run currentness check**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected JSON fields:

```json
{
  "dirty": false,
  "behind_origin_main": 0,
  "clean_for_runtime_work": true
}
```

- [ ] **Step 5: Verify no forbidden runtime evidence is tracked**

Run:

```powershell
git ls-files | Select-String -Pattern "Power\.log|\.hdtreplay|\.hsreplay|BotPlayHistory\.log|Hearthstone.log|outputs/|outputs\\"
```

Expected: no output.

- [ ] **Step 6: Verify final git state**

Run:

```powershell
git status --short --branch
```

Expected: branch line only, no dirty file entries.

- [ ] **Step 7: Push for remote currentness**

Run:

```powershell
git push origin codex/hsconfig-semantic-intent-scoring
```

Expected: push succeeds and remote branch contains all implementation commits.

- [ ] **Step 8: Confirm remote-clean currentness after push**

Run:

```powershell
git fetch --all --prune --tags
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected: `dirty=false`, `behind_origin_main=0`, `clean_for_runtime_work=true`, and no dirty file entries.

---

## Self-Review

- Spec coverage: The plan implements only the current recommended technical improvements: token-safe intent matching, shared modern-mechanic visibility, report-only suppression precedence, and special runtime-surface JSON leanness checks.
- Boundary review: No task adds gameplay sequencing, HSTuner, logs, replay parsing, new runtime surfaces, a second apply gate, or source-status apply blocking.
- Source/contract review: The plan keeps all source and config-quality signals diagnostic-only while making their evidence cleaner and harder to misread.
- Wild-deck review: Unknown or report-only mechanics remain visible as suppression/report rows, not blockers; packages should still generate for arbitrary Wild decks.
- Cleanliness review: Each code task commits only its scoped files, final verification checks no forbidden runtime evidence, and the branch ends pushed with a clean worktree.

## Execution Handoff

Plan complete and saved to `C:\Users\darbo\Documents\HSConfig\docs\superpowers\plans\2026-07-22-hsconfig-runtime-contract-hygiene.md`.

Recommended next execution mode: **Subagent-Driven**. Dispatch one implementation subagent for each independent task after Task 0, then use the main agent as reviewer and final verifier.
