## Task 5 Report: Operator Docs And Skill Guidance For Strong-But-Honest Source Closure

Status: DONE

### Scope Completed

- Documented `evergreen_wild_archetype` as a source lane in `docs/operator/guide-research-policy.md`.
- Documented the Evergreen Wild guide rule for `SOURCE_BACKED_STRONG`: current guide evidence or qualifying full-text public Wild archetype guide evidence can contribute only when deck/archetype match and explicit card overlap are present.
- Documented that old non-Wild guides, snippets, decklists, aggregate stats, and static databases are support or diagnostic evidence and must not prove strategic runtime surfaces by themselves.
- Documented that HearthstoneJSON/static records can support deterministic CardID/effect rows such as `hero_power_transform`, but must not create opening-hand Mulligan keeps without an explicit mulligan claim.
- Updated the repo-local HSConfig skill with the same compact operating rule.
- Updated the repo-local skill reference `references/guide-research-policy.md` so agents reading the referenced policy see the same Evergreen Wild closure boundary.
- Synced the installed HSConfig skill from the repo-local source.

### Test Evidence

1. RED docs test:
   `python -m pytest tests/test_docs_active_path.py::test_guide_research_policy_documents_evergreen_wild_source_closure -q`
   Result: failed before docs update because `evergreen_wild_archetype` was missing.
2. Isolated docs test:
   `python -m pytest tests/test_docs_active_path.py::test_guide_research_policy_documents_evergreen_wild_source_closure -q`
   Result: `1 passed in 0.10s`
3. Skill sync:
   `python scripts/sync_installed_skill.py`
   Result: installed skill synced to `C:\Users\darbo\.codex\skills\hsconfig`.
4. Skill sync check:
   `python scripts/sync_installed_skill.py --check`
   Result: installed skill is in sync.
5. Docs suite:
   `python -m pytest tests/test_docs_active_path.py -q`
   Result: `37 passed in 0.13s`
6. Review-fix RED guard:
   `python -m pytest tests/test_docs_active_path.py::test_guide_research_policy_documents_evergreen_wild_source_closure tests/test_skill_files.py::test_skill_source_policy_documents_evergreen_wild_closure_boundary -q`
   Result: failed before the reference sync fix because `full-text public Wild guide` and `evergreen_wild_archetype` were not protected across the active docs and skill reference.
7. Review-fix docs and skill suite:
   `python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py -q`
   Result: `93 passed in 0.28s`
8. Review-fix skill sync check:
   `python scripts/sync_installed_skill.py --check`
   Result: installed skill is in sync.

### Constraints Preserved

- `operator_summary.json` remains the only normal apply authority.
- Source closure remains diagnostic and does not create a second gate.
- Weak source coverage remains non-blocking for valid decks.
- The docs do not turn static card text, aggregate stats, decklists, snippets, or policy fallback into strategic runtime proof.
