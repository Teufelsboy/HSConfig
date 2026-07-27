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

## Round 3 surface identity follow-up

Combo rows retain their exact supported operator in canonical identity; even a
single valid physical row is rich. Mulligan records include card-specific hold
and discard rules while usefulness only treats concrete non-wildcard holds as
rich. Claim reconciliation matches Mulligan selector/action and Combo
order/operator, preserves claim-local evidence/missing files, and rejects
orphan or out-of-deck CardID/Mulligan/Combo identities unless an explicit
linked runtime owner authorizes the CardID entity.

Round-3 verification: RED confirmed for operator loss, one-row Combo richness,
discard identity, and orphan output; focused Task-8 suite `86 passed`, Ruff and
`git diff --check` passed. No runtime, HSTuner or Desktop access was used.

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

## Round 4 claim satisfaction and canonical identity follow-up

Card, closure, and operator-attention status now derive from claim-specific
physical satisfaction instead of a raw union of filenames. Mulligan matching
uses normalized direct, list, plus-combo, DROP and wildcard selectors and
requires exact action and condition. Combo requires exact order and operator;
GlobalValues requires the exact changed key; CardID requires the accepted
behavior-plan runtime owner, behavior block, condition and value to match a
physical runtime row.

Only validated non-self linked relations whose source exists in the deck or
analysis graph can exempt linked CardID entities from orphan detection. Self
owners cannot authorize unrelated entities. `Presume.json` and `Concede.json`
are modelled as supported special surfaces rather than misclassified as CardID
payloads. Discard-only Mulligan output remains thin and actionable but is not
labelled default-only.

Strict validation now requires schema version 2 to be an actual integer and
compares canonical JSON type-safely, including nested bool/int distinctions.
The sideboard regression reaches the real unexpected-physical-emission path.
Strong Closure prefers canonical explainability claim rows and their
ledger-confirmed emitted files, so generated-file lists or unmatched plan rows
cannot close a profile.

Round-4 verification: RED was observed for each mismatch and type case; the
affected Task-8 and strict-validation suite finished with `340 passed`.
Targeted Ruff and `git diff --check` passed. No runtime, HSTuner or Desktop
access was used.

## Round 5 productive identity and multi-owner follow-up

The productive source-contract audit now carries the exact fields needed to
reconcile emitted artifacts: Mulligan selector, action and source condition;
Combo operator (defaulting to `>>`); both GlobalValues key spellings; and the
accepted CardID behavior-plan identities.

Mulligan conditions are normalized with the same lowering function as the
compiler, including omitted conditions, coin state, and structured
`hand_contains` conditions. The physical ledger canonicalizes its condition
rows through that same contract. Combo claims without an explicit operator now
match the compiler's `>>` default.

Behavior-plan mappings retain every identity for a claim. Multi-card claims are
reconciled per runtime owner and expected CardID file, so a complete two-file
claim succeeds while a partial or value-mismatched file remains explicitly
missing instead of being silently discarded as ambiguous.

Round-5 verification used real source-contract audit output for the new
regressions. RED was observed for missing productive identity fields, condition
alias/canonicalization, the Combo default, and multi-identity behavior claims.
The affected Task-8 suite plus source-audit coverage finished with `364 passed`;
targeted Ruff and `git diff --check` passed. No runtime, HSTuner or Desktop
access was used.
