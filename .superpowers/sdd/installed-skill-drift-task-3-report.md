Status: GREEN

Commit before work: `86ea840`
Commit created: `9e3658c`

Files changed:
- `docs/operator/README.md`
- `.agents/skills/hsconfig/SKILL.md`
- `tests/test_skill_files.py`
- `tests/test_operator_docs_contract_policy.py` (no content change required; covered by verification only)

RED result:
- Command: `python -m pytest tests/test_skill_files.py::test_docs_and_skill_route_installed_skill_sync_through_contract_preflight -q`
- Result: failed as expected
- Failure: missing `--skill-install-root` wording in `docs/operator/README.md`

GREEN result:
- Command: `python -m pytest tests/test_skill_files.py tests/test_operator_docs_contract_policy.py -q`
- Result: `94 passed in 0.25s`

Concerns:
- None beyond the existing compactness constraint on `.agents/skills/hsconfig/SKILL.md`; the expert-path wording was kept on one line to preserve the current `< 80` line-count contract.

Final git status --short --branch:
```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring [ahead 8]
```

Review fix:
- Restored `## Expert Paths` as an exact standalone heading in `.agents/skills/hsconfig/SKILL.md`.
- Moved the installed-skill drift route into the first compact Expert Paths bullet.
- Tightened `tests/test_skill_files.py` so installed-skill sync and `--skill-install-root` stay out of the pre-Expert normal skill guidance while operator docs still document preflight JSON, diagnostic-only behavior, and non-default skill roots.

Review-fix tests:
- `python -m pytest tests/test_skill_files.py::test_docs_and_skill_route_installed_skill_sync_through_contract_preflight -q`: `1 passed in 0.21s`
- `python -m pytest tests/test_skill_files.py tests/test_operator_docs_contract_policy.py -q`: `94 passed in 0.24s`

Review-fix commit:
- Message: `fix: keep installed skill routing in expert path`
