# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

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

## Bootstrap

python -m pip install -e .

Start with `docs/operator/README.md`.

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
