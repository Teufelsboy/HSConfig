# Task 10 Report — Twelve-Deck Read-Only Acceptance

Added one manifest-driven acceptance matrix for the complete audited deck set:
the 11 representative configurations plus the supplemental CuteWarrior
configuration.

Implemented:

- Added `tests/test_audited_deck_set_acceptance.py` with a unique twelve-deck
  catalog assembled from the representative and supplemental manifests.
- Prepared all diagnostic/captured packages only below pytest temporary
  directories and asserted their current read-only authority:
  technically valid, load-safe fixtures remain
  `runtime_apply_mode=blocked`, `runtime_apply_allowed=false`, and
  `fixture_runtime_apply_authority=diagnostic_only`.
- Added global semantic checks for physical CardID/report parity, runtime-owner
  source evidence, unsupported-condition suppression, and the prohibition on
  spell-owned `OnBoardBonus` or `BeforeBattlecryTargetBonus`.
- Added deck-specific acceptance for ShadowPriest, MechPala, Kingslayer,
  Boarlock, Discolock, and ImbueMage, including linked-owner, sideboard,
  hold/block, Combo, GlobalValues, and physical Mulligan identity boundaries.
- Added a positive exact-deck source case through the real online acquisition
  pipeline with the network transport monkeypatched locally. It proves that a
  `live_http`/`live_verified` package can pass strict validation and the sole
  operator apply gate without performing a runtime write.
- Added a strict-validation mutation case proving that removing the generated
  GlobalValues profile blocks both validation and current-package apply
  authority.
- Updated the existing strong-fixture closure expectations to the Task 9
  diagnostic-source contract and removed one stale mechanic-lowering count that
  was unrelated to the closure/read-only purpose of that suite.
- Documented the acceptance boundary in the operator guide, installed skill
  source, and the CardID, GlobalValues, and VisionAI policy references.

TDD evidence:

- Initial RED run: `4 failed, 9 passed`.
- After correcting the acceptance representation to the existing runtime
  contract, the new suite passed: `13 passed`.

Verification:

- Required focused matrix:
  `45 passed, 11 skipped`.
- Full contract guardrail: `949 passed`; installed-skill sync,
  contract-spine sentinel, and focused boundary checks all reported `OK`.
- Installed skill was synchronized using the repository script, then verified
  byte-for-byte for all changed skill files and with `--check`.
- Targeted Ruff: clean.
- `git diff --check`: clean apart from Git's existing LF-to-CRLF notices.

This acceptance is intentionally read-only. It proves repository semantics,
artifact consistency, strict validation, and gate behavior; it does not prove
in-client loading, gameplay quality, optimization, or runtime write
correctness. No runtime, HSTuner, HearthRanger Desktop, or runtime write path
was used.
