# Final Review Fixes

## Scope

- Fixed final-review issues A, B, and C in the allowed production files.
- Added the missing skill-sync missing-folder regression test; no production change was needed there.
- Did not touch `.superpowers/sdd/progress.md`, task-2 report files, operator docs, skill docs, runtime logs, HSTuner, or runtime apply surfaces.

## RED

- `python -m pytest tests/test_card_intent_taxonomy.py::test_taxonomy_does_not_treat_attendant_title_alone_as_damage_aura -q`
  - Expected failure: `Attendant deck guide` classified as `damage_aura_amplifier` instead of `semantic_default`.
- `python -m pytest tests/test_config_quality_contract.py::test_config_quality_allows_darkbishop_mulligan_keep_with_explicit_source_evidence -q`
  - Expected failure: `darkbishop_boundary` did not expose `explicit_mulligan_keep_evidence_present`, and the old logic would still report the Darkbishop keep problem.
- `python -m pytest tests/test_contract_preflight.py::test_contract_preflight_runtime_error_fallback_preserves_normal_payload_schema -q`
  - Expected failure: generic CLI fallback omitted top-level `research_context`.
- `python -m pytest tests/test_skill_sync.py::test_shared_skill_sync_status_reports_missing_install_folder_without_writes -q`
  - Result: passed on first run. This was the minor test gap; existing production behavior already returned `missing_folder` without writing.

## GREEN

- `python -m pytest tests/test_card_intent_taxonomy.py::test_taxonomy_does_not_treat_attendant_title_alone_as_damage_aura tests/test_config_quality_contract.py::test_config_quality_allows_darkbishop_mulligan_keep_with_explicit_source_evidence tests/test_contract_preflight.py::test_contract_preflight_runtime_error_fallback_preserves_normal_payload_schema tests/test_skill_sync.py::test_shared_skill_sync_status_reports_missing_install_folder_without_writes -q`
  - `4 passed`
- `python -m pytest tests/test_contract_preflight.py tests/test_skill_sync.py -q`
  - `24 passed`
- `python -m pytest tests/test_card_intent_taxonomy.py tests/test_config_quality_contract.py -q`
  - `29 passed`
- `git diff --check`
  - passed; only Git line-ending warnings were printed.

## Changes

- `card_intent_taxonomy.py`: requires clear Voidtouched identity or a damage plus amplifier conjunction for `damage_aura_amplifier`; `attendant` alone no longer scores as critical.
- `config_quality_contract.py`: Darkbishop mulligan keeps are only flagged when `Mulligan.json` keeps `SW_448` and no explicit accepted `mulligan_keep` source evidence is present in existing claim/mulligan/source-audit reports.
- `commands/contract_preflight.py`: generic exception fallback now preserves the normal payload schema by including `research_context`.
- `tests/test_skill_sync.py`: missing install-root/folder coverage verifies `installed_skill_present=false`, `matches_repo_skill=false`, `reason=missing_folder`, `status=attention`, diagnostic-only authority, sync-script recommendation, and no filesystem writes.

## Residual Risk

- No full repository suite was run; verification was focused on the requested affected test files.
