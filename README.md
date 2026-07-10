# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those are HSTuner concerns. `Presume.json` and `Concede.json` are not emitted in the normal path.

## Bootstrap

python -m pip install -e .

Start with `docs/operator/README.md`.

Preferred normal path: `hsconfig configure`.

`hsconfig configure` is the one-command pre-run package path. It decodes the deck, writes the manifest, creates source-document/research/package output folders, runs research, prepares the package, validates it, and only writes runtime files when `--apply` is explicitly requested.

Lower-level inspected path: source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply.

Use the lower-level inspected path when you need to review or edit source evidence between stages. It starts with `hsconfig source-manifest`, continues through `hsconfig prepare`, and still ends at `reports/operator_summary.json` plus the guarded apply gate.

Runtime apply is guarded: `hsconfig apply` validates the package, checks `reports/operator_summary.json`, creates a fake apply receipt, verifies the package hash, and then writes only when runtime apply is explicitly requested.
Runtime writes remain only when requested through `hsconfig apply`.

Keep the installed skill synchronized with:

python scripts/sync_installed_skill.py --check
