# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

## License and visibility

Publicly visible — proprietary — All Rights Reserved

Copyright (c) 2026 Teufelsboy.

## Scope and non-goals

HSConfig is a Windows pre-run configuration tool. Give it a deck name and deck
code and it produces the load-safe HearthRanger configuration package for that
deck. It does not parse replays, inspect winrate, tune after games, or claim
gameplay improvement. Those activities are outside HSConfig.

Generated runtime surfaces are limited to `GlobalValues.json`, `Mulligan.json`,
per-card `<CARDID>.json`, and `Combo.json` only when its exact contract is
satisfied. Source evidence and diagnostics cannot grant runtime-write authority.
`reports/operator_summary.json` is the sole normal apply authority.

## Installation

```powershell
python -m pip install -e .
```

The detailed operator instructions are in `docs/operator/README.md`.

## Normal operation

Preferred normal path: `hsconfig configure`.

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --json
```

Resolve `outputs/<DeckName>/current.json`, then read the selected package's
`reports/operator_summary.json`. Runtime writes happen only through `hsconfig
apply` or `hsconfig configure --apply`.

## Verification

The canonical local release gate is the local Clean-OID producer/verifier:

```powershell
python scripts/check_release_gate.py --repo . --outputs outputs --tree-mode working-pre-cutover --json
```

Run it only from the intended clean committed OID. The single locked `ci`
workflow has `contract`, `test`, `package`, and `security` jobs. Repository and
package verification do not prove final GitHub governance or gameplay quality.

## Documentation

- [Operator guide](docs/operator/README.md)
- [Architecture overview](docs/architecture/overview.md)
- [Pre-run contract](docs/contracts/pre-run-contract.md)
- [Security policy](SECURITY.md)
- [Contribution policy](CONTRIBUTING.md)
