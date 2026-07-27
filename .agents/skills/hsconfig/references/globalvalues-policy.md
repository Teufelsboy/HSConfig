# GlobalValues Policy

`GlobalValues.json` is mandatory.

Rules:

- Start from the active runtime baseline at `CustomConfig/default/GlobalValues.json` or `CustomConfig/Default/GlobalValues.json` when available.
- Runtime baselines may contain UTF-8 BOMs, trailing commas, or simple numeric expressions from HearthRanger-edited files; load and profile the baseline instead of hand-normalizing it.
- Use the bundled fallback baseline only for preview/CI when no runtime default exists, and record that fallback source in reports.
- Preserve every loaded baseline key.
- Profile every key as changed, confirmed, or blocked.
- Write only the compiled config to runtime.
- Write the loaded baseline under `reports/globalvalues_baseline.json`.
- Write the baseline source under `reports/globalvalues_baseline_receipt.json`.
- Write the profile under `reports/globalvalues_profile.json`.
- Write the key authority profile under `reports/global_values_key_profile_report.json`.
- Record `authority_category` and `board_value_component` for every key.
- Use `copy_baseline` for keys that HSConfig must preserve unchanged.
- Use `step1_posture_overlay_allowed` only for source-backed Step1 posture keys.
- Only `gameplan_posture` may drive Step1 GlobalValues posture overlays.
- Infer the effective legacy claim kind before stripping authority-bearing
  fields. Untyped posture prose cannot mint a source receipt.
- Evaluate document and claim source identities additively. Any explicit
  official, static, statistical, or otherwise non-guide signal vetoes
  public-guide authority.
- Keep the canonical non-plan claim bundle, live-verified receipts, lifecycle, and
  source audit as package truth. Imported plan claims, rows, and receipts stay
  in diagnostic-only `plan_input_diagnostics.json`.
- Re-gate imported plan rows against canonical lifecycle, the target
  fingerprint, and verified receipts. Preserve key, operation, overlay, value,
  and claim references when suppressing a noncanonical row.
- Treat malformed, boolean, negative, or container-shaped exact-evidence
  counts as missing authority: keep baseline values and emit visible
  suppression.
- `globalvalue_numeric_tuning` is accepted source evidence for explicit numeric
  recommendations, but it is `runtime_evidence_required` and must remain
  blocked/report-visible until runtime evidence owns it.
- Do not use generic `globalvalue_*` claim kinds.
- Use `runtime_evidence_required` for keys that require HSTuner or other runtime evidence before changing.
- Treat GlobalValues reports as supporting evidence for `operator_summary.json`, not as a separate apply gate.
- Validate with both baseline and profile before apply.

## ShadowPriest Authority Boundary

| Source claim | GlobalValues authority | Constraint |
| --- | --- | --- |
| `hero_power_transform` | none | CardID effect semantics only. |
| `exact gameplan_posture` | aggressive posture overlay | Requires the four-part public-guide contract plus canonical exact-deck fingerprint evidence matching the current target. |
| `archetype-only gameplan_posture` | baseline only | Keep validated posture values unchanged. |

`hero_power_transform` does not authorize aggressive GlobalValues by itself.
The exact source `SW_448` -> `hero_power_transform` -> runtime owner
`EX1_625t` identity owns one physical `CardID/EX1_625t.json` Hero Power bonus; it
does not authorize a Darkbishop body priority, a Mulligan keep, or a
GlobalValues posture change. The numeric bonus is configuration policy, not
proof of optimal play. A neutral generated `MyHeroPowerValue=1.00` may
fill a missing registered baseline key, but it is not an aggressive overlay.
Archetype-only posture claims are suppressed visibly and cannot change posture.
An asserted `deck_match_scope=exact_deck_matched` without matching
`deck_match.exact_deck_evidence`, or without a current target deck fingerprint,
also fails closed and remains visible as suppressed.

## Audited Deck-set Boundary

The read-only twelve-deck acceptance keeps GlobalValues authority narrow:
Boarlock may not gain `MyHeroPowerValue` without authority, Discolock must keep
empty authorized/emitted overlay parity for its audited fixture, and the
ShadowPriest linked Hero Power effect does not grant a posture overlay. The
fixture manifests classify proof scope only; they are not an apply gate.
Current apply authority remains the package's `reports/operator_summary.json`.

Captured and fixture-backed rows remain diagnostic-only even when strict
validation passes. The separate positive fixture must enter through exact
`live_http` / `live_verified` acquisition and pass current strict package
validation before it can be technically eligible. This pre-run acceptance does
not prove in-client execution, gameplay improvement, or optimality.
