# Task 2 Report: Preserve Static Identity Fields And Derived Links

## Status

DONE

## Files Changed

- `src/hsconfig/hearthstonejson.py`
- `src/hsconfig/semantic_enrichment.py`
- `src/hsconfig/option_identity_resolver.py`
- `tests/test_hearthstonejson.py`
- `tests/test_semantic_enrichment.py`
- `tests/test_option_identity_resolver.py`
- `.superpowers/sdd/task-2-report.md`

## Tests Run

- `python -m pytest tests/test_hearthstonejson.py::test_normalize_card_row_preserves_identity_link_fields -q`
  - Red outcome before implementation: failed with `KeyError: 'hero_power_dbf_id'`.
  - Green outcome after implementation: passed.
- `python -m pytest tests/test_option_identity_resolver.py::test_resolve_linked_entities_from_static_identity_fields -q`
  - Red outcome before implementation: failed with `ModuleNotFoundError: No module named 'hsconfig.option_identity_resolver'`.
  - Green outcome after implementation: passed.
- `python -m pytest tests/test_semantic_enrichment.py::test_enrichment_adds_direct_hjson_linked_entities_from_hero_power_dbf_id -q`
  - Red outcome before implementation: failed with `KeyError: 'hero_power_dbf_id'`.
  - Green outcome after implementation: passed.
- `python -m pytest tests/test_hearthstonejson.py tests/test_semantic_enrichment.py tests/test_identity_graph.py tests/test_option_identity_resolver.py -q`
  - Outcome: 14 passed.
- `python -m pytest -q`
  - Outcome: 195 passed.
- `git diff --check`
  - Outcome: passed; Git reported CRLF normalization warnings only.

## Commits Created

- `feat: preserve static identity links` (final hash assigned by Git when this report is committed)

## Self-Review Notes

- `normalize_card_row` now preserves `hero_power_dbf_id`, `quest_reward`, `play_requirements`, and existing `entourage` while accepting already-normalized snake_case inputs.
- `resolve_linked_entities` derives direct link rows from `hero_power_dbf_id`, `quest_reward`, and `entourage`, with row-level `source` provenance.
- Semantic enrichment merges direct HearthstoneJSON link rows after metadata hydration and before writing `linked_entities`.
- Shadowform Mind Spike fallback remains available, but its link provenance is `builtin_shadowform_fallback` when no direct HearthstoneJSON link is present.
- No changes were made to `identity_graph.py`; existing identity graph tests still pass.
- Pre-existing untracked `docs/superpowers/plans/2026-07-07-hsconfig-source-backed-config-depth-closure.md` was left untouched.

## Concerns

- None.
