# Task 1 Report: Source-Informed Closure Order

Status: DONE

## Scope

Implemented Task 1 from `C:\Users\darbo\Documents\HSConfig\.superpowers\sdd\source-closure-depth-ux-task-1-brief.md` in the allowed files only:

- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_depth_closure_index.py`
- `C:\Users\darbo\Documents\HSConfig\tests\test_source_depth_closure_index.py`
- `C:\Users\darbo\Documents\HSConfig\tests\test_boarlock_closure_wave.py`

## What Changed

1. Added summary-level closure ordering helpers to `source_depth_closure_index.py`:
   - `_closure_priority()`
   - `_source_informed_closure_sequence()`
   - `_preserved_source_informed_targets()`
2. Extended the closure-index summary with:
   - `next_closure_target`
   - `closure_sequence`
   - `preserved_source_informed_targets`
3. Added the brief-mandated regression test covering ordered source-informed closure targets.
4. Updated existing tests to cover the new summary fields for both empty and Boarlock/Kingslayer representative cases.

## TDD Record

Red:

```powershell
python -m pytest tests/test_source_depth_closure_index.py::test_index_exposes_ordered_source_informed_closure_targets -q
```

Observed expected failure:

- `KeyError: 'next_closure_target'`

Green:

```powershell
python -m pytest tests/test_source_depth_closure_index.py tests/test_boarlock_closure_wave.py tests/test_matrix_visibility.py -q
```

Final result:

- `11 passed in 8.08s`

## Commit

- `06594b3` `feat: expose source-informed closure order`

## Notes

- Preserved unrelated existing untracked work at `docs/research/2026-07-08-hsconfig-skill-optimality-audit-v2/`.
- Did not widen the fixture matrix and did not add runtime or post-run behavior.

---

# Task 1 Fix Report: Review Finding on Preserved Source-Informed Targets

Status: DONE

## Review Finding

`_preserved_source_informed_targets()` included any row with `strongness_visibility.operator_action == preserve_source_informed_with_explicit_stop_condition`, even when `fixture_stage` was not `source_informed_valid_fixture`.

## Fix Applied

1. Added the same `fixture_stage == "source_informed_valid_fixture"` guard used by `_source_informed_closure_sequence()` before a row can enter `preserved_source_informed_targets`.
2. Added a regression test proving a `core_source_backed_fixture` row with the preserve operator action is excluded from `preserved_source_informed_targets`.

## TDD Record

Red:

```powershell
python -m pytest C:\Users\darbo\Documents\HSConfig\tests\test_source_depth_closure_index.py -q
```

Observed expected failure:

```text
..F.                                                                     [100%]
================================== FAILURES ===================================
_____ test_index_excludes_non_source_informed_rows_from_preserved_targets _____

E       AssertionError: assert ['Boarlock', 'ShadowPriest'] == ['Boarlock']
```

Green:

```powershell
python -m pytest tests/test_source_depth_closure_index.py tests/test_boarlock_closure_wave.py tests/test_matrix_visibility.py -q
```

Final result:

```text
............                                                             [100%]
12 passed in 9.59s
```
