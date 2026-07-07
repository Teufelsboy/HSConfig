# Task 4 Report: Compact Depth-Matrix E2E for HSConfig

Status: DONE

## Scope

- Added the required compact integration proof at `tests/test_depth_matrix_e2e.py`.
- Kept the task narrow: one new E2E file plus only the minimal adjacent production fixes exposed by the RED run.

## Files Changed

- `tests/test_depth_matrix_e2e.py`
  - Added the three required proof lanes:
    - ShadowPriest full-depth package proof
    - MechPala posture-contrast proof
    - Synthetic linked-entity combo fixture proof
- `src/hsconfig/compile_globalvalues.py`
  - Added a backward-compatible `status` alias alongside the existing `decision` field in key profiles.
- `src/hsconfig/visionai_registry.py`
  - Relaxed CardID runtime filename acceptance just enough to allow synthetic uppercase underscore fixture IDs such as `DISCOVER_CARD.json` and `COMBO_A.json`.
- `src/hsconfig/card_behavior_surface_router.py`
  - Stopped reporting `combo_sequence` claims as card-behavior suppressions when they are owned by the combo lane.

## RED Evidence

Command:

```powershell
python -m pytest tests/test_depth_matrix_e2e.py -q
```

Outcome:

- `2 failed, 1 passed in 8.09s`

Failures observed:

1. `test_depth_matrix_shadowpriest_primary_surface_contract`
   - `globalvalues_profile["keys"]["MyHeroPowerValue"]["status"]` was missing.
   - Existing profile only exposed `decision`.
2. `test_depth_matrix_linked_entity_combo_micro_fixture`
   - Prepare returned `code == 1`.
   - Validation rejected synthetic per-card files as unsupported runtime surfaces.
   - Package also reported missing per-card CardID runtime files because those synthetic CardID filenames were filtered out.

Second RED run after the first minimal fixes:

```powershell
python -m pytest tests/test_depth_matrix_e2e.py -q
```

Outcome:

- `1 failed, 2 passed in 7.91s`

Remaining failure:

- `card_behavior_suppression_report.json` still contained the `combo_sequence` claim with reason `no_documented_card_behavior_surface` even though the combo lane was already valid and emitted `Combo.json`.

## GREEN Evidence

Focused Task 4 run:

```powershell
python -m pytest tests/test_depth_matrix_e2e.py -q
```

Outcome:

- `3 passed in 7.69s`

Required adjacent verification:

```powershell
python -m pytest tests/test_depth_matrix_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_multideck_source_backed_e2e.py -q
```

Outcome:

- `10 passed in 14.88s`

Diff hygiene:

```powershell
git diff --check
```

Outcome:

- Exit 0.
- Only Windows line-ending warnings from Git for touched tracked files.

## Minimal Fix Rationale

- The `status` alias preserves existing `decision` consumers and satisfies the compact integration contract without redefining GlobalValues semantics.
- The CardID filename regex change is narrow and fixture-driven. It still rejects lowercase generic names like `notes.json`.
- The combo suppression change does not broaden option validation and does not weaken unresolved option handling. It only stops misclassifying combo-owned claims inside the card-behavior suppression report.

## Concerns

- None blocking.
