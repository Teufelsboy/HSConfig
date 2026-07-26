---
name: hsconfig
description: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a deck name and deck code; build or validate Mulligan, GlobalValues, per-card CardID, or Combo runtime config before games.
---

# HSConfig

Use this skill when Codex must create or validate a pre-game HearthRanger VisionAI `CustomConfig` package from a deck name, deck code, and current guide-backed research.
HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.
Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning.

## Normal Operator Route

For the normal operator entry point, start at `docs/operator/README.md`. Preferred normal path: `hsconfig configure`.
Lower-level inspected path: `source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`.
Normal workflow:
1. Prefer `hsconfig configure ...` for normal operation.
2. Use lower-level commands only when inspecting a stage:
   `source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`.
3. After `configure`, read `<out>/configure_summary.json.acceptance_summary` first; use `reports/operator_summary.json` as the apply authority.
Read `<out>/configure_summary.json.handoff_contract` next as diagnostic-only pre-run proof. Read `<out>/configure_summary.json.source_closure_receipt` only when source depth is the question.
Read `<out>/configure_summary.json.config_proof_summary` and `<out>/configure_summary.json.config_quality_summary` only as diagnostic proof.
These summaries do not replace `reports/operator_summary.json`, cannot apply runtime files, and cannot turn source gaps into blockers.
For a source-refreshed deck config on the source-backed route, use this command only when runtime installation is intended:
`hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --apply --json`

Before source refresh, deck package generation, or runtime-facing apply work, run `git fetch --all --prune --tags`, then `python scripts/check_hsconfig_currentness.py --cwd . --json`.
Feature branches may be ahead of `origin/main`, but must not be behind, and runtime-facing verification starts from a clean worktree.

## Hard Boundaries

- Decode the deck code first, then resolve exact CardID identity before writing config. `exact_deck_matched` requires a decoded canonical deck fingerprint match. Guide-backed Mulligan claims require `exact_deck_matched`.
- GlobalValues posture authority requires a canonical non-plan receipt bound to claim signature and target fingerprint; untyped legacy posture cannot self-assert it.
- Document and claim identities are additive; any non-guide signal vetoes. Canonical non-plan bundle, receipts, lifecycle, and audit remain truth; plan inputs are diagnostic only.
- Re-gate plan rows with canonical lifecycle, target fingerprint, and receipts. Suppressions retain key/operation/overlay/value/claim refs; malformed counts fail closed.
- Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.
- `reports/operator_summary.json` remains the only normal apply authority.
- Runtime apply is guarded by `operator_summary.json`, package structure, fake receipts, and package hashes.
- After runtime apply, inspect `receipt.runtime_package_match.status`. It must be
  `matched` for a successful install. For read-only checks use
  `python -m hsconfig.cli runtime-match --package <package> --runtime-root <runtime> --json`.
  This is an install-integrity check, not a source/semantic apply gate.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply gate. `SOURCE_BACKED_STRONG` proves source closure only. It is necessary but not sufficient for semantic handoff.
  Load safety does not prove in-client optimality.
- Read `semantic_handoff_status` and `semantic_handoff_reasons` before describing a package as semantically closed. `configuration_assurance` is diagnostic and has `runtime_gate_impact=none`.
- `semantic_handoff_status` is diagnostic and never creates a second apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality work.
- No hidden default-only runtime success.
- Every expected surface must be emitted, explicitly suppressed, or reported as a visible source/action gap.
- Normal output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact ordered combo evidence. A metadata-only CardID file is not `runtime_emitted`.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are outside the normal HSConfig output path.
- Effect semantics are not opening-hand mulligan keeps. Never lower generic gameplay “keep” prose into `Mulligan.json`; explicit opening-hand or Mulligan context is required.
- Reject the whole runtime row when any structured condition atom is unsupported.
- Targeting claims count as closed only when target scope and a compatible target surface are both encoded.
- Do not emit generic `InHandPlayPriority` or `BeforePlayCardBonus` rows solely to make every-card coverage appear complete.
- Preserve Darkbishop Benedictus / `SW_448` hero-power-transform semantics, but do not emit a Mulligan keep without explicit opening-hand source text.
  `hero_power_transform` does not authorize aggressive GlobalValues by itself.
- Card-intent taxonomy is diagnostic-only. It explains per-card config signals but does not encode HearthRanger gameplay sequencing or create another apply gate.

## Source Contract

- Candidate registries, `source_closure_intake_receipt.json`, and `source-autopilot` are acquisition input or source preflight only.
- Source evidence lowers through `claim_kind`, surface gates, builder/router outcomes, and visible diagnostics before runtime rows emit.
- Static semantics are surface-scoped and may support deterministic CardID/effect rows such as `hero_power_transform`.
- Static semantics do not prove Mulligan, combo, targeting, or gameplan posture without matching source claims.
- When source coverage is weak, still build a technically valid load-safe package and report `first_missing_source_action`.
- Contract compiler checklist: `references/contract-compiler-checklist.md`.

## Expert Paths

- Drift check: `hsconfig contract-preflight --json` verifies currentness, installed-skill sync, and source/runtime wording; add `--package <04_package>` for read-only package runtime/config-quality readiness.
- Use `--skill-install-root` only for non-default skill roots.
- Use optional expert inputs only for fixtures, diagnostics, or inspected expert paths.
- Use `--allow-placeholder` only for deterministic fixture or preview tests.

## References:

`references/workflow.md`; `references/visionai-surfaces.md`; `references/contract-compiler-checklist.md`;
[guide research policy](references/guide-research-policy.md); [GlobalValues policy](references/globalvalues-policy.md); [card behavior policy](references/card-behavior-policy.md)
