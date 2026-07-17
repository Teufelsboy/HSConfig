# HSConfig Current Truth Index

Research artifacts are evidence, not operator instructions.

Normal operator path starts at `docs/operator/README.md`.

After durable Boarlock and Kingslayer preservation, the current actionable source-informed closure targets are CtAPaladin, Discolock, TreantDruid, and PirateDH.

## 2026-07-11 Surface authority split

Current HSConfig truth: source claims are normalized first, then lowered through
surface-specific authority gates. This preserves no-block deck generation while
preventing source-backed effects such as Darkbishop Benedictus start-of-game
Hero Power transformation from becoming false opening-hand Mulligan keeps.

## How To Read Historical Evidence

Active docs win over historical evidence. Do not start a new architecture wave from superseded research alone. Use real deck output or live mechanic drift as the trigger for new implementation work.

Older research packages can explain why a decision happened, but they do not override the operator path, installed skill, or universal Wild no-block contract. If old evidence mentions normal `Presume.json`, `Concede.json`, replay tuning, winrate gates, or candidate promotion, treat that as historical context unless the active docs explicitly reintroduce it.

## Research Snapshot Status Sync

Use `hsconfig research-status-sync --package <04_package> --research-results-dir <results>`
when `research-deep` JSON files appear to disagree with a prepared package.
Research artifacts are evidence history, not operator instructions. Historical
research snapshots can be stale or seed-only; research snapshots do not downgrade canonical package status, and they do not promote partial packages.
They can recommend a refresh action for docs/research hygiene only.
They do not create apply authority. `operator_summary.json remains the only
normal apply authority`.

## Current Active Evidence

- `2026-07-14-hsconfig-source-contract-logic-guardrail-audit`: Contract-spine Guardrail v2 evidence. Confirms the current two-lane model: technical load safety decides normal apply, while source-contract, source-to-runtime, and mechanic warnings stay diagnostic and non-blocking.

| Package | Role | Current implication |
| --- | --- | --- |
| `docs/research/2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm/` | Source-contract spine evidence | Keep source truth separate from runtime authority: `claim_kind` routes through policy, surface gates, builder/router decisions, and diagnostics; operator_summary.json remains the only normal apply authority. |
| `docs/research/2026-07-12-hsconfig-source-contract-spine-brainstorm/` | Contract-spine freeze and no-second-gate evidence | Keep `operator_summary.json` as the normal apply authority; `source_contract_audit.json` and `contract_spine_rows` remain diagnostic explanations of source -> policy -> surface gate -> builder/router -> runtime effect. |
| `docs/research/2026-07-11-hsconfig-source-contract-logic-audit/` | Source and runtime contract evidence | Treat `claim_kind` as semantic input to the runtime surface gates; broad guide text and start-of-game effects must not become Mulligan keeps without explicit mulligan claims. |
| `docs/research/2026-07-11-hsconfig-post-hardening-skill-audit/` | Post-hardening skill audit evidence | Keep the current lean HSConfig boundary, correct Presume surface wording, preserve no-block apply behavior, and use real decks for targeted defects instead of another broad architecture wave. |
| `docs/research/2026-07-11-hsconfig-current-skill-audit/` | Current skill contract and slimness evidence | Keep HSConfig narrow; harden the no-block apply gate with executable tests, correct Presume/Concede wording, and keep the active skill/workflow docs compact. |
| `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/` | No-block universal skill posture evidence | Add visibility-only warning rows for `rewind`, `herald`, and `shatter`; keep the normal package path limited to load-safe HSConfig surfaces. |
| `docs/research/2026-07-10-hsconfig-post-contract-closure-skill-audit/` | Post-contract no-block cleanup evidence | Keep the core apply gate unchanged; runtime hard blocks are technical only, per-card-every-card coverage is HSConfig rich output, and source-strength gaps are promotion/richness gaps. |
| `docs/research/2026-07-09-hsconfig-next-recommendation-mechanic-polish/` | Visibility-only Mechanic Polish | Add non-blocking mechanic visibility for `choose_one`, `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool`; do not change apply gates. |
| `docs/research/2026-07-09-hsconfig-current-no-block-wild-mechanic-audit/` | No-block Wild mechanic evidence | Valid deck packages should stay load-safe even when mechanic semantics are report-only. |
| `docs/research/2026-07-09-hsconfig-universal-no-block-skill-audit-v2/` | Universal no-block evidence | The no-block promise is implemented through warning visibility, not through broader runtime writes. |

- `2026-07-11-hsconfig-live-skill-audit`: Live skill audit evidence. Confirms HSConfig is ready for real-deck usage with narrow polish only: normal runtime surface unchanged, `hsconfig configure` preferred, warning-only mechanics remain non-blocking, and Presume/Concede stale citation notes are superseded by the active operator docs and runtime-surface audit.

- `2026-07-10-hsconfig-universal-no-block-skill-audit-v5` - No-block failure-mode summary evidence.
  Confirms that the next narrow improvement is
  an operator-facing `no_block_failure_mode_summary`, not a broader apply gate,
  new representative decks, or post-run HSTuner scope.

- `2026-07-10-hsconfig-mechanic-lowering-parity-wave` - Mechanic lowering parity evidence.
  The mechanic lowering registry is the executable authority:
  lowerable mechanics with documented CardID targets should emit rows or
  `cards_needing_mechanic_lowering`; report-only mechanics such as Dredge,
  Tradeable, and unknown future mechanics remain warning-only and non-blocking.

## 2026-07-10 No-Block Universal Skill Audit V4

- Path: `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/`
- Role: active evidence for no-block universal skill posture, modern mechanic visibility, and public VisionAI surface boundaries.
- Operator implication: add visibility-only warning rows for `rewind`, `herald`, and `shatter`; keep the normal package path limited to load-safe HSConfig surfaces.
- Boundary: research artifacts are evidence, not operator instructions.

## 2026-07-12 Source-Contract Spine Truth

Active research package:
`docs/research/2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm/`.

This package is the current source-contract spine reference for HSConfig. It
confirms that source claims route through `claim_kind`, the policy matrix,
surface gates, builder/router decisions, and diagnostic reports before any
runtime package is considered. `operator_summary.json remains the only normal
apply authority`.

Research and diagnostics explain source quality and runtime-surface decisions;
they do not authorize runtime writes. A valid package may still be
`READY_TO_APPLY_WITH_WARNINGS` when source debt is visible but the runtime
package is load-safe.

## Superseded Evidence

Older packages remain useful background, but they are not normal operator guidance. When a claim conflicts with `docs/operator/README.md`, `.agents/skills/hsconfig/SKILL.md`, or `docs/operator/universal-wild-no-block-contract.md`, the operator and skill documents win.
