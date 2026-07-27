# Task 8 Report — Physical Runtime Surface Ledger

Implemented a canonical `runtime_surface_ledger.json` derived only from compiled
Mulligan, GlobalValues, Combo and CardID artifacts. Readiness, usefulness,
explainability and the operator summary now carry one shared ledger SHA-256;
the package builder asserts the three report hashes agree.

Covered physical parity:

- ImbueMage `FIR_911` compiled Mulligan hold is `Mulligan.json` / `mulligan_only`.
- ShadowPriest keeps `SW_448` as the source record and `EX1_625t` as a separate
  linked runtime record.
- All three MechPala sideboard modules remain analysis-only with no surfaces.

Verification: 248 prescribed tests passed; targeted Ruff check and `git diff --check`
passed. No runtime, HSTuner or Desktop access was used.
