# Task 2 Fix Report

## Result

Metadata-only guide records can no longer self-certify as strong source evidence.
Guide promotion now requires acquired body text in `normalized_text` or `text`,
even when raw metadata declares `source_visibility="full_text"`.

## TDD Evidence

RED command:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_evidence_policy.py -q
```

Before the policy change, the new metadata-only regression failed because the
record incorrectly returned `promotion_eligible=True`.

GREEN command:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_evidence_policy.py -q
```

Result:

```text
15 passed in 0.12s
```

Additional verification:

```powershell
git diff --check
```

Result: passed. Git only emitted existing LF-to-CRLF working-copy warnings.

## Commit

- SHA: `f56a4af58c14cd8ba8fbef0c9129b22c9418b93a`
- Message: `fix: require acquired text for strong guide evidence`

## Changed Files

- `src/hsconfig/source_evidence_policy.py`
- `tests/test_source_evidence_policy.py`
- `.superpowers/sdd/task-2-fix-report.md`

## Concerns

- No known concerns within the requested scope.
- Existing positive guide promotion remains valid when acquired body text is present.
- Decklist-only and static-semantics boundaries remain unchanged; static
  `hero_power_transform` evidence is still effect-eligible but not mulligan-keep
  strategy evidence.
- The implementation commit does not include this report because the report
  records that commit's final SHA; the report is a separate scoped follow-up
  commit.
