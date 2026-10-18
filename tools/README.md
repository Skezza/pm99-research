# PM99 Tools

Standalone local tools live here. They are separate from the database editor and
patcher upstream repositories.

- `pkf-viewer/`: local SIMULDAT PKF browser and image viewer.
- `season_preset_browser.py`: local season recipe workbench. Run
  `python3 tools/season_preset_browser.py` and choose a year from the left
  side. Its default spreadsheet view resolves the exact source package behind
  that year’s local runtime candidate, without selecting or uploading a file.
  Players, managers, clubs and linked kit BMPs have separate tabs. The Players
  tab shows a portrait BMP link only where a separate hash-bound
  `portrait-render-bindings-v1.json` receipt maps that exact package player id
  to a local BMP; otherwise it explicitly says `No verified portrait`.
  Editable cells stage hash-bound corrections in
  `seasons/<year>/editorial-amendments/working.json`. Materialising creates
  source copies only—it never changes a frozen package or PM99 game database.
  The previous full manifest browser remains at `/manifests`. Use
  `--authoring-root` to point it at a different generated manifest collection.

- `../scripts/season_name_provenance_v1.py`: creates a hash-bound, non-mutating
  player-name sidecar from a selected season package and its captured squad
  source. It records the exact raw source spelling and source-row hash for
  every uniquely linkable source-backed player, keeps native retained carriers
  out of the historical-source queue, and produces transparent proposed PM99
  name components for a direct alpha repair when the evidence is mechanical.

- `../scripts/apply_number_label_name_repairs_v1.py`: directly corrects the
  proven `#<squad number> <player name>` parser defect in the selected alpha
  recipe and live game. It accepts only source-linked candidates, regenerates
  the affected parser-safe name aliases, and replaces only those player
  records in JUG; managers, ratings, kits, squads and calendars are left
  alone. Its local receipt is an audit trail, not an approval queue.

- `../scripts/apply_number_label_name_repairs_batch_v1.py`: resumes that
  direct repair across the current playable post-1999 games. Re-running it
  skips seasons with an existing per-season receipt. Use `--list` to see the
  affected-player count before running it.

- `../scripts/apply_2015_english_manager_names_direct_v1.py`: directly fixes
  the 2015/16 English manager-name defect from the dated English-92 manifest.
  It patches only the existing linked ENT manager names and read-backs all 92
  English manager carriers before replacing the live file.

- `../scripts/apply_position_handling_repair_v1.py`: applies the established
  deterministic, position-aware Handling rule directly to a current recipe
  and game: outfield players are kept in the 1–20 range and goalkeepers have
  a sensible quality-based floor. It compiles only to obtain parser-safe
  replacements, proves every non-target JUG record is byte-identical, then
  writes a compact audit receipt. It does not rebuild a season or alter kits,
  managers, lineups, clubs or other player fields.

- `../scripts/apply_position_handling_repairs_batch_v1.py`: resumes that
  bounded repair across the post-1999 playable games. Its per-season receipts
  let it skip already repaired seasons; `--jobs 2` is the conservative default
  for this workstation.

- `../scripts/apply_compiled_handling_readback_repair_v1.py`: repairs a
  separately proven legacy compiler readback drift only when the recipe has a
  valid outfield value but the exact live carrier does not. The companion
  `apply_compiled_handling_readback_repairs_batch_v1.py` runs the same
  carrier-specific proof across the current post-1999 games.
