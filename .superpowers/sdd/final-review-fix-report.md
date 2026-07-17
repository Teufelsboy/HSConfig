# HSConfig Final Review Fix Report

## Status

Fixed final review findings for stale public/community guide strong promotion and acquisition report missing-action aggregation.

## Commit

Fix commit: `1bd59df5c07ec300baae997868db4cfbb89f8c08`

## Files Changed In Fix Commit

- `src/hsconfig/source_document_model.py`
- `src/hsconfig/source_acquisition.py`
- `tests/test_source_document_builder.py`
- `tests/test_source_acquisition_strong_closure.py`

## Changes

- `source_document_model._strong_promotion_eligible` now blocks public/community guide strong promotion when `freshness_status` is present and is not `current`.
- `source_acquisition.collect_public_source_records` now reports the first non-`none` per-record `first_missing_source_action` in source order, while preserving the existing no-record fallback action.
- Added a regression proving stale manually supplied guide claims can remain generally promotion eligible but no longer become `strong_promotion_eligible`.
- Added a regression proving acquisition-level `first_missing_source_action` is non-`none` for decklist/snippet/stale-only non-strong records and matches the first per-record missing action.

## Tests Run

### Red Regression Run Before Fix

Command:

```powershell
python -m pytest tests\test_source_document_builder.py::test_source_document_builder_blocks_stale_candidate_strong_guide_claims tests\test_source_acquisition_strong_closure.py::test_acquisition_report_uses_first_missing_action_from_non_strong_records
```

Output:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\darbo\Documents\HSConfig
configfile: pyproject.toml
plugins: anyio-4.14.1, base-url-2.1.0, playwright-0.8.0, xdist-3.8.0
collected 2 items

tests\test_source_document_builder.py F                                  [ 50%]
tests\test_source_acquisition_strong_closure.py F                        [100%]

================================== FAILURES ===================================
___ test_source_document_builder_blocks_stale_candidate_strong_guide_claims ___

    def test_source_document_builder_blocks_stale_candidate_strong_guide_claims():
        deck_identity = {
            "deck_name": "Fixture",
            "cards": [{"card_id": "CARD_A", "count": 2, "name": "Card A"}],
        }
        source_documents = [
            {
                "source_url": "https://example.invalid/old-fixture-guide",
                "source_title": "Old Fixture Guide",
                "source_family": "guide",
                "retrieved_at": "2024-01-01T00:00:00Z",
                "deck_name": "Fixture",
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "deck_or_archetype_matched",
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_A"],
                        "stance": "keep",
                        "evidence_text_short": "Mulligan: Keep Card A.",
                        "source_confidence": "high",
                        "source_record_strength": "candidate_strong",
                    }
                ],
            }
        ]

        bundle = build_source_document_bundle(
            deck_identity=deck_identity,
            card_metadata={"cards": deck_identity["cards"]},
            source_documents=source_documents,
            current_date="2026-07-07",
        )
        claim = bundle["claims"][0]
        qualified = qualify_source_claim(claim)

        assert claim["freshness_status"] == "stale"
        assert claim["claim_confidence"] == "medium"
        assert qualified["promotion_eligible"] is True
>       assert qualified["strong_promotion_eligible"] is False
E       assert True is False

tests\test_source_document_builder.py:129: AssertionError
__ test_acquisition_report_uses_first_missing_action_from_non_strong_records __

    def test_acquisition_report_uses_first_missing_action_from_non_strong_records():
        deck_identity = {
            "deck_name": "ShadowPriest",
            "deck_slug": "shadowpriest",
            "deck_code_hash": "sha256:shadow",
            "cards": [
                {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
                {"card_id": "CARD_001", "name": "Patches the Pirate", "cost": 1, "count": 1},
            ],
        }

        payload = collect_public_source_records(
            deck_name="ShadowPriest",
            deck_identity=deck_identity,
            source_urls=[
                "https://example.test/decklist-only",
                "https://example.test/snippet",
                "https://example.test/stale-guide",
            ],
            current_date="2026-07-15",
            fetcher=_fetcher,
            resolver=_resolver,
        )

        records = payload["source_records"]
        assert [record["source_document_kind"] for record in records] == [
            "decklist",
            "snippet",
            "guide",
        ]
        assert {record["strong_promotion_eligible"] for record in records} == {False}
        missing_actions = [
            record["first_missing_source_action"]
            for record in records
            if record["first_missing_source_action"] != "none"
        ]
        assert missing_actions
>       assert payload["source_acquisition_report"]["first_missing_source_action"] == missing_actions[0]
E       AssertionError: assert 'none' == 'add_current_...current_guide'
E
E         - add_current_publication_metadata_or_current_guide
E         + none

tests\test_source_acquisition_strong_closure.py:154: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_source_document_builder.py::test_source_document_builder_blocks_stale_candidate_strong_guide_claims
FAILED tests/test_source_acquisition_strong_closure.py::test_acquisition_report_uses_first_missing_action_from_non_strong_records
============================== 2 failed in 0.39s ==============================
```

### Green Regression Run After Fix

Command:

```powershell
python -m pytest tests\test_source_document_builder.py::test_source_document_builder_blocks_stale_candidate_strong_guide_claims tests\test_source_acquisition_strong_closure.py::test_acquisition_report_uses_first_missing_action_from_non_strong_records
```

Output:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\darbo\Documents\HSConfig
configfile: pyproject.toml
plugins: anyio-4.14.1, base-url-2.1.0, playwright-0.8.0, xdist-3.8.0
collected 2 items

tests\test_source_document_builder.py .                                  [ 50%]
tests\test_source_acquisition_strong_closure.py .                        [100%]

============================== 2 passed in 0.16s ==============================
```

### Focused Source/Acquisition/Guide Depth Run

Command:

```powershell
python -m pytest tests\test_source_document_builder.py tests\test_source_acquisition_strong_closure.py tests\test_source_acquisition.py tests\test_source_evidence_policy.py tests\test_guide_source_depth.py
```

Output:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\darbo\Documents\HSConfig
configfile: pyproject.toml
plugins: anyio-4.14.1, base-url-2.1.0, playwright-0.8.0, xdist-3.8.0
collected 53 items

tests\test_source_document_builder.py .......................            [ 43%]
tests\test_source_acquisition_strong_closure.py .....                    [ 52%]
tests\test_source_acquisition.py .........                               [ 69%]
tests\test_source_evidence_policy.py .....                               [ 79%]
tests\test_guide_source_depth.py ...........                             [100%]

============================= 53 passed in 0.33s ==============================
```

### Strong Promotion Boundary Run

Command:

```powershell
python -m pytest tests\test_claim_kind_runtime_contract.py tests\test_static_semantics_source_records.py tests\test_semantic_runtime_negative_boundaries.py
```

Output:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\darbo\Documents\HSConfig
configfile: pyproject.toml
plugins: anyio-4.14.1, base-url-2.1.0, playwright-0.8.0, xdist-3.8.0
collected 72 items

tests\test_claim_kind_runtime_contract.py .............................. [ 41%]
.....................                                                    [ 70%]
tests\test_static_semantics_source_records.py ....                       [ 76%]
tests\test_semantic_runtime_negative_boundaries.py .................     [100%]

============================= 72 passed in 0.46s ==============================
```

## Checks

Command:

```powershell
git diff --check
```

Output:

```text
warning: in the working copy of 'src/hsconfig/source_acquisition.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/hsconfig/source_document_model.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_source_acquisition_strong_closure.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_source_document_builder.py', LF will be replaced by CRLF the next time Git touches it
```

Exit code: 0.

## Concerns

- The report was written after the fix commit so it could contain the real final commit hash; therefore the report file itself is a post-commit workspace artifact, not part of commit `1bd59df5c07ec300baae997868db4cfbb89f8c08`.
- `git diff --check` returned exit code 0 with existing Windows line-ending normalization warnings only.

---

## Final Review Fix: Canonical Source Status Sync

### Files Changed

- `src/hsconfig/research_status_sync.py`
  - Normalize deck identities before assigning snapshot relations.
  - Classify non-matching snapshots as `different_deck_snapshot` before any status comparison.
  - Base `missing_research_snapshot`, stale/conflict counts, and matching counts only on canonical-deck snapshots.
  - Keep different-deck rows diagnostic and non-blocking with `inspect_research_snapshot_deck_identity`.
- `src/hsconfig/commands/source_workflow.py`
  - Write the unmodified diagnostic report for `--out`; do not add `written_report`.
- `tests/test_research_status_sync.py`
  - Cover mixed results, same-status different-deck snapshots, and results with no matching deck snapshot.
- `tests/test_research_status_sync_cli.py`
  - Assert that `--out` and stdout payloads are equal and omit `written_report`.
- `tests/test_research_current_truth_index.py`
  - Assert the exact machine-readable snapshot-sync policy, normal apply authority, and all diagnostic-only booleans.
- `docs/research/current-truth-index.json`
  - Add `different_deck_snapshot` to the documented relation contract.

### Tests Run

Command:

```powershell
python -m pytest tests/test_research_status_sync.py tests/test_research_status_sync_cli.py tests/test_research_current_truth_index.py -q -p no:cacheprovider
```

Output:

```text
...............                                                          [100%]
15 passed in 0.92s
```

Command:

```powershell
python -m pytest tests/test_research_status_sync.py tests/test_research_status_sync_cli.py tests/test_research_current_truth.py tests/test_docs_active_path.py tests/test_source_status_resolver.py tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
```

Output:

```text
........................................................................ [ 35%]
........................................................................ [ 70%]
...........................................................              [100%]
203 passed in 18.19s
```

Command:

```powershell
git diff --check -- src/hsconfig/research_status_sync.py src/hsconfig/commands/source_workflow.py tests/test_research_status_sync.py tests/test_research_status_sync_cli.py tests/test_research_current_truth_index.py docs/research/current-truth-index.json
```

Output:

```text
warning: in the working copy of 'docs/research/current-truth-index.json', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/hsconfig/commands/source_workflow.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/hsconfig/research_status_sync.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_research_current_truth_index.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_research_status_sync.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_research_status_sync_cli.py', LF will be replaced by CRLF the next time Git touches it
```

Exit code: 0.

### Concerns

- No functional concerns found. The diff check reports existing Windows line-ending normalization warnings only.
- No files were staged or committed.
