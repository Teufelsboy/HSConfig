# Task 3 Report: Expose Configure Acceptance Summary

Status: done

Changed files:
- `src/hsconfig/commands/configure.py`
- `tests/test_configure_cli.py`

RED result:
- Command: `pytest tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests\test_configure_cli.py::test_configure_quality_summary_failure_stays_diagnostic_only -q`
- Result before implementation: `2 failed`
- Expected failure: both tests raised `KeyError: 'acceptance_summary'` because `configure_summary.json` did not yet expose the top-level field.

GREEN / verification:
- Command: `pytest tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests\test_configure_cli.py::test_configure_quality_summary_failure_stays_diagnostic_only -q`
- Result after implementation before commit: `2 passed in 10.62s`
- Result after commit: `2 passed in 6.66s`

Commit:
- `eedf84286e5dda2d19e9bb78488ab63ed588c4b0` (`feat: expose configure acceptance summary`)

Notes / risks:
- `acceptance_summary` is written only to the top-level `configure_summary.json`.
- `reports/operator_summary.json` schema was not changed and remains the normal apply authority.
- `SOURCE_BACKED_STRONG`, `source_status_apply_blocking`, `default_only_runtime_surfaces`, and `config_quality_summary` remain diagnostic for this output projection and were not added as new apply gates.
- No HSTuner, runtime artifacts, gameplay logs, new reports, or runtime behavior changes were used.
- `.superpowers/sdd/progress.md` was already dirty and was not edited or staged.

---

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

## Compatibility Fix: source_freshness and currency_status

### Review Finding

Delegating contract freshness to `research_payload_provenance` unintentionally
dropped historical current/evergreen recognition for top-level and nested
`source_freshness` and `currency_status` markers.

### RED

Command:

```powershell
python -m pytest tests/test_source_provenance.py::test_research_payload_provenance_keeps_source_freshness_and_currency_compatibility -q
```

Result: expected failure, `4 failed in 0.20s`. The new parameterized regression
test covered top-level and nested `source_freshness="current"` plus
`currency_status="evergreen"`.

### Fix and GREEN

`research_payload_provenance` now normalizes those two compatibility fields at
both levels, after the established `freshness_status` handling. Existing
`canonical_evidence=True` precedence is unchanged and every provenance result
continues to return `source_status_apply_blocking=False`.

Command:

```powershell
python -m pytest tests/test_source_provenance.py tests/test_research_result_validator.py tests/test_research_result_contract.py -q
```

Result: `45 passed in 0.27s`.

Scope: only `source_provenance.py`, its regression test, and this report changed;
no runtime/apply, default-only surface, operator-authority, or gameplay behavior
was touched.

---

# Task 3: Source Readiness Preview Contract Visibility

## Status

Completed. Contract preflight now exposes `source_readiness_preview_visible` and
`source_readiness_preview_contract` for the existing diagnostic
`source_readiness_preview` report field. The check verifies documentation,
implementation constants, default-only/no-block terms, and producer emissions in
`source_autopilot_report.json` and `configure_summary.json`.

## RED

Command:

```powershell
pytest tests/test_contract_preflight.py::test_contract_preflight_checks_source_readiness_preview_visibility tests/test_contract_preflight.py::test_contract_preflight_reports_attention_when_source_readiness_preview_drifts -q
```

Result before implementation: `2 failed in 4.09s`.

- PASS-path test failed with `KeyError: 'source_readiness_preview_contract'`.
- Drift-path test still reported `PASS` because no readiness-preview visibility
  check existed yet.

## GREEN / Verification

Focused command:

```powershell
pytest tests/test_contract_preflight.py::test_contract_preflight_checks_source_readiness_preview_visibility tests/test_contract_preflight.py::test_contract_preflight_reports_attention_when_source_readiness_preview_drifts -q
```

Result after implementation: `2 passed in 1.16s`.

Full contract preflight tests:

```powershell
pytest tests/test_contract_preflight.py -q
```

Result: `39 passed in 10.39s`.

CLI preflight:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Result: exit code `1`, `status=ATTENTION`; `source_readiness_preview_visible=true`
and `source_readiness_preview_contract.status=visible`. Attention was due to
`repo_current=false` on the dirty worktree and `installed_skill_sync_current=false`
because the repo skill workflow paragraph differs from the installed skill copy.
`runtime_apply_authority` remained `reports/operator_summary.json` and
`source_status_apply_blocking` remained `false`.

Diff check:

```powershell
git diff --check -- src/hsconfig/contract_preflight.py src/hsconfig/commands/contract_preflight.py tests/test_contract_preflight.py docs/operator/source-builder-workflow.md .agents/skills/hsconfig/references/workflow.md .superpowers/sdd/task-3-report.md
```

Result: exit code `0`; only CRLF conversion warnings.

## Changed Files

- `src/hsconfig/contract_preflight.py`
- `src/hsconfig/commands/contract_preflight.py`
- `tests/test_contract_preflight.py`
- `docs/operator/source-builder-workflow.md`
- `.agents/skills/hsconfig/references/workflow.md`
- `.superpowers/sdd/task-3-report.md`

## Notes

- `src/hsconfig/commands/contract_preflight.py` was updated only to preserve the
  existing CLI fallback payload schema after adding the new top-level contract
  key.
- No runtime outputs, logs, HSTuner paths, apply paths, or
  `.superpowers/sdd/progress.md` were edited.
- No commit was created.

## Review Fix: Contract Field Names

Status: complete

Review finding:
- Task 3 required `configure_summary_field` and `autopilot_report_field` in
  `source_readiness_preview_contract`, but the initial payload only exposed
  `documentation_paths` and `producer_paths`.

Fix:
- Added `configure_summary_field="source_readiness_preview"` and
  `autopilot_report_field="source_readiness_preview"` to both the normal
  contract-preflight payload and CLI exception fallback payload.
- Updated the focused contract expectation to pin these fields.

Verification:
- `pytest tests/test_contract_preflight.py::test_contract_preflight_checks_source_readiness_preview_visibility tests/test_contract_preflight.py::test_contract_preflight_runtime_error_fallback_preserves_normal_payload_schema -q`
  - Result: `2 passed in 1.30s`.
