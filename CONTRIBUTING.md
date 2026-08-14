# Contributing

Start with `README.md`, then follow
[`docs/operator/README.md`](docs/operator/README.md) for the single current
operator path.

Use test-driven development for behavior changes: add a focused failing test,
confirm the expected RED, implement the minimum change, and confirm GREEN.
Keep changes narrow and preserve existing report schemas and authority
boundaries unless the task explicitly changes them.

Do not commit raw runtime evidence, logs, replays, runtime XML exports, private
evidence folders, deck codes, or generated `outputs/`. Use redacted fixtures
that contain only the fields required by the test.

`reports/operator_summary.json` remains the only normal apply authority.
Maintenance scripts, inventories, historical documents, diagnostics, tests,
and generated contracts cannot authorize runtime writes. Runtime writes occur
only through the documented apply command.

Before submitting a change, run the focused tests first and then:

```powershell
python -m ruff check --no-cache src tests scripts
python -m pytest -p no:cacheprovider
python -m pip_audit
git diff --check
```

Also parse changed YAML files and run the relevant operator, documentation,
skill, and contract tests for the affected boundary.
