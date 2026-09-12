# HSConfig

HSConfig turns a Hearthstone deck name and deck code into a validated, live-matched HearthRanger VisionAI `CustomConfig` through the installed Codex skill.

Copy this normal prompt into Codex:

```text
Deck name: ShadowPriest
Deck code: <DeckCode>
```

Illustrative successful response (not a measured deck result):

ShadowPriest — all cards considered — review confidence: high — LIVE_AND_MATCHED

Every card is reviewed; deliberately unchanged cards do not need an unnecessary
generated rule.

Deck -> Snapshot -> Bounded research -> Candidate -> Independent review -> Live or Preview

Illustrative limited-evidence preview:

ShadowPriest — all cards considered — review confidence: limited — PREVIEW_READY

In this example, the user explicitly requested preview. Available guide evidence
was limited, so assumptions and reduced confidence remain visible; preview means
no runtime files were written. Limited confidence alone does not prevent an
authorized live run.

The aim is the best practical evidence-based pre-run configuration, not measured gameplay optimality.

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

Use Windows with Python 3.11 or newer. From the repository checkout directory,
with your intended Python environment activated, run:

```powershell
python -m pip install -e .
```

This installs the Python package, not the Codex skill or a live profile.
Complete "One-time setup" in [docs/operator/README.md](docs/operator/README.md) to install the bundled
skill and explicitly authorize the intended runtime/output roots.
After setup, the normal prompt needs only the deck name and deck code.

## Normal operation

The installed HSConfig skill captures one consistent local data snapshot,
performs bounded Codex discovery, and asks the controller to seal the resulting
research and rich deck facts before candidate work begins. It creates one
candidate with one lead strategist, then uses one independent reviewer whose
approval is bound to that candidate's matching validation receipt. The lead
considers alternatives internally; the operator does not choose between
competing candidates. Technical validation and review share at most two
revisions by the same lead.

This installed optimized workflow is the only normal generation route. A
valid enabled profile authorizes live operation for its bound runtime and
output roots, so the normal prompt needs no per-run apply confirmation.
Explicit preview overrides live and ends at `PREVIEW_READY` without runtime
writes. A missing or invalid profile, or a disabled profile without explicit
preview, returns `PROFILE_REQUIRED`; there is no silent preview fallback.

Completion is `LIVE_AND_MATCHED`, or `ALREADY_LIVE` after verifying the same
approved config is already active. Review confidence is `high|limited`;
limited confidence and evidence gaps remain visible and do not mean gameplay
quality was measured. An empty research shortlist is valid; source limitations
and assumptions stay explicit rather than being invented or hidden.
`LLM_OPTIMIZED_START` binds the approved starter and compiler output, while
`reports/operator_summary.json` remains the normal apply authority. Source
gaps are informational on this optimized route, not a substitute authority.

Use the same session's `resume` phase after interruption. Once an invocation
receipt exists, or `APPLY_STARTED` is reached, resume is recovery-only: it
does not rerun strategy or review, create a replacement candidate, or blindly
retry apply. Failures report the actual status instead of claiming live
success.

## Conservative CLI Compatibility

Direct raw `hsconfig configure` remains available for explicitly conservative
source-contract operation. It is compatibility/expert access, not the normal
installed-skill generation route.

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "<OutputBaseRoot>/<DeckName>" --json
```

Use a separate personal output base, not the repository's fixed twelve-deck
`outputs/` release catalog. Resolve `<OutputBaseRoot>/<DeckName>/current.json`,
then read the selected package's
`reports/operator_summary.json`. On these explicit expert paths:
Runtime writes happen only through `hsconfig
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
