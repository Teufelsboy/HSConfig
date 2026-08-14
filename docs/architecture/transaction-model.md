# Transaction Model

[Back to the operator guide](../operator/README.md)

HSConfig separates package construction from runtime mutation. Construction
happens in a revision-scoped staging area. The revision becomes current only
after strict validation succeeds, and runtime apply is a separate explicit
transaction.

## Package transaction

1. Decode and bind the deck identity.
2. Write all source, contract, package, and report artifacts beneath one
   revision root.
3. Validate every required file and cross-report invariant.
4. Publish `current.json` atomically to the completed immutable revision.

An interrupted build cannot turn a partial revision into the current package.
Existing current revisions remain addressable and unchanged.

## Apply transaction

Apply resolves the selected revision, recomputes the technical and authority
checks, stages the exact runtime tree beside the destination, and swaps it into
place only when the checks remain valid. Rollback covers `BaseException` so an
interrupt does not leave a staged or partially replaced runtime tree as the
accepted result.

Diagnostics, release receipts, source strength, and package publication never
perform runtime writes by themselves.
