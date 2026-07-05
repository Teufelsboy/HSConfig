# Workflow

Build flow: deck input -> exact identity -> card metadata -> guide claims -> guide-backed gameplan -> surface intent -> compilers -> validation -> optional runtime apply.

Use `hsconfig build` for package creation, pass `--claims-json` when guide research has source-backed claims, use `hsconfig validate` before handoff or apply, and use `hsconfig apply` only when the user explicitly asks to write to a HearthRanger runtime.
