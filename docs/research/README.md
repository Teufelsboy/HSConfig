# HSConfig Research Evidence

Research artifacts are evidence, not operator instructions.

Normal operator path starts at `docs/operator/README.md`. The docs/operator/README.md remains the normal operator entrypoint.

Current truth index: `docs/research/current-truth.md`. Use it to find the small set of active evidence packages before opening older historical research folders.

Research folders explain why a workflow, matrix row, or source-depth decision exists; they do not grant runtime apply permission and they do not replace `reports/operator_summary.json`.

## Active Research Packages

| Package | Purpose | Operator Implication |
| --- | --- | --- |
| `2026-07-08-hsconfig-final-skill-audit` | Audits lean operator scope, 11-deck source-depth truth, VisionAI runtime surfaces, every-card contract visibility, apply-gate safety, and maintainability. | Keep HSConfig pre-run only, close Kingslayer and Boarlock before widening the matrix, and slim `hsconfig.cli` without changing public CLI behavior. |
| `2026-07-08-hsconfig-current-skill-lean-audit/` | Current skill lean audit evidence for operator boundary, VisionAI surface, every-card source-depth model, deck matrix truth, and repo slimness. | Evidence, not operator instructions; normal operation still starts at `docs/operator/README.md`. |
| `2026-07-09-hsconfig-universal-wild-skill-audit/` | Universal Wild no-block and mechanic-support evidence for load-safe apply, warning-only mechanics, and card identity resilience. | Active research package for the universal no-block contract; older audit folders remain historical evidence. |

- `2026-07-08-hsconfig-guarded-apply-matrix-audit.md`: curated recommendation from the guarded apply, matrix governance, and VisionAI micro-registry audit.

## Active Universal Wild No-Block Audit

Use `docs/research/2026-07-09-hsconfig-universal-wild-skill-audit/` as the
active research package for the universal no-block and Wild mechanic support
contract. Older audit folders are historical evidence and must not override the
live operator docs or current tests.
