# Architecture Overview

[Back to the operator guide](../operator/README.md)

HSConfig is a pre-run compiler for HearthRanger VisionAI configuration. Its
normal input is a deck name plus an exact deck code. Its normal output is an
immutable revision containing strict JSON runtime files and diagnostic reports.
The operator guide owns the command details; this document describes only the
component boundaries.

## Components

1. Input decoding establishes the exact deck fingerprint and CardID roster,
   while one captured data snapshot fixes the main deck, sideboard, and linked
   identity facts used by the run.
2. Codex performs bounded discovery from that frozen request. The controller's
   `complete-research` phase validates the acquisition receipt and seals one
   schema-3 strategist context; an empty shortlist remains a valid, visible
   limitation.
3. One lead produces one candidate. Contract validation returns findings to
   that same lead, and one independent reviewer evaluates the sealed candidate
   together with its matching full validation receipt. Validation and review
   share at most two targeted revisions.
4. Contract compilation maps supported claims to their permitted runtime
   surfaces and keeps wrong-surface claims diagnostic. Richer context cannot
   grant new runtime syntax or ownership.
5. Package validation checks the complete `CustomConfig` tree and the exact
   quality authority: snapshot manifest, context, candidate, candidate
   validation receipt, and review.
6. The revision publisher atomically advances `current.json` only after the
   package is complete.
7. Guarded finalization recomputes authority and either applies then verifies
   the exact runtime match, or returns an explicit preview without writes.

The normal durable tuple is session/manifest v2 with schema-3
context/candidate/review and compiler `hsconfig-live-start-v2`. The legacy
session/manifest v1 plus schema-2 single-candidate tuple remains readable, and
the schema-1 three-candidate route is a separate older compatibility contract.
Human output uses readable deck names and confidence labels; immutable hashes
remain in technical details.

## Authority boundary

`reports/operator_summary.json` is the sole normal human-facing apply verdict.
Other reports explain the verdict but cannot replace it, promote source
strength, or authorize writes. Runtime files are written only by the explicit
apply path. Exact runtime matching proves file parity, not gameplay optimality,
in-client behavior, or win-rate improvement.

## Related contracts

- [Transaction model](transaction-model.md)
- [Pre-run contract](../contracts/pre-run-contract.md)
- [Evidence and disposition](../contracts/evidence-and-disposition.md)
- [Release gate](../contracts/release-gate.md)
