# Task 1 Report: Index the New Research Package Without Making It Operator Guidance

Status: DONE

## What Changed

- Added `docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/README.md`.
- Indexed `2026-07-14-hsconfig-source-contract-logic-guardrail-audit` in `docs/research/current-truth.md` as Contract-spine Guardrail v2 evidence.
- Added a docs regression test in `tests/test_docs_active_path.py` to verify:
  - the current-truth index names the research package;
  - the package is labelled as research evidence only;
  - the package is explicitly not operator instructions or runtime input;
  - `operator_summary.json` remains the normal apply authority;
  - source-contract and source-to-runtime reports remain diagnostic.

## RED Evidence

Command:

```powershell
python -m pytest -q tests/test_docs_active_path.py::test_current_truth_names_2026_07_14_contract_guardrail_audit
```

Result: expected failure.

Key failure:

```text
FileNotFoundError: [Errno 2] No such file or directory: 'docs\\research\\2026-07-14-hsconfig-source-contract-logic-guardrail-audit\\README.md'
1 failed in 0.24s
```

## GREEN Evidence

Command:

```powershell
python -m pytest -q tests/test_docs_active_path.py::test_current_truth_names_2026_07_14_contract_guardrail_audit
```

Result:

```text
1 passed in 0.08s
```

Additional verification:

```powershell
python -m pytest -q tests/test_docs_active_path.py
```

Result:

```text
34 passed in 0.10s
```

## Files Changed

- `docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/README.md`
- `docs/research/current-truth.md`
- `tests/test_docs_active_path.py`

Existing research artifacts under `docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/` were left as evidence artifacts and staged with the research package path:

- `fields.yaml`
- `outline.yaml`
- `results/Current_HSConfig_Contract_Spine_Guardrails.json`
- `results/HearthRanger_VisionAI_Runtime_Surface_Boundary.json`
- `results/Hearthstone_Semantic_False-Lowering_Risks.json`
- `results/Lean_Any-Deck_Autonomy_And_No-Block_Contract.json`

## Self-Review

- Scope stayed within the task brief.
- No operator docs were changed.
- No runtime surface, apply gate, candidate promotion, replay parsing, winrate validation, post-game tuning, or HSTuner behavior was introduced.
- The README uses the brief's wording that the package is evidence only, not operator guidance, not runtime input, and not an apply gate.
- The current-truth entry keeps `operator_summary.json` as the only normal apply authority and keeps source-contract/source-to-runtime/mechanic warnings diagnostic and non-blocking.

## Concerns

- None.
