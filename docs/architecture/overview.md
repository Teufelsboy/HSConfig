# Architecture Overview

[Back to the operator guide](../operator/README.md)

HSConfig is a pre-run compiler for HearthRanger VisionAI configuration. Its
normal input is a deck name plus an exact deck code. Its normal output is an
immutable revision containing strict JSON runtime files and diagnostic reports.
The operator guide owns the command details; this document describes only the
component boundaries.

## Components

1. Input decoding establishes the exact deck fingerprint and CardID roster.
2. Source acquisition and normalization record provenance without creating
   runtime-write authority.
3. Contract compilation maps supported claims to their permitted runtime
   surfaces and keeps wrong-surface claims diagnostic.
4. Package validation checks the complete `CustomConfig` tree and report set.
5. The revision publisher atomically advances `current.json` only after the
   package is complete.
6. Apply revalidates the selected revision before any runtime write.

## Authority boundary

`reports/operator_summary.json` is the sole normal human-facing apply verdict.
Other reports explain the verdict but cannot replace it, promote source
strength, or authorize writes. Runtime files are written only by the explicit
apply path.

## Related contracts

- [Transaction model](transaction-model.md)
- [Pre-run contract](../contracts/pre-run-contract.md)
- [Evidence and disposition](../contracts/evidence-and-disposition.md)
- [Release gate](../contracts/release-gate.md)
