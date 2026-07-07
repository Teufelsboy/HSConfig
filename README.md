# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those are HSTuner concerns. `Presume.json` and `Concede.json` are not emitted in the normal path.

## Normal Operator Path

Start with `docs/operator/README.md`.

Normal command path: `hsconfig source-manifest ...` -> write short evidence rows -> `hsconfig draft-source-documents ...` -> `hsconfig research-deck --source-documents-json ...` -> `hsconfig prepare --guide-sources-json ...` -> inspect `reports/operator_summary.json` -> `hsconfig apply ...` only when requested.

## Install And Verify

```powershell
python -m pip install -e .
python -m pytest -q
python scripts\sync_installed_skill.py --check
```

## Maintainer Sync

After changing `.agents/skills/hsconfig`, run `python scripts\sync_installed_skill.py --check`; if drift is expected, run `python scripts\sync_installed_skill.py`.
