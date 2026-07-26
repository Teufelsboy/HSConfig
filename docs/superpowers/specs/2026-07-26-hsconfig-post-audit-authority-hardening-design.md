# HSConfig Post-Audit Authority Hardening Design

**Status:** Approved through the 2026-07-26 evidence-tiered audit and the
user's explicit request to create the implementation plan from its
recommendations.

**Scope:** `C:\Users\darbo\Documents\HSConfig` only. This design changes
source authorization, linked runtime-entity ownership, package derivation
integrity, expert input handling, exact-evidence bounds, deterministic date
propagation, tests, and operator documentation. It does not apply a package,
write HearthRanger runtime files, use HSTuner, introduce unproven VisionAI
syntax, or claim gameplay optimality.

## Problem

The current `main` branch produces technically valid ShadowPriest packages and
passes the complete repository suite, but the audit found contract gaps that
the tests do not cover:

1. `source_backed_static_semantics` can authorize `combo_sequence` and emit
   `Combo.json`, contradicting the documented rule that static card data cannot
   prove strategic combo order.
2. The same static combo claim can contribute to
   `SOURCE_BACKED_STRONG` closure because Strong source quality is not scoped
   by claim kind.
3. `SW_448.json` owns `BeforeUseHeroPowerBonus` even though `SW_448` is
   Darkbishop Benedictus and `EX1_625t` is the transformed Mind Spike hero
   power that VisionAI evaluates before use.
4. Exact source receipts prove internal consistency but do not distinguish a
   live HTTP acquisition from fixture, captured, or manually drafted input.
5. `reports/operator_summary.json` is the sole apply authority but is not
   bound to a canonical derivation receipt covering deck identity, source
   receipts, strict validation inputs, and runtime JSON.
6. `configure --cards-json` and `--allow-placeholder` can bypass normal
   deck-code decoding without making runtime apply technically impossible.
7. Exact-evidence count parsing lacks deterministic bounds and logical
   count/hash relationships.
8. `--current-date` is not propagated through every final source-claim build
   stage.
9. Saved and installed ShadowPriest packages are stale, but generated outputs
   are ignored evidence and must not be committed or silently applied.

## Chosen Architecture

The remediation remains one cohesive source-to-runtime integrity wave because
all affected mechanisms meet in `package_builder`, the canonical surface gates,
and the normal apply path.

### 1. Strategic Surface Authorization

`source_document_model` remains the canonical owner of surface authorization.
`can_lower_to_combo` receives the same deck identity and verified-receipt
context used by Mulligan and GlobalValues.

A Combo runtime row requires all of the following:

- `claim_kind == "combo_sequence"`;
- `claim_readiness == "guide_backed"`;
- canonical public-guide identity;
- `deck_match_scope == "exact_deck_matched"`;
- `promotion_eligible == true`;
- `source_visibility == "full_text"`;
- `source_lane == "deck_matched_public_guide"`;
- complete exact-deck evidence matching the target fingerprint;
- a matching canonical source receipt;
- a complete sequence/timing contract containing at least two cards from the
  target deck.

Static, fixture-only, captured-unverified, stale, snippet, decklist,
statistical, policy, and default-runtime evidence remains diagnostic and cannot
emit Combo.

Strong closure becomes claim-kind aware. Static semantics may contribute only
to deterministic CardID/effect claim families. It cannot satisfy strategic
groups for Mulligan, Combo, targeting posture, or gameplan posture.

### 2. Acquisition Provenance

Every acquired or imported source record carries a normalized
`acquisition_provenance` object:

```json
{
  "mode": "live_http",
  "content_sha256": "sha256:64-lowercase-hex-digits",
  "authority": "live_verified"
}
```

Supported modes are:

- `live_http` / `live_verified`;
- `captured_record` / `captured_unverified`;
- `manual_evidence` / `manual_unverified`;
- `fixture_map` / `fixture_only`;
- `legacy_claims_json` / `legacy_unverified`.

Only `live_verified` provenance can mint canonical exact strategic source
receipts. Other modes remain useful for deterministic tests, diagnostics, and
static CardID semantics but cannot authorize exact Mulligan, GlobalValues, or
Combo runtime writes and cannot promote `SOURCE_BACKED_STRONG`.

The receipt binds claim ID, claim signature, target deck fingerprint,
acquisition mode, and content digest. The raw deckstring and raw page body are
not persisted in the receipt.

### 3. Linked Runtime Entity Ownership

Card semantics and physical runtime ownership are separate concepts.
Darkbishop remains the source/enabler card, while Mind Spike is the runtime
entity evaluated by `BeforeUseHeroPowerBonus`.

The linked-entity resolver maps:

```text
SW_448 / hero_power_transform -> EX1_625t
```

The generated runtime package therefore contains:

- metadata-only `SW_448.json`, with no Mulligan keep, body priority,
  `BeforePlayCardBonus`, or `BeforeUseHeroPowerBonus`;
- `EX1_625t.json` with `GameCardId=EX1_625t` and exactly one
  `BeforeUseHeroPowerBonus / * / 10` row;
- source-to-runtime diagnostics that retain both the source card and the
  runtime owner;
- linked-runtime readiness that does not pretend `EX1_625t` is a main-deck
  card.

Strict validation accepts linked runtime entities only when the identity graph
contains an exact curated link. Arbitrary non-deck CardIDs remain forbidden.
Pre-run output continues to state that in-client behavior is unproven.

### 4. Package Derivation Integrity

`package_derivation_receipt.py` owns a deterministic receipt over:

- `reports/input_manifest.json`;
- `reports/deck_identity.json`;
- `reports/deck_fingerprint.json`;
- canonical source receipts;
- `reports/globalvalues_baseline.json`;
- `reports/globalvalues_profile.json`;
- every runtime JSON under the single generated deck directory.

The receipt contains sorted relative paths and SHA-256 digests. It does not
hash itself and does not include volatile timestamps.

`operator_summary.json` records the receipt digest and schema version.
`evaluate_apply_gate`:

1. runs strict package validation itself;
2. verifies the derivation receipt;
3. verifies the operator-summary receipt reference;
4. checks the existing generated-file parity and forbidden-surface rules;
5. allows load-safe apply only when the recomputed technical result is valid.

The operator summary remains the only normal human-facing authority, but it can
no longer become valid merely by declaring `technical_status=VALID_PACKAGE`.

### 5. Deck Input Verification

`deck_input_verification.py` classifies the roster:

- `decoded_from_deck_code`;
- `cards_json_matches_deck_code`;
- `cards_json_unverified`;
- `placeholder_unverified`.

Normal configure uses `decoded_from_deck_code`.
`cards-json` is verified by decoding the supplied deck code and comparing the
canonical card multiset. Placeholder or mismatching inputs may build
diagnostic packages, but the package records
`deck_input_verification.runtime_apply_eligible=false`.

`configure --apply` and `apply` reject packages whose deck input is unverified.
No source-strength warning can override this technical identity boundary.

### 6. Deterministic Evidence Bounds And Date

Exact-source candidate counts use a repository-owned maximum of 256. Decimal
strings longer than three digits are rejected before `int()` conversion.
Canonical evidence additionally requires:

- `1 <= decoded_candidate_count <= candidate_count <= 256`;
- one unique hash per candidate;
- `len(candidate_deck_code_hashes) == candidate_count`.

Every configure stage passes the same normalized `current_date` into source
acquisition, source autopilot, source drafting, guide claim building, final
source-document building, and reports.

## Error Handling

- Rejected strategic claims remain visible with stable surface-specific
  reasons.
- Invalid provenance never falls back to live authority.
- Invalid or missing derivation receipts block apply but do not prevent
  diagnostic inspection.
- Unverified deck input may generate reports but never obtain runtime apply
  permission.
- Unknown linked runtime entities are suppressed with
  `linked_runtime_entity_unresolved`.
- Invalid count forms return no canonical exact evidence and cannot mint a
  receipt.
- Date parsing errors fail the command before source classification begins.

## Verification Contract

Implementation must prove:

- a static, stale, fixture, captured, snippet, decklist, statistical, policy,
  or default-runtime Combo claim never emits `Combo.json`;
- only exact, full-text, live-verified, receipt-bound guide Combo evidence
  emits;
- static Combo cannot satisfy Strong closure;
- deterministic static CardID/effect claims remain supported;
- `SW_448.json` contains no hero-power-use row;
- `EX1_625t.json` owns the single hero-power-use row and is accepted only
  through the curated link;
- exact Mulligan and GlobalValues require live-verified acquisition receipts;
- fixture-backed exact runs remain explicit diagnostic proof and cannot become
  production Strong/apply authority;
- forged or stale operator summaries and modified derivation inputs block
  apply;
- normal decoded deck input remains apply-eligible;
- mismatching `cards-json` and placeholder input are not apply-eligible;
- oversized, inconsistent, or hash-count-mismatched exact evidence is rejected
  independently of Python interpreter settings;
- one frozen `current_date` produces the same freshness decision at every
  stage;
- fresh exact and archetype ShadowPriest packages validate read-only;
- runtime-match performs no write;
- no generated package or runtime evidence is committed;
- the complete test suite, contract guardrails, installed-skill check, and
  one-version Git/GitHub checks pass.

## Out Of Scope

- Applying any package or changing `C:\Users\darbo\Desktop\HS`.
- HSTuner, replay analysis, win-rate measurement, or matchup tuning.
- New VisionAI condition atoms.
- Empirical calibration of the numeric values `12`, `10`, `8`, or the
  GlobalValues multipliers.
- Treating fixture or captured input as equivalent to a live public source.
- Cryptographic protection against an operator who can intentionally rewrite
  both the repository and the HearthRanger runtime.
