# ShadowPriest Task 5 Report

## Changed Files

- `.agents/skills/hsconfig/references/card-behavior-policy.md`
- `.superpowers/sdd/shadowpriest-task-5-report.md`

## Implementation

Added the `Diagnostic Intent Taxonomy` policy section before `Choice Surface Lowering`.
It defines the scoring-only boundary, documents the supported ShadowPriest-style
semantic categories, and explicitly keeps unsupported Mulligan, sequencing,
targeting, timing, and tuning claims report-only.

The policy does not introduce runtime surfaces, apply gates, HearthRanger syntax,
dependencies, HSTuner behavior, or new output files.

## Test Evidence

Command:

```text
pytest tests/test_operator_docs_contract_policy.py tests/test_skill_contract_entrypoint.py -q
```

Result: `40 passed in 0.58s`

Additional check: `git diff --check` passed for the policy change.

## Commit

Policy commit: `5f04e5185034e1ff26d17d5a32f40e1769c80f3a`

## Concerns

No implementation concerns. The taxonomy remains diagnostic metadata and does
not claim runtime proof for unsupported card ordering, targeting, timing, or
post-game tuning.
