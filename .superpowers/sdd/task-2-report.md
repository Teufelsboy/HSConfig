Implemented and committed Task 2.

Changed:
- src/hsconfig/operator_summary.py: wires evaluate_closure_profile(...) into operator summary generation, adds the new source_backed_strong_closure profile fields, and uses profile eligibility to refine SOURCE_BACKED_STRONG source confidence without touching runtime apply authority.
- tests/test_source_backed_strong_harvester_closure.py: adds the prepared ShadowPriest guide regression proving aggro_burn_hero_power closes without requiring an extra generic apply surface.
- tests/test_operator_summary.py: covers profile fields, profile miss demotion, and confirms profile misses do not block runtime apply.

Review fix:
- 424a0a9 fix: harden closure profile strong eligibility
- Added optional gameplan_contract input to build_operator_summary and passed it from package_builder.
- Made profile claim eligibility allowlist-based: promotion_eligible=True or known strong source lane only.
- Explicitly rejects stats, unsupported_runtime_hint, decklist_only, snippet_only, policy/default-runtime fallback lanes, low-confidence lanes, contract_gap, and diagnostic-only rows without strong lane.
- Stops reconstructed card-row fallback data from promoting unless it carries explicit provenance.
- Reconciles strong_promotion_report readiness with profile closure.

Second review fix:
- ff8a79c fix: fail close closure profile evidence
- Prohibited lanes reject before promotion_eligible=True is considered.
- Bare promotion_eligible=True without strong provenance cannot close a profile.
- Missing closure/profile claim evidence now fails closed for source confidence.
- Derived promotion_ready now requires closure_profile_verdict.strong_eligible.
- Added parameterized prohibited-lane coverage with promotion_eligible=True and no-lifecycle/card-row fallback regressions.

Third review fix:
- d97bf02 fix: require strong provenance for closure profiles
- source_confidence and claim_confidence low/thin/unknown-style values now reject before strong-lane checks.
- Reconstructed card_rows can only positively qualify through explicit source_lane; policy_lane/lane/confidence metadata can reject but cannot positively qualify reconstructed fallback rows.
- Added low-confidence and card-row policy-lane/source-lane boundary tests.

Final confidence fix:
- 2500fd3 fix: preserve confidence on reconstructed closure rows
- Reconstructed card_rows now preserve source_confidence and claim_confidence from card_row and nested closure before closure eligibility checks.
- Added reconstructed-card-row low-confidence regressions.

Validation run:
- python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_operator_summary.py tests/test_strong_closure_profiles.py -q -> 123 passed in 7.91s
- python -m pytest tests/test_operator_summary.py -q -k "low_confidence or policy_lane or strong_provenance or card_rows_fallback" -> 10 passed, 105 deselected in 0.16s
- python -m compileall -q src/hsconfig/operator_summary.py src/hsconfig/package_builder.py -> passed

Commit:
- 2374e8d feat: use closure profiles for strong promotion
- 424a0a9 fix: harden closure profile strong eligibility
- ff8a79c fix: fail close closure profile evidence
- d97bf02 fix: require strong provenance for closure profiles
- 2500fd3 fix: preserve confidence on reconstructed closure rows

Residual risk: profile input extraction is intentionally defensive across current report shapes; if future reports move claim-kind data into a new report-only structure, the extractor may need another narrow adapter. Runtime apply gating was not changed.
