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

## Round 2 canonicality and claim-projection follow-up

Schema-2 packages now require `reports/runtime_surface_ledger.json`. Strict
validation re-derives the canonical ledger from `CustomConfig`, deck identity,
the GlobalValues baseline, and linked-owner plan records, then verifies schema,
SHA-256, and complete content equality. Missing, stale, malformed, or tampered
ledger files fail closed; the physical re-derivation itself supplies the
sideboard, malformed-payload, owner-collision, and unknown-GlobalValues-key
checks.

The ledger records actual Mulligan rule identities/count, Combo row identities/
count, CardID entities and behavior-row counts (including linked runtime
owners), and baseline-compared GlobalValues changed-key metrics. Usefulness now
uses those values exactly, so baseline-only GlobalValues remains thin.

Explainability reprojects matching claim files from card/linked physical
surfaces. Empty physical output removes claim emission and summary lowering;
matching strong Mulligan output keeps the source-backed strong closure.

Round-2 verification: RED observed for missing/tampered/stale Strict ledgers
and absent metrics; then `80 passed` across ledger, explainability, and strict
validation plus targeted Ruff; `19 passed` multi-deck E2E plus Ruff; `git diff
--check` passed. No runtime, HSTuner or Desktop access was used.
