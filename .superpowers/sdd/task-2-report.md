# Task 2 Report

## Status

DONE

## Task

HSConfig Source-Backed Strong Contract Closure, Task 2: claim qualification and source lanes.

Add `qualify_source_claim` so raw source claim dictionaries expose source-quality fields for strong-promotion diagnostics without making `SOURCE_BACKED_STRONG` a load-safe prerequisite.

## Changed Files

- `src/hsconfig/source_document_model.py`: added `qualify_source_claim` plus private source-lane, opening-hand relevance, runtime-lowering, and promotion-eligibility helpers.
- `tests/test_claim_kind_runtime_contract.py`: added tests proving hero-power-transform claims can be strong static evidence without opening-hand relevance, and policy-backed claims never promote strong evidence.
- `.superpowers/sdd/task-2-report.md`: refreshed this report for the current Task 2 worker run.

`tests/test_source_contract_conformance.py` was not edited; it was included in targeted verification and stayed green.

## RED Evidence

Command:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py::test_hero_power_transform_is_strong_static_but_not_opening_hand_relevant tests/test_claim_kind_runtime_contract.py::test_policy_backed_claim_is_never_strong_promotion_evidence -q
```

Result:

```text
ERROR tests/test_claim_kind_runtime_contract.py
1 error in 0.53s
```

Expected failure:

- Import failed because `qualify_source_claim` did not exist in `hsconfig.source_document_model`.

## GREEN Evidence

Command:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py::test_hero_power_transform_is_strong_static_but_not_opening_hand_relevant tests/test_claim_kind_runtime_contract.py::test_policy_backed_claim_is_never_strong_promotion_evidence -q
```

Result:

```text
2 passed in 0.37s
```

Targeted contract suite:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_source_contract_conformance.py -q
```

Result:

```text
65 passed in 0.43s
```

Additional check:

```powershell
git diff --check
```

Result: exit code 0; only existing CRLF normalization warnings were printed.

## Commit

Source/test commit:

```text
1bf6bd6e82881909c4f06bc2b7d15e006a5916be feat: qualify source claims for strong promotion
```

## Scope Notes

- `SOURCE_BACKED_STRONG` remains an evidence-quality label; no load-safe apply gate was added.
- Policy-backed and default/generated runtime sources are not promotion eligible.
- `hero_power_transform` can qualify as a strong static claim from official/static sources, with `opening_hand_relevant=False` by default and runtime lowering limited to CardID/contract style handling.
- No runtime surfaces or dependencies were added.

## Concerns

- The implementation follows the task brief's helper contract directly. It does not yet wire qualification into broader promotion/reporting flows; that is outside Task 2 and belongs to later plan tasks.
- `git diff --check` emitted only Git line-ending normalization warnings for touched Python files.
