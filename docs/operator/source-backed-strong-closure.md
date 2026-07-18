# Source-Backed Strong Closure

This file tracks which representative HSConfig deck fixtures are truly strong.

For the promotion wave, check `reports/source_claim_gap_report.json` first for the first missing source or lowering link, then `reports/strong_promotion_report.json` for the promotion verdict.

`core_source_backed_fixture` means the fixture must produce:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- no `semantic_blockers`
- no normal-path `Presume.json` or `Concede.json`

`source_informed_valid_fixture` means the fixture proves a valid source-informed package,
but it still needs guide claims, runtime-surface lowering, condition lowering,
mechanic lowering, or combo sequence detail before it can be called strong.

The fixture matrix also documents `decision_families_proven` and `known_coverage_limits`. These fields describe what a fixture proves for HSConfig's pre-game config compiler. They are not gameplay-quality claims and they do not imply post-run optimization coverage.

runtime apply is no longer blocked by source strength. The representative matrix still preserves source-strength truth, but `VALID_PACKAGE` plus `runtime_load_safe=true` is enough for an initial load-safe runtime write. Source-informed rows remain valuable because they expose confidence debt, not because they should block usable package handoff.

## SOURCE_BACKED_STRONG Contract

HSConfig always attempts to generate a load-safe valid package for any valid deck code.
`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation gate. HSConfig must still build a valid load-safe config when public source coverage is partial. A deck or surface may only be Strong when every lowerable claim has visible source text or deterministic official static semantics, no expected runtime surface is default-only, and `first_missing_source_action` is `none`.
Operator shorthand: SOURCE_BACKED_STRONG is an evidence-quality label and not a second runtime-write gate.
`reports/operator_summary.json` remains the only normal apply authority.
Plain operator wording: operator_summary.json remains the only normal apply authority.

Acceptance-loop wording:

- operator_summary.json remains the only normal apply authority.
- SOURCE_BACKED_STRONG is an evidence-quality label.
- source_status_apply_blocking must remain false.
- default-only runtime surfaces prevent SOURCE_BACKED_STRONG.
- Darkbishop Benedictus preserves start-of-game and hero-power-transform
  semantics, but must not become a mulligan keep without explicit opening-hand
  source text.

`source_backed_strong_closure` and `no_default_only_runtime_status` are compact diagnostic-only `operator_summary.json` summaries. `source_backed_strong_closure` summarizes whether the visible source-to-runtime chain is closed enough for the Strong label. `no_default_only_runtime_status` summarizes whether expected runtime surfaces avoided hidden default-only output. They do not create apply gates, do not grant or deny runtime writes, and do not replace `reports/operator_summary.json` authority.

`source_backed_status`, `source_strong_ready`, `first_missing_source_action`,
`source_missing_source_actions`, `source_status_reasons`,
`source_status_diagnostic_only`, and `source_status_apply_blocking` are resolved
by `src/hsconfig/source_status_resolver.py`. The same diagnostic-only resolver
feeds `operator_summary.json`, `strong_promotion_report.json`, and
`source_evidence_closure.json`; it never overrides `technical_status`,
`runtime_apply_mode`, or `runtime_apply_allowed`.

`hsconfig research-status-sync` is a read-only diagnostic for historical
`research-deep` JSON files. It compares snapshots with the canonical prepared
package status in `reports/operator_summary.json`. A stale or seed-only
snapshot must not downgrade `SOURCE_BACKED_STRONG`, must not promote a partial
package, and does not create apply authority.

`hsconfig strong-closure-dossier` writes an operator-facing closure dossier for
a prepared package. strong-closure-dossier is diagnostic-only: it may read
`reports/operator_summary.json`, research result snapshots, and
`source_autopilot_report.json`, but it must not write HearthRanger runtime files
or create a second readiness gate. operator_summary.json remains the only normal
apply authority.

## Source Closure Optimizer

`hsconfig source-closure-optimizer` is a diagnostic-only batch report for
freshly prepared packages. It reads `reports/operator_summary.json`, optional
source-candidate proof context, and closure summaries. It does not write runtime
files and does not replace `operator_summary.json`.

The source closure priority queue is diagnostic-only. It combines package
`operator_summary.json`, source candidate proof rows, and optional research-deep
result rows to decide which source claim should be closed next. It must not
write runtime config and must not set `source_status_apply_blocking=true`.

The command may classify a package as:

- `strong`: `SOURCE_BACKED_STRONG` is closed, no default-only runtime surfaces
  are visible, and `first_missing_source_action=none`.
- `partial_source_action_needed`: the package is load-safe, but at least one
  source-to-runtime link remains open.
- `preserved_partial_stop_condition`: the package is load-safe and the current
  missing action is an intentional, documented stop condition such as
  Kingslayer Quick Pick mulligan evidence or Boarlock Fracking mulligan
  evidence.
- `context_only_load_safe`: public candidate material is useful for navigation
  or archetype context, but it cannot close runtime surfaces.
- `invalid_package`: the package is technically invalid and must be fixed before
  source closure matters.

`default_only_runtime_surfaces` prevents `strong`, but it must not turn source
depth into a runtime apply block. `source_status_apply_blocking` remains false
for source-depth gaps.

Operator invariants for source-backed strong closure:

- Source-candidate registries are acquisition seeds only, not promotion authority.
- Candidate URLs must never promote `SOURCE_BACKED_STRONG` without fetched full-text, deck-matched, claim-kind-normalized, surface-gated evidence.
- No default-only runtime success: every emitted/expected runtime surface must be visible in `operator_summary.json.surface_status_ledger` or source-to-runtime diagnostics.
- `source_autopilot_report.json` is source-strength preflight only; `operator_summary.json` remains the normal apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation/apply gate.
- Darkbishop boundary: preserve start-of-game and hero-power-transform semantics, but do not infer opening-hand keep without explicit keep text.
- Profile-aware closure and first-missing maps by card/surface are diagnostics.
- No conservative blocking: any valid deck still builds load-safe even with partial evidence; visible source actions replace blocking.

A package may be `SOURCE_BACKED_STRONG` only when:

- `technical_status=VALID_PACKAGE`
- `runtime_apply_allowed=true`
- every emitted normal runtime row is tied to a non-default promoting source claim
- `default_only_runtime_surfaces=[]`
- every expected runtime surface is emitted, explicitly suppressed, or reported as a gap or source action
- strong evidence comes only from explicit `deck_matched_public_guide`, explicit `archetype_matched_public_guide`, or explicit `official_static_semantics` claims that match the target surface
- `decklist_only`, `statistical_enrichment`, `policy_fallback`, snippets, `default_runtime`, and runtime examples do not count as strong evidence
- policy-backed rows do not count as strong evidence
- snippet-only sources do not count as strong evidence
- explicit `official_static_semantics` may close deterministic CardID/effect surfaces such as `hero_power_transform`, but it does not prove deck-specific mulligan, combo, targeting, or gameplan posture by itself

An explicit policy fallback may keep a package useful and load-safe, but it
keeps the affected row partial until a promoting source lane covers it.
Thin or weak source remains non-blocking, but it must stay visible through
operator/source action fields instead of becoming hidden default-only runtime.

Darkbishop Benedictus is the canonical boundary case: preserve the start-of-game
`hero_power_transform`, Mind Spike, and Shadow runtime effect in contract/CardID
semantics, but never infer an opening-hand keep from Start-of-Game, Shadowform,
or Hero Power text alone. A `mulligan_keep` row for a Start-of-Game or
hero-power-transform card is valid only when the same public guide sentence
directly says to keep that exact card in the mulligan or opening hand.
Incidental mentions such as "keep Papercraft Angel while Darkbishop enables the
Shadow hero power" must keep Papercraft only and preserve Darkbishop as effect
semantics.

`source_autopilot_report.json` is the compact preflight proof for this boundary.
Use `runtime_apply_authority`, `default_only_runtime_surfaces`,
`source_backed_strong_closure.closed`, `card_rows`, `surface_rows`,
`card_closure_lanes`, `surface_closure_lanes`,
`first_missing_source_action_by_card`, and
`first_missing_source_action_by_surface` as diagnostics only. Strong packages
return empty first-missing maps; partial packages list only the first missing
card or surface links that still need source closure.

`source_autopilot_report.json.default_only_runtime_surfaces` is a
source-preflight diagnostic, not runtime-package proof. Runtime default-only
truth is read from `reports/operator_summary.json`; source preflight exposes
`default_only_runtime_surface_status=not_evaluated_in_source_preflight` so this
boundary is machine-readable.

Online-source runs may begin from the built-in source candidate registry. The
registry provides known public-guide URL candidates for selected representative
Wild archetypes and records their count in the source acquisition report. It
does not bypass URL validation, page fetching, deck/card matching, claim
extraction, or the Strong closure profile; weak or stale registry results stay
visible as source actions rather than blocking a valid load-safe package.

## 12-Deck Source Candidate Proof Set

`docs/operator/source-candidate-proof-decks.json` tracks the user-supplied
12-deck source candidate set. This file proves that HSConfig has a source
acquisition seed or an explicit source gap for every supplied deck. It does not
replace `docs/operator/archetype-fixture-matrix.json`, and it does not make
candidate URLs promotion authority.

Candidate rows can be:

- `runtime_claims_possible`: acquisition may reach `SOURCE_BACKED_STRONG`
  only after fetched full-text claims close the runtime surfaces. The registry
  label itself is not strong evidence.
- `candidate_partial`: acquisition can improve source quality, but at least one
  first missing source action is expected.
- `context_only`: the source can confirm archetype or meta presence, but must
  not promote `SOURCE_BACKED_STRONG`.
- `context_seed_urls`: index or archetype-context pages for finding current
  guide candidates. They are never runtime authority and never close a runtime
  surface by themselves.

Candidate URLs must not promote `SOURCE_BACKED_STRONG` without fetched,
deck-matched, claim-kind-normalized, surface-gated full-text evidence.

Historical `research-deep` result JSON is current only when
`hsconfig research-status-sync` can classify it as a strict runtime-lowerable
contract: full-text or canonical source evidence exists, at least one
runtime-lowerable claim kind is present, `first_missing_source_action=none`, and
`default_only_runtime_surfaces=[]`. Seed-only, context-only, partial, stale, or
default-only snapshots are diagnostics only. They must not downgrade a canonical
Strong package and must not promote a partial package.

## Promotion Rule

A matrix row may move from `source_informed_valid_fixture` to `core_source_backed_fixture` only when a fixture prepare run proves:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- zero semantic blockers
- zero blocked cards in `source_claim_gap_report.json`
- no generated `Presume.json` or `Concede.json`

Rows that do not meet all six checks stay source-informed and must expose one specific first missing chain.

## Current Closure Targets

| Deck | Fixture stage | Required work before promotion |
|---|---|---|
| ShadowPriest | `core_source_backed_fixture` | Already strong. Preserve this as the control fixture. |
| CtAPaladin | `source_informed_valid_fixture` | `SOURCE_BACKED_PARTIAL`. Package is load-safe and `runtime_apply_allowed=true`, but explicit mulligan source evidence is still needed before promotion. |
| PirateRogue | `core_source_backed_fixture` | Already strong. Preserve this as the third promoted fixture. |
| BigShaman | `core_source_backed_fixture` | Already strong. Preserve the source-faithful recruit and deathrattle claim set, including explicit `9` recruit/big-cheat and `7` deathrattle runtime values. |
| Discolock | `source_informed_valid_fixture` | `SOURCE_BACKED_PARTIAL`. Package is load-safe and `runtime_apply_allowed=true`, but explicit mulligan source evidence and source-warning closure are still needed before promotion. |
| TreantDruid | `source_informed_valid_fixture` | `SOURCE_BACKED_PARTIAL`. Package is load-safe and `runtime_apply_allowed=true`, but card-specific guide claims are still needed before promotion. |
| ImbueMage | `core_source_backed_fixture` | Promotion proven. Keep as a core control fixture. |
| MechPala | `core_source_backed_fixture` | Already strong. Preserve this as the second promoted fixture. |
| Kingslayer | `source_informed_valid_fixture` | Preserved blocked with explicit stop condition: exact Kingslayer Quick Pick mulligan evidence remains unavailable. Preserve this row as the weapon-sequence source-informed control until an exact Kingslayer/Kingsbane Quick Pick keep-or-discard source exists. |
| Boarlock | `source_informed_valid_fixture` | Preserved blocked with explicit stop condition: exact Boarlock Fracking mulligan evidence remains unavailable or unresolved lowering blockers remain. Preserve this row as the combo-control source-informed control until those blockers close. |
| PirateDH | `source_informed_valid_fixture` | `SOURCE_BACKED_PARTIAL`. Package is load-safe and `runtime_apply_allowed=true`, but card-specific guide claims are still needed before promotion. |

- `Boarlock` remains source-informed with explicit stop condition `exact_boarlock_fracking_mulligan_source_unavailable` unless an exact Boarlock-relevant Fracking mulligan source is added.
- `Kingslayer` remains source-informed with explicit stop condition `exact_kingslayer_quick_pick_mulligan_source_unavailable` unless an exact Kingslayer/Kingsbane `DEEP_014` / `Quick Pick` mulligan source is added.
- `CtAPaladin`, `Discolock`, `TreantDruid`, and `PirateDH` remain load-safe partial rows. Do not use their package validity or policy/runtime fallback rows as source-backed-strong evidence.
- Adjacent archetype advice is not source-backed evidence for these rows.

## Current Source-Informed Closure Decisions

| Deck | Current decision | First missing link | Promotion blocker reason |
|---|---|---|---|
| CtAPaladin | Preserve as source-informed partial until exact source exists | Explicit mulligan source needed before policy-backed mulligan rows can count as strong evidence | `policy_claim_not_strong_evidence` |
| Discolock | Preserve as source-informed partial until exact source exists | Explicit mulligan source needed before policy-backed mulligan rows can count as strong evidence | `policy_claim_not_strong_evidence`, `source_evidence_warnings` |
| TreantDruid | Preserve as source-informed partial until card-specific guide claims exist | Card-specific guide claims needed for low-confidence or uncovered rows | `generic_low_confidence_cards`, `policy_claim_not_strong_evidence`, `source_evidence_warnings`, `uncovered_cards` |
| Kingslayer | Preserve as source-informed until exact source exists | `DEEP_014` / Quick Pick needs explicit mulligan claim | `unsupported_conditions_present`; stop condition `exact_kingslayer_quick_pick_mulligan_source_unavailable` |
| Boarlock | Preserve as source-informed until blockers close | `WW_092` / Fracking needs explicit mulligan claim | `cards_need_runtime_surface`, `generic_low_confidence_cards`, `uncovered_cards`, `unsupported_conditions_present` |
| PirateDH | Preserve as source-informed partial until card-specific guide claims exist | Card-specific guide claims needed for low-confidence or uncovered rows | `generic_low_confidence_cards`, `source_evidence_warnings`, `uncovered_cards` |

Boarlock's current low-confidence `WW_092` / `Fracking` mulligan row documents
generic card-draw advice only. Do not treat Boarlock's low-confidence Fracking row as SOURCE_BACKED_STRONG.

Current closure order keeps Boarlock first and Kingslayer second because they
are durable preserved controls with explicit stop conditions. CtAPaladin,
Discolock, TreantDruid, and PirateDH follow as load-safe partial rows; they are
promotion targets only after the listed exact source or card-specific guide gaps
close.

After durable Boarlock and Kingslayer preservation, the current actionable
source-informed closure targets are the four partial representative rows above.
They must remain `SOURCE_BACKED_PARTIAL` until new exact source evidence closes
their first missing chain.

Do not widen the matrix to a twelfth deck to avoid these rows. Either close the first missing chain with deck-specific source evidence and runtime-surface lowering, or preserve the row as a visible source-informed control.

Source candidate proof decks live in `docs/operator/source-candidate-proof-decks.json`.
Supplemental proof decks live in `docs/operator/supplemental-proof-decks.json` and do not change the representative matrix count.

## Current Blocker Snapshot

Fresh no-apply runs with
`hsconfig configure --online-source --auto-source --current-date 2026-07-18`
for the 12 user-supplied Wild decks show every package as `VALID_PACKAGE`.
Every row keeps `source_status_apply_blocking=false` and
`default_only_runtime_surfaces=[]`. Source strength remains diagnostic-only:
`READY_TO_APPLY_WITH_WARNINGS` stays the runtime readiness, while
`first_missing_source_action` stays a source-closure action.

| Deck | Strong contract status | First missing chain | Next action |
|---|---|---|---|
| ShadowPriest | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| CtAPaladin | `SOURCE_BACKED_PARTIAL` | card-specific or explicit mulligan/source claim still missing | `add_card_specific_source_claim` |
| PirateRogue | `SOURCE_BACKED_PARTIAL` | card-specific mulligan or role source still missing | `add_card_specific_source_claim` |
| BigShaman | `SOURCE_BACKED_PARTIAL` | exact combo sequence timing/details still missing | `add_exact_combo_sequence_claim` |
| Discolock | `SOURCE_BACKED_PARTIAL` | card-specific discard/mulligan source still missing | `add_card_specific_source_claim` |
| TreantDruid | `SOURCE_BACKED_PARTIAL` | card-specific Treant role/setup source still missing | `add_card_specific_source_claim` |
| ImbueMage | `SOURCE_BACKED_PARTIAL` | explicit mulligan source still missing | `add_explicit_mulligan_source` |
| MechPala | `SOURCE_BACKED_PARTIAL` | card-specific Mech Paladin source still missing | `add_card_specific_source_claim` |
| Kingslayer | `SOURCE_BACKED_PARTIAL` | Quick Pick / weapon role or mulligan source still missing | `add_card_specific_source_claim` |
| Boarlock | `SOURCE_BACKED_PARTIAL` | source-to-runtime chain still visible but not Strong-closed | `close_first_missing_chain` |
| PirateDH | `SOURCE_BACKED_PARTIAL` | card-specific source claims needed for low-confidence or uncovered rows | `add_card_specific_source_claim` |
| CuteWarrior | `SOURCE_BACKED_PARTIAL` | current card-specific/full-text Warrior source still missing | `add_card_specific_source_claim` |
