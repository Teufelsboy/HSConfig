# Final Fix Report

## 2026-07-07 - HSConfig Source-Backed Archetype Fixture Wave

Status: fixed and verified.

Commit: `e5f20d4` (`fix: avoid unsupported fixture mulligan lowering`)

Changes:
- Kingslayer Quick Pick (`DEEP_014`) mulligan evidence is downgraded to low/report-only because the linked Kingsbane guide supports Kingsbane, Kingsbane tutors, and Silverleaf Poison, not Quick Pick.
- Imbue Mage mulligan evidence now uses `EDR_852` Bitterbloom Knight, a guide-named key Imbue enabler that exists in the decoded fixture deck.
- Added fixture regression coverage proving the Kingslayer low-confidence Quick Pick claim is suppressed from runtime mulligan rules and Imbue Mage runtime mulligan keeps stay within the source-named Imbue enabler set.

Tests:
- `python -m pytest tests/test_archetype_source_fixtures.py::test_kingslayer_unsupported_quick_pick_mulligan_claim_does_not_lower tests/test_archetype_source_fixtures.py::test_imbuemage_mulligan_keeps_use_source_named_imbue_enablers -q`
  - Red before fixture patch: failed on Quick Pick being `guide_backed` and Wildfire (`BAR_546`) lowering as a source-claim hold.
  - Green after fixture patch: 2 passed in 10.24s.
- `python -m pytest tests/test_archetype_source_fixtures.py tests/test_archetype_fixture_e2e.py -q`: 23 passed in 17.22s.
- `python -m pytest -q`: 305 passed in 65.88s.
- `git diff --check -- tests/fixtures/source_documents_kingslayer_strong.json tests/fixtures/source_documents_imbuemage_strong.json tests/test_archetype_source_fixtures.py tests/test_archetype_fixture_e2e.py`: exit 0; Git printed LF-to-CRLF working-copy warnings only.

Concerns:
- The Kingsbane guide's source-supported mulligan cards are not present in the decoded HSConfig Kingslayer fixture deck, so the fixture now keeps the Quick Pick mulligan note report-only and emits no source-claim Mulligan.json hold for `DEEP_014`.

## 2026-07-09 - HSConfig research truth and warning boundary guidance

Status: fixed and verified.

Commit: `fix: align research truth and warning boundary guidance`

Changes:
- `docs/research/README.md`
- `docs/operator/README.md`
- `.agents/skills/hsconfig/SKILL.md`
- `.agents/skills/hsconfig/references/workflow.md`
- `tests/test_docs_active_path.py`
- `tests/test_skill_files.py`

Tests:
- `$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py -q` -> `39 passed in 0.26s`
- `$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py -q` -> `39 passed in 0.18s`

Concerns:
- Pre-existing untracked research directories under `docs/research/` were left untouched.
