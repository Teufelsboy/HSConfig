# GlobalValues Policy

`GlobalValues.json` is mandatory.

Rules:

- Start from the active runtime baseline at `CustomConfig/default/GlobalValues.json` or `CustomConfig/Default/GlobalValues.json` when available.
- Use the bundled fallback baseline only for preview/CI when no runtime default exists, and record that fallback source in reports.
- Preserve every loaded baseline key.
- Profile every key as changed, confirmed, or blocked.
- Write only the compiled config to runtime.
- Write the loaded baseline under `reports/globalvalues_baseline.json`.
- Write the baseline source under `reports/globalvalues_baseline_receipt.json`.
- Write the profile under `reports/globalvalues_profile.json`.
- Validate with both baseline and profile before apply.
