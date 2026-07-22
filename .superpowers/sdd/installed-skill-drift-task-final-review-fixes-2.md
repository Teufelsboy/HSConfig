# Final Review Fixes 2

## Scope

- Fixed all three Important findings in the owned config-quality, skill-sync, and contract-preflight modules.
- Added focused regressions for Darkbishop evidence eligibility, real mechanic-discipline summary status, and quoted non-default install-root guidance.
- Kept installed-skill drift diagnostic-only and preserved `reports/operator_summary.json` as the only normal runtime apply authority.
- Did not write installed skill roots, runtime files, replay/log evidence, HSTuner data, or new runtime surfaces.

## RED

- `pytest -q tests/test_config_quality_contract.py tests/test_contract_preflight.py tests/test_skill_sync.py`
  - Result before production edits: `10 failed, 42 passed`.
  - Mechanic status regressions expected `clean` or `attention`; actual result was `KeyError: 'status'` for both real report paths.
  - Four Darkbishop negative regressions expected `explicit_mulligan_keep_evidence_present=false`; actual result was `true` for `policy_backed_autonomous_mulligan`, `policy_fallback`, `default_runtime`, and effect-only/suppressed claims.
  - Drift, missing-root, and contract-preflight fallback regressions expected `python scripts\sync_installed_skill.py --install-root "<resolved-root>"`; actual result was the bare `python scripts\sync_installed_skill.py` command.

## GREEN

- `pytest -q tests/test_config_quality_contract.py tests/test_configure_cli.py tests/test_contract_preflight.py tests/test_skill_sync.py`
  - Final combined verification: `76 passed in 23.85s`.
- `pytest -q tests/test_config_quality_contract.py tests/test_contract_preflight.py tests/test_skill_sync.py`
  - `52 passed in 6.92s`.
- `pytest -q tests/test_configure_cli.py`
  - `24 passed in 10.43s`.
- `python scripts\sync_installed_skill.py --check`
  - Passed: installed HSConfig skill is in sync.
- `git diff --check`
  - Passed; only LF-to-CRLF working-copy warnings were printed.
- `python scripts\check_hsconfig_currentness.py --cwd . --json`
  - Branch `codex/hsconfig-semantic-intent-scoring`, `ahead_origin_main=129`, `behind_origin_main=0`; dirty was expected before commit.

## Changes

- Darkbishop exceptions now originate only from claim IDs in `guide_claim_bundle.json` that link to complete public-guide `source_evidence_index` records, use an eligible guide lane/type, remain runtime-lowerable, and contain canonical explicit opening-hand/mulligan intent. Runtime acceptance still has to trace the same claim ID.
- `mechanic_runtime_discipline.status` is now deterministically `attention` when report-only runtime rows or unregistered mechanics exist, otherwise `clean`; the configure compact summary receives that non-empty value from a real report.
- Skill-sync recommendations now append a Windows-safe quoted `--install-root "<resolved-root>"` for non-default roots. Normal status and contract-preflight fallback use the same recommendation helper.

## Residual Risk

- Verification is focused on the requested changed areas plus the configure CLI suite; no full repository suite was requested or run.
