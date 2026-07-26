# Source Contract Spine

Diagnostic reference only.

`reports/operator_summary.json` remains the only normal apply authority.

This page explains why a source claim did or did not lower to runtime config. It is diagnostic context, not an apply authority.

## Normal Runtime Surfaces

| Surface | Use |
| --- | --- |
| `Mulligan.json` | Explicit opening-hand `mulligan_keep` and `mulligan_discard` claims only. |
| `GlobalValues.json` | Governed Step 1 posture overlays from `gameplan_posture`; numeric tuning waits for runtime evidence. |
| `Combo.json` | Explicit ordered `combo_sequence` claims only. |
| `CARDID.json` | Card-local behavior such as targeting, hero-power transform, option identity, and supported mechanic behavior. |

`Presume.json` and `Concede.json` are documented HearthRanger concepts but not normal HSConfig runtime outputs.

## Audited Semantic Closure Contract

| Contract | Authority | Outcome |
| --- | --- | --- |
| `source_identity` | decoded canonical deck fingerprint | `exact_deck_matched` |
| `mulligan_authority` | `exact_deck_matched` | guide-backed Mulligan may lower only after the complete exact-guide gate |
| `globalvalues_authority` | canonical non-plan source-document receipt bound to the exact claim signature | imported claims and plan rows cannot grant or replace posture authority |
| `hero_power_transform` | exact CardID and linked identity | CardID only |
| `metadata_only_cardid` | parsed physical `values` row | not `runtime_emitted` |
| `load_safety` | strict package validation | in-client optimality remains unproven |
| `configuration_assurance` | diagnostic projection | `runtime_gate_impact=none` |

`exact_deck_matched` requires a decoded canonical deck fingerprint match.
Guide-backed Mulligan claims require `exact_deck_matched`.
GlobalValues posture also requires the canonical source-document receipt; all
explicit provenance signals must agree that the source is a public guide.
Plan-report GlobalValues rows are rebuilt from that receipt, never accepted by
Claim ID alone.
`hero_power_transform` does not authorize aggressive GlobalValues by itself.
A metadata-only CardID file is not `runtime_emitted`.
Load safety does not prove in-client optimality.
`configuration_assurance` is diagnostic and has `runtime_gate_impact=none`.

## GlobalValues Plan Trust Boundary

| Boundary | Canonical input | Required outcome |
| --- | --- | --- |
| `legacy_claim_inference` | effective claim kind before authority-field stripping | untyped posture text cannot mint a source receipt |
| `identity_signal_layers` | document and claim identity signals together | any explicit non-guide signal vetoes public-guide authority |
| `bundle_receipt_truth` | non-plan source-document bundle and verified receipts | plan bundle and plan receipts cannot replace package truth |
| `plan_input_diagnostics` | imported plan claims, rows, and receipts | diagnostic only with `runtime_gate_impact=none` |
| `plan_revalidation` | canonical lifecycle, target fingerprint, and verified receipts | only canonical rows may lower |
| `suppression_transparency` | key, operation, overlay, value, and claim references | rejected plan attempt remains reconstructible |
| `exact_evidence_counts` | non-negative integer evidence | malformed counts fail closed to baseline and visible suppression |

The canonical non-plan `guide_claim_bundle.json`, verified source receipts,
claim lifecycle, and `source_contract_audit.json` remain package truth. An
imported plan bundle is recorded separately as input diagnosis and never
replaces those surfaces. A plan row that does match canonical truth must pass
the same lifecycle, target-fingerprint, and receipt gate; the import path must
not add a false missing-receipt suppression to that valid row.

## ShadowPriest Runtime Surfaces

| Semantic family | Identity | Runtime surface | Boundary |
| --- | --- | --- | --- |
| `hero_power_transform` | `SW_448 -> EX1_625t` | one `BeforeUseHeroPowerBonus` | No Darkbishop body priority and no inferred Mulligan keep. |
| `gameplan_posture` | separate exact guide claim | `GlobalValues.json` posture overlay | The Hero Power transform alone has no aggressive GlobalValues authority. |
| `summon_trigger_board_engine` | Treasure Distributor or Ship's Chirurgeon | `OnBoardBonus` | Board engine value only; it does not claim the card summons a minion. |
| `reciprocal_hero_burn` | reciprocal health effect | report-only | Self-health safety is not proven by the supported condition grammar. |

Other state-dependent mechanics remain report-only until a documented
deterministic condition exists.

## Physical Runtime Row Contract

| Concept | Shape | Result |
| --- | --- | --- |
| `runtime_key` | `(card_id, behavior_block, condition)` | one physical owner per runtime slot |
| `full_signature` | `(card_id, behavior_block, condition, value)` | canonical emitted-row identity |
| `duplicate_provenance` | identical full signature | merge and sort provenance |
| `conflicting_values` | same runtime key with different values | fail closed; suppress physical row |
| `physical_report_parity` | physical CardID `values` versus meaningful card-behavior report rows | exact row parity required |

Equivalent physical rows emit once while their source claim IDs, source
references, and lifecycle claim IDs merge deterministically. Conflicting values
must stay visible in diagnostics and must not reach runtime output. Reports may
call a CardID row `runtime_emitted` only when the parsed physical payload
contains the matching non-metadata `values` row. Every physical CardID `values`
row must correspond to one meaningful card-behavior report row, and every such
meaningful report row must correspond to physical output.

## Configuration Assurance

| Field | Contract value | Meaning |
| --- | --- | --- |
| `load_safety` | `validated` or `not_validated` | Technical package validation only. |
| `source_authority` | `exact`, `archetype_only`, `partial`, or `unknown` | Source scope, separate from load safety. |
| `semantic_closure` | current `semantic_handoff_status` | Diagnostic semantic state. |
| `in_client_behavior` | `not_proven_by_pre_run_contract` | No in-client behavior proof. |
| `optimality_claim_allowed` | `false` | Pre-run output cannot claim optimality. |
| `runtime_gate_impact` | `none` | Assurance never changes apply permission. |

## Claim-Kind Spine

| Claim Kind | Lane | Runtime Surface | Boundary |
| --- | --- | --- | --- |
| `archetype` | report_only | none | Context only; not a runtime row. |
| `mulligan_keep` | runtime_lowerable | `Mulligan.json` | Requires explicit opening-hand keep intent. |
| `mulligan_discard` | runtime_lowerable | `Mulligan.json` | Requires explicit opening-hand discard intent. |
| `card_role` | suppressed_or_conditional | `CARDID.json` | Requires supported card behavior surface. |
| `targeting_rule` | runtime_lowerable | `CARDID.json` | Requires supported target and block identity. |
| `combo_sequence` | runtime_lowerable | `Combo.json` | Requires complete ordered sequence. |
| `gameplan_posture` | runtime_lowerable | `GlobalValues.json` | Posture overlay only; not numeric runtime tuning. |
| `hero_power_transform` | suppressed_or_conditional | `CARDID.json` | Preserves effect semantics; not a mulligan keep by itself. |
| `mechanic_usage` | suppressed_or_conditional | `CARDID.json` | Requires documented CardID surface. |
| `known_bad_pattern` | suppressed_or_conditional | `CARDID.json` | Requires supported negative behavior row. |
| `tech_slot` | report_only | none | Deck construction advice only. |
| `replacement_option` | report_only | none | Deck replacement advice only. |
| `discover_choice` | suppressed_or_conditional | `CARDID.json` | Requires exact Discover option identity. |
| `choose_one_choice` | suppressed_or_conditional | `CARDID.json` | Requires exact Choose One option identity. |
| `globalvalue_numeric_tuning` | runtime_evidence_required | none | Requires runtime evidence before numeric write. |

## False-Lowering Boundaries

- Start-of-game effects are not opening-hand mulligan keeps unless the source explicitly says to keep the card in the opening hand.
- Deckbuilding effects are contract evidence, not live runtime actions.
- Discover and Choose One claims need exact option identity before lowering.
- Generated random pools stay report-visible unless the generated entity is deterministic.
- Secret timing, location activation, weapon attack posture, Titan choices, Tourist deckbuilding, Imbue, Forge, Excavate, and unknown mechanics stay warning/report-first until a deterministic runtime mapping exists.

Warnings are follow-up work, not runtime apply blockers.
