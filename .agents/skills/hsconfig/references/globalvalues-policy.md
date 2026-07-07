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
- Use `runtime_evidence_required` for keys that require HSTuner or other runtime evidence before changing.
- Treat GlobalValues reports as supporting evidence for `operator_summary.json`, not as a separate apply gate.
- Validate with both baseline and profile before apply.
