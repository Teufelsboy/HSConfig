# Release Gate Contract

[Back to the operator guide](../operator/README.md)

The canonical release gate verifies one clean committed repository OID, the
complete twelve-package output inventory, locked dependencies, deterministic
distribution artifacts, publishability, contract checks, and the Near-100
scorecard through one controller-owned transaction.

## Tree modes

- `working-pre-cutover` accepts either the exact frozen legacy inventory while
  root cutover is pending or zero legacy files after the atomic cutover. Any
  partial or drifted legacy inventory fails, and this mode never claims final
  release readiness.
- `candidate-index` evaluates an explicitly supplied candidate index.
- `candidate` requires a detached private repository strictly beneath the
  owner's `.cutover-candidate` container and binds the owner's exact outputs.
- `final` accepts no legacy inventory and performs the final governance checks.

The diagnostic publishable-tree command emits one closed JSON document and no
receipt. The canonical gate remains the only release producer and verifier.

## Non-claims

A successful release gate proves the bound repository and package contract. It
does not prove gameplay quality or perform runtime apply.
