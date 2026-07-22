# Task 3: Normalized Provenance in Research Result Validation

## Status

Completed. Strict Strong validation and contract promotion now use the shared
`research_payload_provenance` normalizer. Diagnostic provenance fields are
returned by strict validation. `source_status_apply_blocking` remains `False`;
this change does not create an apply gate or alter the authority of
`reports/operator_summary.json`.

## TDD Evidence

### RED

Command:

```powershell
python -m pytest tests/test_research_result_validator.py::test_research_result_validator_accepts_strong_with_nested_current_source_metadata tests/test_research_result_validator.py::test_research_result_validator_still_rejects_strong_without_any_current_marker tests/test_research_result_contract.py::test_research_result_contract_accepts_nested_evergreen_marker_for_strong_promotion -q
```

Result: expected failure, `2 failed, 1 passed in 0.31s`.

- Nested `guide_current_deck_match` metadata did not satisfy strict Strong
  freshness.
- Nested `guide_evergreen_wild_archetype` metadata did not permit Strong
  contract promotion.
- Strong payloads with no current or evergreen marker remained rejected.

### GREEN

Command:

```powershell
python -m pytest tests/test_research_result_validator.py tests/test_research_result_contract.py -q
```

Result: `35 passed in 0.27s`.

Required combined command:

```powershell
python -m pytest tests/test_research_result_validator.py tests/test_research_result_contract.py tests/test_source_provenance.py -q
```

Result: `41 passed in 0.25s`.

## Changes

- `src/hsconfig/research_result_validator.py`: uses normalized provenance for
  Strong freshness and returns `freshness_status`, `current_or_evergreen`, and
  `current_or_evergreen_reason` as diagnostic metadata.
- `src/hsconfig/research_result_contract.py`: delegates current/evergreen
  classification to the shared normalizer.
- `src/hsconfig/source_provenance.py`: minimally treats top-level
  `canonical_evidence=True` as current provenance. This preserves the existing
  contract behavior required by the task after the classifier delegation.
- `tests/test_research_result_validator.py`: covers nested-current acceptance
  and true-missing-marker rejection.
- `tests/test_research_result_contract.py`: covers nested-evergreen promotion
  and retained canonical-evidence promotion.

## Self-Review

- Strong accepts top-level and nested current/evergreen markers, while truly
  missing freshness still produces
  `strong_requires_current_or_evergreen_freshness`.
- `source_status_apply_blocking` remains hard-coded `False` in validator,
  contract, and normalizer results.
- No runtime write/apply path, operator-summary authority, default-only runtime
  surface rule, or Darkbishop/Mulligan behavior was changed.
- `git diff --check` passed before commit.

## Commit

Commit message: `fix: validate research freshness provenance`
