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

## Fix Round 1

Closed the acceptance-test confidence gaps found in quality review:

- Added a fail-closed catalog validator requiring exactly eleven representative
  rows, exactly one supplemental CuteWarrior row, exactly twelve audited rows,
  and unique non-empty deck names and deck codes.
- Added removal, duplicate-CuteWarrior, duplicate-name, and duplicate-code
  regressions so a damaged manifest cannot silently reduce or duplicate the
  audited set.
- Replaced one-way, string-normalized CardID matching with exact canonical
  typed `Counter` parity in both directions. Duplicate multiplicity and
  condition/value JSON types are preserved.
- CardID provenance is checked only after physical/report parity is proven.
  Phantom report rows, duplicate physical or report rows, condition type drift,
  and value type drift each have a synthetic fail-closed regression.
- Card types now come from `semantic_enrichment_report.json`. Both the source
  card and physical runtime owner are checked for the two spell-forbidden
  surfaces, and linked runtime ownership must resolve through semantic linked
  entities or deckwide effects.
- Synthetic regressions prove that a spell owner fails for both
  `OnBoardBonus` and `BeforeBattlecryTargetBonus`, while a valid linked
  minion-to-Hero-Power owner passes.
- Added a frozen local 192-row DBF snapshot containing exactly the card data
  needed by the eleven representative deckstrings plus CuteWarrior. The
  acceptance fixture uses that snapshot for deckstring decoding, returns
  deterministic empty Cardfeed data, denies any remaining DNS/socket/URL
  access, and records a failure if the runtime writer entry is invoked.
- Every diagnostic package and the live-verified positive case now prove that
  the temporary runtime root remains absent and no runtime apply receipt is
  created.
- Restored the explicit current truth that all five core strong fixtures have
  `cards_needing_mechanic_lowering == 0`.
- Updated the operator guide and skill references to describe the exact
  catalog, typed parity, semantic linked-owner, network-isolation, and
  read-only guarantees.

Fix-round TDD and verification:

- Initial focused RED: `10 failed, 13 deselected`; the new catalog and CardID
  contract helpers did not yet exist.
- A later full DNS-deny run exposed and reproduced the deckstring library's
  hidden online DBF bootstrap before the frozen local DBF loader was added.
- Synthetic GREEN: `10 passed`; the final expanded synthetic set covers both
  forbidden behavior blocks.
- Complete Task 10 file: `25 passed`.
- Core acceptance matrix: `13 passed, 12 deselected`.
- Required focused suites: `57 passed, 11 skipped`.
- Full contract guardrail: `949 passed`; installed-skill sync,
  contract-spine sentinel, and focused boundary checks all reported `OK`.
- Installed-skill sync check, targeted Ruff, and `git diff --check`: clean
  apart from Git's existing LF-to-CRLF notices.

No runtime, HSTuner, HearthRanger Desktop, or runtime write path was used in
the fix round.
