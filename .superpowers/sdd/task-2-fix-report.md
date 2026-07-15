# Task 2 Fix Report

## Scope

- Fixed `qualify_source_claim()` source-family classification in `src/hsconfig/source_document_model.py`.
- Added regression coverage in `tests/test_claim_kind_runtime_contract.py`.
- Did not add runtime/apply gates or runtime surfaces.
- Did not change `tests/test_source_contract_conformance.py`.

## Root Cause

`qualify_source_claim()` only derived source quality from `source_type` or `provenance`.
Builder-shaped claims carry `source_family`, so `source_family="card_text"` and
guide-family claims were classified as `source_lane="unknown"` and were not
promotion eligible.

## RED Evidence

Command:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py -k "source_family or string_false or source_blocked" -q
```

Observed before the fix:

```text
5 failed, 40 deselected in 0.50s
```

Failures proved:

- `source_family="card_text"` hero-power-transform claim produced `source_lane="unknown"` instead of `official_static_semantics`.
- `source_family="guide"` and `source_family="mulligan_guide"` claims produced `source_lane="unknown"` instead of `deck_matched_public_guide`.
- `opening_hand_relevant="false"` evaluated as `True`.
- `source_blocked="true"` did not block public-guide promotion.

## GREEN Evidence

Focused regression slice:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py -k "source_family or string_false or source_blocked" -q
```

```text
5 passed, 40 deselected in 0.30s
```

Required verification:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_source_contract_conformance.py -q
```

```text
70 passed in 0.49s
```

```powershell
python -m pytest tests/test_apply_authority_boundary.py -q
```

```text
4 passed in 0.10s
```

```powershell
git diff --check
```

```text
exit 0; Git emitted only LF-to-CRLF working-copy warnings for the two touched files.
```

## Commit

- `8203dde0f7ebf0969e47b3f67e88e0bb1ec2f819` - `fix: qualify source-family claims`

## Concerns

- None known.
- The fix only maps known static source families to the official static lane and known public guide families to the public guide lane.
- Policy/default/generated/snippet/source-blocked claims remain blocked from strong promotion.
