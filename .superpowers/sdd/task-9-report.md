# Task 9 Report: Add GlobalValues Per-Key Authority

## Status

DONE

## Changed Files

- `src/hsconfig/globalvalues_key_authority.py`
  - Added `authority_for_key(key)` with `copy_baseline`, `step1_posture_overlay_allowed`, and `runtime_evidence_required` categories.
  - Added board-value component labels for Step1 posture keys and runtime-evidence-only keys.
- `src/hsconfig/globalvalues_authority.py`
  - Embeds `key_authority` in allowed Step1 overlay rows.
  - Embeds `key_authority` in runtime-blocked rows.
  - Shares the runtime-evidence key registry with `globalvalues_key_authority.py`.
- `src/hsconfig/compile_globalvalues.py`
  - Adds `authority_category` and `board_value_component` to every GlobalValues profile row.
  - Uses embedded authority metadata from the authority matrix when present, with registry fallback for older plan rows.
- `src/hsconfig/cli.py`
  - Writes `reports/global_values_key_profile_report.json` with the same payload as `globalvalues_profile.json`.
- `tests/test_globalvalues_authority.py`
  - Added red test for core key classification.
  - Added matrix coverage for allowed, blocked, and baseline `key_authority` rows.
- `tests/test_compile_globalvalues.py`
  - Added profile coverage for overlay-allowed, runtime-evidence-required, and baseline-copy keys.
- `tests/test_prepare_cli.py`
  - Added prepare coverage for `global_values_key_profile_report.json`.
- `.superpowers/sdd/task-9-report.md`
  - Added this report.

## Tests And Outcomes

RED:

- `python -m pytest tests/test_globalvalues_authority.py::test_globalvalues_key_authority_classifies_core_keys -q`
  - Outcome before implementation: 1 collection error for the expected `ModuleNotFoundError: No module named 'hsconfig.globalvalues_key_authority'`.
- `python -m pytest tests/test_globalvalues_authority.py::test_globalvalues_authority_matrix_embeds_per_key_authority tests/test_globalvalues_authority.py::test_unknown_posture_keeps_baseline_default tests/test_compile_globalvalues.py::test_compile_globalvalues_profile_includes_key_authority_fields tests/test_prepare_cli.py::test_prepare_source_posture_drives_globalvalues_authority_matrix -q`
  - Outcome before wiring: 4 failed for expected missing `key_authority`, missing profile authority fields, and missing `global_values_key_profile_report.json`.

GREEN:

- `python -m pytest tests/test_globalvalues_authority.py::test_globalvalues_key_authority_classifies_core_keys -q`
  - Outcome after adding the registry module: 1 passed.
- `python -m pytest tests/test_globalvalues_authority.py::test_globalvalues_authority_matrix_embeds_per_key_authority tests/test_globalvalues_authority.py::test_unknown_posture_keeps_baseline_default tests/test_compile_globalvalues.py::test_compile_globalvalues_profile_includes_key_authority_fields tests/test_prepare_cli.py::test_prepare_source_posture_drives_globalvalues_authority_matrix -q`
  - Outcome after wiring: 4 passed.
- `python -m pytest tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_prepare_cli.py -q`
  - Outcome: 27 passed.
- `python -m pytest -q`
  - Outcome before final helper cleanup: 234 passed.
- `python -m pytest tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_prepare_cli.py -q`
  - Outcome after final helper cleanup: 27 passed.
- `python -m pytest -q`
  - Outcome after final helper cleanup: 234 passed.

## Commits

- Task 9 implementation commit: `feat: classify GlobalValues key authority`
- Final commit hash is reported in the controller final response because this report is included in the same commit.

## Self-Review

- Scope stayed within the Task 9 files plus this report.
- Mulligan selector identity, CardID routing, Combo timing, and runtime write gates were not changed.
- Runtime `GlobalValues.json` output shape remains unchanged; authority metadata is report/profile-only.
- Existing GlobalValues baseline validation still receives the same `globalvalues_profile.json` payload, with additive metadata fields.
- `compile_globalvalues(...)` accepts older authority matrix rows without `key_authority` by falling back to `authority_for_key(key)`.
- The new CLI report mirrors `globalvalues_profile.json`, matching the Task 9 brief.
- The existing untracked plan document under `docs/superpowers/plans/` was left untouched.

## Concerns

- No blocking concerns.
- Scope note: per-key categories are intentionally conservative and limited to the Task 9 registry keys. Unknown keys remain `copy_baseline` unless added to the registry later.
