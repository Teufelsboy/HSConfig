# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those are HSTuner concerns. `Concede.json` is publicly documented; `Presume.json` is publicly documented on HearthRanger's AOE play-around page, and normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.

Source-backed runtime Mulligan writes require explicit `claim_kind` values such as `mulligan_keep` or `mulligan_discard`. Card importance, start-of-game effects, deckbuilding effects, hero-power-transform text, and guide gameplan text remain contract evidence unless they are separately backed by explicit hand-required Mulligan guidance.

When no source-backed keep can be emitted, HSConfig may emit a small
`policy_backed_autonomous_mulligan` keep set from low-curve pressure, draw, or
setup semantics so `Mulligan.json` is not default-only. This is a separate,
weaker autonomous fallback, not a source-backed guide claim. Cards with
explicit, suppressed, or quarantined Mulligan source intent are vetoed from the
policy lane; non-hand start-of-game effects such as Darkbishop Benedictus also
stay out of opening-hand keeps. Policy-backed Mulligan coverage must not promote
the deck to `SOURCE_BACKED_STRONG`; it only makes the generated pre-run package
more useful while preserving the source/contract boundary.

HSConfig separates source semantics from runtime authority. A claim such as
`hero_power_transform` or `card_role` can enrich the every-card contract and
per-card behavior reports without being allowed to write `Mulligan.json`,
`GlobalValues.json`, or `Combo.json`. Each runtime surface has its own gate, so
weak or wrong-surface claims remain visible instead of blocking the package.

## Bootstrap

python -m pip install -e .

Start with `docs/operator/README.md`.

Preferred normal path: `hsconfig configure`.

Use `hsconfig configure` for normal operation:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --json
```

`hsconfig configure` is the one-command pre-run package path. It decodes the deck, writes the manifest, creates source-document/research/package output folders, runs research, prepares the package, validates it, and leaves the final decision in `outputs/<DeckName>/04_package/reports/operator_summary.json`. It only writes runtime files when `--apply` is explicitly requested.

Lower-level inspected path: `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`.

Use the lower-level inspected path when you need to review or edit source evidence between stages. It starts with `hsconfig source-manifest`, continues through `hsconfig prepare`, and still ends at `reports/operator_summary.json` plus the guarded apply gate.

Runtime apply is guarded: `hsconfig apply` validates the package, checks `reports/operator_summary.json`, creates a fake apply receipt, verifies the package hash, and then writes only when runtime apply is explicitly requested.
Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.

Keep the installed skill synchronized with:

python scripts/sync_installed_skill.py --check

Developer contract guardrail:

```powershell
python scripts\check_contract_guardrails.py
```

This checks installed-skill sync, the contract-spine sentinel, and the focused
boundary suite. It is a developer drift check, not a second operator gate.
