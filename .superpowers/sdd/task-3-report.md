# Task 3 Report: Profile-Aware Source Autopilot

## Scope

Implemented Task 3 and the follow-up review fixes for source-autopilot Strong closure profile handling.

Changed files:

- `src/hsconfig/source_autopilot.py`
- `tests/test_source_autopilot.py`
- `tests/test_source_backed_strong_harvester_closure.py`

## Behavior

- `source_autopilot_report` routes non-closed closure profiles through `_action_from_profile_gap(...)`.
- No-strong-row source preflight no longer hardcodes `add_explicit_mulligan_source`; generic missing gameplan/card evidence reports `add_current_card_specific_runtime_source`.
- ShadowPriest-style aggro hero-power profiles can close without an extra generic apply-surface guide candidate.
- Autopilot closure detail does not claim generated-package default-only runtime surfaces were evaluated. It reports `default_only_runtime_surface_status: "not_evaluated_in_source_preflight"` and leaves runtime-surface authority to `operator_summary.json`.

## Verification

Command:

```powershell
python -m pytest tests/test_source_autopilot.py tests/test_source_backed_strong_harvester_closure.py tests/test_strong_closure_profiles.py -q
```

Result: 30 passed.

## Gate Boundary

No runtime writer path, package builder path, matrix file, docs file, skill file, or `operator_summary.json` authority path was changed. Source autopilot remains source-preflight diagnostics only.
