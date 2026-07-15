Implemented and committed Task 1.

Changed files:
- src/hsconfig/strong_closure_profiles.py
- tests/test_strong_closure_profiles.py

Validation run:
- python -m pytest tests/test_strong_closure_profiles.py -q -> 5 passed in 0.09s
- Extra smoke check -> generic_no_block, apply_blocking=False, strong_eligible=False for an unknown deck

Commit:
- 604cdab7857670d396ce27ab5c8173482dbefad0
- Message: feat: add source-backed closure profiles

Residual risk: the profile rules are intentionally minimal and isolated to the Task 1 brief. They are not yet wired into operator/autopilot surfaces, per ownership constraints.
