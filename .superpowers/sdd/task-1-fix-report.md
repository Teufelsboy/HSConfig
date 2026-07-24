# Task 1 Review-Haertung Fix Report

## Scope

- Repo: `C:\Users\darbo\Documents\HSConfig`
- Dateien geaendert:
  - `src/hsconfig/source_readiness_preview.py`
  - `tests/test_source_readiness_preview.py`
  - `.superpowers/sdd/task-1-fix-report.md`
- Nicht beruehrt: HSTuner, Logs/Replays, Runtime Writes, Apply-Gates, zweite Apply-Authority.

## RED

- Command: `pytest tests/test_source_readiness_preview.py::test_preview_normalizes_boolean_strings_without_blocking_default_only_surfaces -q`
- Result: exit 1.
- Erwartete Fehlstelle: `runtime_apply_allowed="False"` wurde durch direkte `bool(...)`-Konvertierung als `True` behandelt.
- Relevante Assertion: `assert preview["runtime_apply_allowed"] is False` erhielt `True`.

## Fix

- Kleine `_bool(...)`-Hilfe in `src/hsconfig/source_readiness_preview.py` ergaenzt.
- Genutzt fuer:
  - `source_backed_strong_ready`
  - `strong_candidate`
  - `runtime_apply_allowed`
- Bekannte false-Strings wie `"False"` und `"0"` werden jetzt als `False` normalisiert.
- `default_only_runtime_surfaces` bleibt sichtbar, setzt `default_only_clean=False`, blockiert Apply aber nicht.
- Plan-definierte Outputs bleiben diagnostisch/non-blocking: `apply_blocking=False`, `source_status_apply_blocking=False`, `runtime_write_performed=False`.

## GREEN

- Command: `pytest tests/test_source_readiness_preview.py -q`
- Result: exit 0, `5 passed in 0.12s`.

## Notes

- Der vorhandene dirty Worktree-Eintrag `.superpowers/sdd/progress.md` war bereits vor diesem Fix vorhanden und wurde nicht beruehrt.
- Kein Commit erstellt; Controller uebernimmt Commit/Review.
