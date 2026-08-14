# Output Retention Policy

`outputs/` is ignored local working state. Keep one current package per deck
when practical. Older same-deck entries may be retained when they support an
active comparison, but should not be mistaken for the current operator
package.

List output entries and likely older same-deck candidates with:

```powershell
python scripts/report_output_inventory.py outputs
```

The inventory recognizes both `<entry>/04_package/reports` and direct
`<entry>/reports` plus `CustomConfig`. It writes JSON to stdout only and
reports only deck name, relative path, UTC modified time, and structural
package status. It reads only `deck_name` from `input_manifest.json`; deck
codes, runtime paths, apply fields, and operator-summary decisions are not
reported.

Candidate selection is deterministic: within the same case-insensitive deck
name, the newest package is treated as current and older packages are listed
as likely duplicate candidates. A candidate is a review prompt, not a delete
decision. The script has no delete, clean, move, archive, retention, or output
file option and changes no package.

Do not delete or move an output merely because it appears as a candidate.
Review its purpose and handle any later cleanup as a separately authorized
task. Maintenance and inventory are never apply authority.
`reports/operator_summary.json` remains the only normal apply authority.
