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

## Round 1 fail-closed follow-up

The ledger now parses `ComboList.values[].combo` only through `>>` or `>->`
sequences and records malformed rows as physical errors. CardID surfaces require
matching filename/GameCardId plus a supported nonempty behavior block; metadata-
only compiler scaffolds remain surface-less. GlobalValues is emitted only when a
real nonempty value block exists.

Empty or missing physical ledger records cannot inherit plan-derived readiness,
usefulness, explainability, closure, evidence-chain, or attention status. The
ledger also records ineligible sideboard emissions, rejects them in strict
validation, and fails closed on order-independent linked-owner collisions.

Round-1 verification: `74 passed` across ledger, explainability, and strict
validation regressions; `19 passed` for the multi-deck source-backed E2E suite;
both targeted Ruff checks and `git diff --check` passed. No runtime, HSTuner or
Desktop access was used.
