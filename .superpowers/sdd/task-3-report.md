# Task 3 Report: Semantic Scoring In Card Behavior Routing

Status: done

Files changed:
- `src/hsconfig/card_behavior_surface_router.py`
- `tests/test_card_behavior_router.py`
- `src/hsconfig/semantic_intent_score.py` (minimal integration blocker fix)
- `.superpowers/sdd/task-3-report.md`

RED summary:
- Ran `python -m pytest tests\test_card_behavior_router.py -q -p no:cacheprovider` after adding integration tests and before router implementation.
- Expected failures observed:
  - Mind Sear semantic value still returned `6` instead of `10`.
  - Explicit runtime value row kept value `8` but had no `semantic_score` metadata.

GREEN summary:
- Ran `python -m pytest tests\test_semantic_intent_score.py tests\test_card_behavior_router.py -q -p no:cacheprovider`.
- Result: `46 passed in 0.20s`.

Implementation summary:
- Imported `score_card_behavior_claim` into `card_behavior_surface_router.py`.
- `_attach_behavior_fields()` now scores accepted CardID behavior rows after behavior block, intent, roles, rule suffix, and condition are selected.
- Accepted rows receive `value` from the scorer and diagnostic `semantic_score` metadata with `band`, `reason`, `profile`, and `matched_signals`.
- Explicit source `runtime_value`/`value` still wins through the scorer and reports `reason == "explicit_runtime_value"`.
- Suppressed rows are not scored.

Scope note:
- `src/hsconfig/semantic_intent_score.py` required a minimal fix because its board-tempo rule matched `mech` inside `mechanic_usage`, causing unrelated generic mechanic rows to score as `8`. The fix now treats `mech` as a standalone token.

Commit:
- Created with message `feat: score accepted card behavior rows`; exact final HEAD hash is in the worker final answer.

Concerns:
- The branch started dirty because `.superpowers/sdd/progress.md` was already modified. It was not edited or staged by this task.
