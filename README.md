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

The installed HSConfig skill normally builds an LLM-optimized start from
exactly three fixed candidates:

- `candidate-1.json` (`proactive_tempo`)
- `candidate-2.json` (`balanced`)
- `candidate-3.json` (`resource_oriented`)

Each candidate is validated against one immutable `starter_context.json`
before an independent clean-context critic ranks all three without numeric
scores. A strategist gets at most two targeted repair rounds for technical
validation defects. The selected document is then compiled through
`configure --optimized-start --starter-decision-json`; direct raw `hsconfig
configure` remains the conservative compatibility path.

`LLM_OPTIMIZED_START` means the package is bound to the validated starter
documents and compiler output. It is a best practical pre-game start config,
not measured gameplay optimality. Inspect
`configure_summary.json.optimized_start` and the package's
`reports/operator_summary.json` before any runtime action.

This installed optimized workflow is the only normal generation route. Source
acquisition eligibility is a source-contract-only apply blocker on the
conservative route. Optimized packages keep source gaps as visible
informational limitations while their sealed starter authority, package
derivation, and guarded apply facts are validated independently.

The skill applies only when live writing was requested, and then runs the
read-only `runtime-match` check against the exact applied package. Failures such
as `optimized_start_summary_invalid` or `optimized_start_derivation_invalid`
inside the production configure transaction leave prior published output and
runtime state in place. The helper also validates the live configure-result
summary immediately after production configure returns. That post-configure
check is read-only detection: it preserves runtime state but cannot roll back
an already-published current pointer.

## Conservative CLI Compatibility

Direct raw `hsconfig configure` remains available for explicitly conservative
source-contract operation. It is compatibility/expert access, not the normal
installed-skill generation route.

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
