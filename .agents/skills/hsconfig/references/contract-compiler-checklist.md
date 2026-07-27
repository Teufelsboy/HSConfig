# Contract Compiler Checklist

Use this checklist before generated config handoff, source-depth work, or runtime-facing apply review. It is not another operator gate; it is the compact pre-run contract the skill follows before reading detailed references.

1. Currentness gate: run `git fetch --all --prune --tags`, `python scripts/check_hsconfig_currentness.py --cwd . --json`, and `git status --short --branch` before runtime-facing work.
2. Source gate: candidate registries and `source_closure_intake_receipt.json` are acquisition input only; they cannot promote, block, write runtime config, or replace `reports/operator_summary.json`.
3. Claim gate: source text must normalize to an explicit `claim_kind`; effect relevance, guide importance, and archetype value do not bypass claim-kind or surface gates.
4. Runtime gate: normal output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact ordered combo evidence.
5. Quality gate: no silent default-only runtime success; every expected surface is emitted, explicitly suppressed, or reported as a visible source/action gap.
6. Strong gate: `SOURCE_BACKED_STRONG` requires honest source closure and `default_only_runtime_surfaces=[]`; it is not needed for load-safe apply.
7. No-block gate: source warnings, warning-only mechanics, unresolved options, and thin guide coverage do not block a technically valid load-safe package.
8. Operator gate: open `reports/operator_summary.json` first; it remains the only normal apply authority.
9. Darkbishop gate: preserve `SW_448` hero-power-transform semantics, but do not emit a Mulligan keep without explicit opening-hand source text.
10. Boundary gate: do not add `Presume.json`, `Concede.json`, aggregate `CardBehavior.json`, replay parsing, winrate analysis, HSTuner tuning, or gameplay sequencing logic.

## Authority Hardening

- Only `live_http` plus `live_verified` provenance can mint strategic receipts; captured, fixture, manual, and legacy inputs are diagnostic only for strategic authority.
- Static semantics can support deterministic CardID/effect claims but can never authorize strategic Combo order.
- `reports/operator_summary.json` is the sole human-facing verdict; never infer apply readiness from individual diagnostic reports.
- Unverified deck input blocks apply, and package derivation is recomputed before write authorization.
- `SW_448` causes `hero_power_transform`; `EX1_625t` owns the physical Mind Spike behavior row.
- Offline tests prove neither in-client behavior nor gameplay optimality.

## Semantic Handoff Safety

- `SOURCE_BACKED_STRONG` proves source closure only. It is necessary but not sufficient for semantic handoff.
- Read `semantic_handoff_status` and `semantic_handoff_reasons` before describing a package as semantically closed.
- Never lower generic gameplay “keep” prose into `Mulligan.json`; explicit opening-hand or Mulligan context is required.
- Reject the whole runtime row when any structured condition atom is unsupported.
- Targeting claims count as closed only when target scope and a compatible target surface are both encoded.
- Do not emit generic `InHandPlayPriority` or `BeforePlayCardBonus` rows solely to make every-card coverage appear complete.
- `reports/operator_summary.json` remains the only normal apply authority.
- `semantic_handoff_status` is diagnostic and never creates a second apply gate.

## Report Order

1. `reports/operator_summary.json`
2. `reports/source_to_runtime_explainability.json`
3. `reports/source_evidence_closure.json`
4. `reports/source_contract_audit.json`
5. `reports/per_card_config_readiness_report.json`
6. `reports/guide_source_depth_report.json`
7. `reports/strong_promotion_report.json`
8. `reports/card_behavior_plan_report.json`
9. `reports/mulligan_plan_report.json`
10. `reports/global_values_authority_matrix.json`

`operator_summary.json` remains the only normal apply authority.
`source_contract_audit.json` is diagnostic.
`source_to_runtime_explainability.json` is diagnostic.
`source_evidence_closure.json` is diagnostic.

## Non-Goals

HSConfig does not parse replays.
HSConfig does not inspect winrate.
HSConfig does not analyze runtime logs.
HSConfig does not tune after games.
HSConfig does not replace HearthRanger gameplay decisions.
