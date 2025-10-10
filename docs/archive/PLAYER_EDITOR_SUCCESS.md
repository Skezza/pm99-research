# Player Editor Status – Not Yet Complete

The earlier handover claimed a fully working player editor CLI. The current
codebase shows that the helper powering that script still contains placeholder
logic:

* `scripts/player_editor.py` wires the CLI to `parse_all_players`, but it only
  prints whatever the parser returns.【F:scripts/player_editor.py†L24-L170】
* `pm99_editor.player_models.parse_all_players` is a stub that synthesizes a
  single placeholder record rather than enumerating real players, so the CLI
  cannot currently list or rename actual database entries.【F:pm99_editor/player_models.py†L64-L86】

For confirmed parsing and editing support, rely on the main library via
`pm99_editor.io.FDIFile` and the GUI/CLI entry points documented in
[docs/EDITOR_README.md](../EDITOR_README.md).【F:pm99_editor/io.py†L215-L358】
