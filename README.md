# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

## License and visibility

Publicly visible — proprietary — All Rights Reserved

Copyright (c) 2026 Teufelsboy.

## Scope and non-goals

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those are HSTuner concerns. `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path. Their absence never blocks a valid load-safe package, and their presence in a normal package is treated as drift.

Source-backed runtime Mulligan writes require explicit `claim_kind` values such as `mulligan_keep` or `mulligan_discard`. Card importance, start-of-game effects, deckbuilding effects, hero-power-transform text, and guide gameplan text remain contract evidence unless they are separately backed by explicit hand-required Mulligan guidance.

Runtime Mulligan rows may come only from exact live-guide authority (Lane B) or
an explicit deterministic claim bound to the packaged
`versioned_internal_policy` profile (Lane D). HSConfig never infers keeps from
mana curve, card roles, pressure, draw, setup, or deck-name heuristics. When
neither lane authorizes a physical row, Lane E records explicit
`bot_delegated` dispositions and leaves the Mulligan decision to HearthRanger's
native pre-run bot with zero generated runtime rows. Lane D and
Lane E must not promote the deck to `SOURCE_BACKED_STRONG`.

The frozen twelve-package pre-run release projection contains 316 canonical
claim identities: 267 Lane-A static-semantics claims and 49 Lane-C
guide-context claims, with zero Lane-B, Lane-D, or Lane-E claims. A
deck-matched guide label without a live-verified, same-fingerprint typed
authority remains Lane C; low confidence or suppression is not bot delegation.
Lane E is minted only by an explicit `bot_delegated` disposition and matching
zero-emission lifecycle row.

HSConfig separates source semantics from runtime authority. A claim such as
`hero_power_transform` or `card_role` can enrich the every-card contract and
per-card behavior reports without being allowed to write `Mulligan.json`,
`GlobalValues.json`, or `Combo.json`. Each runtime surface has its own gate, so
weak or wrong-surface claims remain visible instead of blocking the package.

## Installation

python -m pip install -e .

Start with `docs/operator/README.md`.

## Normal operation

Preferred normal path: `hsconfig configure`.

Use `hsconfig configure` for normal operation:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --json
```

If compact public source-search records exist, use the source-autopilot bridge:

```powershell
hsconfig configure --auto-source --source-search-results-json ...
```

The bridge writes `02_source_autopilot/source_documents.json` and feeds it into the existing research and prepare stages. `source-autopilot` is source-strength preflight, not runtime apply authority. decklist-only and static records do not promote `SOURCE_BACKED_STRONG`.

`hsconfig configure` is the one-command pre-run package path. It decodes the deck, writes the manifest, creates source-document/research/package output folders, runs research, prepares the package, validates it, and atomically updates `outputs/<DeckName>/current.json`. That pointer resolves to `outputs/<DeckName>/revisions/sha256-<digest>/04_package/reports/operator_summary.json`, the sole human-facing verdict. Individual reports are diagnostic and must not be used to infer apply readiness. It only writes runtime files when `--apply` is explicitly requested.

Lower-level inspected path: `source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`.

Use the lower-level inspected path when you need to review or edit source evidence between stages. Compact source-search records can be converted with `hsconfig source-autopilot` before the inspected chain continues. It starts with `hsconfig source-manifest`, continues through `hsconfig source-autopilot` or `hsconfig draft-source-documents`, then `hsconfig research-deck` and `hsconfig prepare`, and still ends at `reports/operator_summary.json` plus the guarded `hsconfig apply` gate.

Runtime apply is guarded by recomputed strict validation, verified deck input and strategic source authority, deterministic package derivation, and operator-summary parity. See `docs/operator/README.md` for the exact gate order and blocked reason codes.
Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.

## Verification

Keep the installed skill synchronized with:

python scripts/sync_installed_skill.py --check

Developer contract guardrail:

```powershell
python scripts\check_contract_guardrails.py
```

This checks installed-skill sync, the contract-spine sentinel, and the focused
boundary suite. It is a developer drift check, not a second operator gate.

Canonical local release gate:

```powershell
python scripts/check_release_gate.py --repo . --outputs outputs --tree-mode working-pre-cutover --json
```

Run it only from a clean committed OID. It executes the complete local release
contract, emits concise progress on stderr, and emits exactly one stable JSON
document on stdout. `working-pre-cutover` keeps GitHub polish pending and never
claims final release readiness. `candidate` requires a detached tree and binds
the complete canonical outputs inventory. `final` is fail-closed with no
historical publishability exceptions.

The command itself is the stdlib-only bootstrap parent for the local Clean-OID
producer/verifier. The single locked `ci` workflow has `contract`, `test`,
`package`, and `security` jobs; it reuses this parent only for the bound locked
coverage route, the two canonical internal repository checks, and the
stdlib-only event-commit baseline. That baseline binds `github.sha`, `HEAD`, the
tree OID, clean status, and a sorted path/Git-mode/content-SHA256 inventory
before any dependency download, rejects non-regular Git tree entries, and
materializes the exact-OID archive through the same strict archive reader.
Inventory validation checks the source root and every directory ancestor before
reading a file, rejecting symlinks, junctions, reparse points, and any resolved
path outside the materialized root even when outside bytes match. It
does not claim final GitHub governance or gameplay
validation. The local command selects the lock for the running Python minor. It
supports Python 3.11 and 3.12,
matching the two committed release locks; Python 3.13 or newer fails with one
JSON document and exit code 2 before environment creation. It
downloads and verifies the exact locked
pip wheel into a venv created without `ensurepip`, downloads and inventories all
43 locked wheels before install, installs the 41 startup-surface-free wheels
from the local wheelhouse, and exposes the hash-bound Setuptools and Coverage
payloads through a revalidated overlay with their `.pth` hooks omitted. It
builds `hsconfig` from a second byte/mode/digest-identical committed-source
materialization and binds each wheel inventory, the source inventory digest,
commit, and tree before any gate check runs. Re-execution always starts
`committed-source/scripts/check_release_gate.py`. Before creating the child
process, the trusted parent revalidates the complete committed-source inventory
and the controller's exact path, Git mode, bytes, SHA256, row, and inventory
digest. The manifest producer returns the digest of the exact bytes it wrote,
and the parent transports the already verified controller bytes to the child;
the executable source is never reopened by path after validation. The child
independently proves that its own controller path and content are that same
source-inventory entry. The child retains the original invocation
directory, so relative `--repo` and `--outputs` operands keep their public CLI
meaning even though the executed script is the committed controller. The same
package/version policy controls each wheel's install disposition, allowed
startup hooks, and complete child-side re-inventory. Ambient packages, plugins,
bytecode, and poisoned virtual environments are not trusted or reused.

The gate is the only canonical producer/verifier. It requires `outputs/` to
contain exactly the twelve catalog deck directories, snapshots every directory
and file by type, size, and digest, and derives semantic closure from the current
canonical package reports. It derives open findings from the completed checks;
there are no hand-authored authority JSON inputs. In final mode it performs a
fresh live GitHub API transaction for repository settings, the active ruleset,
the version tag, release, and empty asset inventory, all bound to the same repository,
OID, tree, version, observation time, and transaction identity. Ephemeral scorecard
evidence and receipts exist only in memory and cross the Near-100 process boundary as one
canonical JSON stdin envelope. Embedded receipt schema v2 binds repository identity,
commit OID, tree OID, tree state, dirty-tree fingerprint, and generation mode; final
GitHub receipts also bind the validated transaction identity and observation time. The
gate creates no evidence files or named evidence workspace. The legacy schema-v1
`--evidence <file>` scorecard input remains diagnostic compatibility only and is not a
canonical release-gate authority path.

## Documentation

- [Operator guide](docs/operator/README.md)
- [Security policy](SECURITY.md)
- [Contribution policy](CONTRIBUTING.md)
