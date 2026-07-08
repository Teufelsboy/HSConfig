# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those are HSTuner concerns. `Presume.json` and `Concede.json` are not emitted in the normal path.

## Bootstrap

python -m pip install -e .

Start with `docs/operator/README.md`.

Normal path starts with `hsconfig source-manifest`; runtime apply happens only when requested through `hsconfig apply`.

Keep the installed skill synchronized with:

python scripts/sync_installed_skill.py --check
