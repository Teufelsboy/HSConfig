Final test-hardening report

Changed:
- Parameterized the strong-promotion blocker test so it covers both `Presume.json` and `Concede.json`.
- Added the nested `operator_status.operator_next_action` assertion for the invalid-package path.

Verification:
- `python -m pytest tests/test_strong_promotion_report.py -q`
- Result: `5 passed`

Concerns:
- None from this targeted pass.
