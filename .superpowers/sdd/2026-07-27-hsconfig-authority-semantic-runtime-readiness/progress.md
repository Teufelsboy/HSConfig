# SDD ledger — plan: docs/superpowers/plans/2026-07-27-hsconfig-authority-semantic-runtime-readiness.md

Execution baseline: 7d6313b48bc771bb1f58f74e0cc556b46a53d1bb
Workspace policy: direct sole main by explicit user instruction; no branch or git worktree.
Runtime policy: no apply and no writes under C:\Users\darbo\Desktop\HS.

Task 1: fix round 1/5 (spec Important empty rows with physical linked owner addressed by ac41fe5b115e5fe0b9842a060ca7cb3a5504a1e1)
Task 1: minor (deferred): curated linked relation knowledge is duplicated across runtime_entity_owner and strict_package_validation.
Task 1: minor (deferred): schema-1 no-write behavior lacks explicit plan_apply_package/apply_package regression coverage.
Task 1: fix round 2/5 (universal invalid-rows fail-closed handling addressed by ca434bec277f48ac74526c57e47ac6a0940d2504)
Task 1: complete (commits f37e65de1395654a5614ba945a2726ff05f5b634..ca434bec277f48ac74526c57e47ac6a0940d2504; spec and quality Important findings closed; root verification 168 passed)
Task 2: fix round 1/5 (copied consumed lineage replay addressed by 43c4135e1836886e3077064a8a838cbdf1852326)
Task 2: minor (deferred): configure split call is outside the source-autopilot stage-specific exception handler.
Task 2: minor (deferred): nested search-record objects remain aliased across consumed lineage and document handoff.
Task 2: complete (commits 0116741d15261a1f59ad0b96d91fa30b11ff9cb0..43c4135e1836886e3077064a8a838cbdf1852326; spec finding closed; quality approved; root verification 56 passed)
Task 3: minor (deferred): local sideboard metadata fallback retains less metadata after deck identity normalization.
Task 3: minor (deferred): downstream missing runtime_eligible defaults remain true even when deck_zone is sideboard.
Task 3: minor (deferred): tests initially lacked operator-attention closure and zone-duplicate coverage.
Task 3: fix round 1/5 (report-only closure and cross-zone CardID aggregation addressed by 2ccea5e3305a1d0d9d7efd062ac6aa4bd98f0a34)
Task 3: complete (commits 50acdc4f6d6c5bd47dec3774598f97a99357288a..2ccea5e3305a1d0d9d7efd062ac6aa4bd98f0a34; spec passed; quality Important findings closed; root verification 111 passed)
Task 4: fix round 1/5 (removed diagnostic fixture authority, preserved exact suppressed-claim vetoes and original lifecycle provenance in 551b88e14f93d1f84e03add7181695b6d08da985)
Task 4: fix round 2/5 (generated lifecycle IDs, multi-card provenance rows, and discard intent repaired in b80024e74fd61801ba6435ad7380bf1e3aa14990)
Task 4: complete (commits 7ca835952e01e734eef0a8b2cfcd81700159ef2c..b80024e74fd61801ba6435ad7380bf1e3aa14990; spec passed after fix round 1; quality approved after fix round 2; root verification 111 passed)
Task 4: post-task regression fix (legacy_unverified claims no longer mint policy vetoes; 3706e60; independent review approved; covered in root Task-5 integration verification)
Task 4: minor (deferred): legacy-unverified comparison uses a string literal instead of the shared provenance constant.
Task 5: fix round 1/5 (canonical matrix/baseline strict binding and malformed/duplicate authority rejection; b0fb386215d82006bf5b9bff9bce00062771c526)
Task 5: fix round 2/5 (schema/ledger/operation downgrade paths; 1d9d679495cf44948bc913ada2df2dd2f5093a81)
Task 5: fix round 3/5 (exact baseline sentinel and initial current-package marker; a8016c4e4ffe6a47f051ad66257dce85e389684b)
Task 5: fix round 4/5 (production validation current-only; explicit legacy opt-in limited to direct tests; 1db159f)
Task 5: minor (deferred): config_usefulness omits baseline-present schema-2 authority keys from expected overlay diagnostics.
Task 5: complete (commits 27411fdf3653d1e40a17830dc9af5ae9b9459aed..1db159f; spec passed; quality approved after four fail-closed rounds; root affected-suite verification 231 passed)
Task 6: fix round 1/5 (readiness taxonomy and exact ShadowPriest fixture/provenance coverage; a2b5361)
Task 6: fix round 2/5 (restored exclusive single-source runtime ownership while keeping within-owner physical dedupe; 7be3f12)
Task 6: minor (deferred): full ShadowPriest fixture E2E is housed in config-quality rather than semantic-safety tests.
Task 6: complete (commits 9eb4cfc..7be3f12; spec and quality approved; root verification 382 passed)
Task 7: fix round 1/5 (real-fixture reasons/readiness, boundary-specific proof, metadata and provenance normalization; 9564829)
Task 7: fix round 2/5 (restored lifecycle-accepted-only CardID emission and suppression-only diagnostics; 334957c)
Task 7: complete (commits 498d4c3..334957c; spec and quality approved; root verification 370 passed with one unrelated known Task3 MechPala sideboard count failure)
Task 8: complete (physical compiled-artifact runtime surface ledger; FIR_911 Mulligan parity, SW_448 to EX1_625t linked separation, and MechPala sideboard coverage; local verification 248 passed)
Task 8: fix round 1/5 (fail-closed Combo/CardID/GlobalValues physical parsing; authoritative empty-ledger consumer projections; sideboard emission strict rejection; order-independent linked-owner collision rejection; ledger/strict slice 74 passed, multi-deck E2E 19 passed, Ruff clean)
Task 8: fix round 2/5 (schema-2 canonical ledger re-derivation and integrity enforcement; exact ledger metrics; claim/card/summary physical reconciliation; ledger/strict slice 80 passed, multi-deck E2E 19 passed, Ruff clean)
Task 8: fix round 3/5 (exact Combo/Mulligan physical identities, discard-aware usefulness and claims, orphan ownership rejection; focused Task-8 suite 86 passed, Ruff clean)
Task 8: fix round 4/5 (claim-satisfied card/closure/attention projection; exact Mulligan/Combo/CardID/GlobalValues identities; normalized selector ownership; special-surface modelling; graph-scoped linked-owner exemptions; canonical type-safe strict validation; ledger-confirmed Strong Closure; affected suite 340 passed, Ruff clean)
