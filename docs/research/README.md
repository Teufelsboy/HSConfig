# HSConfig Research Evidence

Research artifacts are evidence, not operator instructions.

Normal operator path starts at `docs/operator/README.md`. The docs/operator/README.md remains the normal operator entrypoint.

Current truth index: `docs/research/current-truth.md`.

`docs/research/current-truth.md` is the only active evidence index. Use it as the only place that names the active evidence packages before opening older historical research folders. The older research folders are historical evidence and should be read through that index before influencing implementation or operator guidance.

Machine-readable sibling: `docs/research/current-truth-index.json`.

Use the Markdown file for human research orientation and the JSON file for tests or tools that need the active evidence packages. Both files are evidence-only. They do not replace `docs/operator/README.md` and they do not grant runtime apply permission.

Research folders explain why a workflow, matrix row, or source-depth decision exists; they do not grant runtime apply permission and they do not replace `reports/operator_summary.json`.

See `docs/research/current-truth.md` for the current active evidence package names and roles. This index stays as evidence-only orientation and does not compete with the current truth file.

Historical evidence examples that remain useful for audit trails:

- `2026-07-08-hsconfig-final-skill-audit`: final skill audit evidence, not current operator guidance.
- `2026-07-08-hsconfig-current-skill-lean-audit`: current skill lean audit evidence, not current operator guidance.
