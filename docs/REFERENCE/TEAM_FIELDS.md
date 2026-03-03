# Team Fields Reference

This is the authoritative team-record reference for the current codebase.

For container-level rules, use [../DATA_FORMATS.md](../DATA_FORMATS.md). For parser and loader behavior, cross-check [../../app/loaders.py](../../app/loaders.py), [../../app/models.py](../../app/models.py), and [../../app/eq_jug_linked.py](../../app/eq_jug_linked.py).

## Scope

This document describes the team and roster data the project can currently parse conservatively from `EQ98030.FDI`.

## Confirmed Team Sources

The project currently recognizes two main team-related paths:

1. `TeamRecord` parsing from `EQ98030.FDI` team subrecords
2. Parser-backed EQ-to-JUG linked roster extraction via `app/eq_jug_linked.py`
3. Authoritative same-entry roster runs from `scripts/probe_eq_team_roster_overlap_extract.py`
   when `preferred_roster_match.provenance == same_entry_authoritative`

These are related, but not identical.

## Team Subrecord Structure

The current `TeamRecord` loader is still partially heuristic. These elements are the confirmed parts:

- Team-like subrecords are commonly separated by `0x61 0xDD 0x63`.
- Team names are extracted from the first credible uppercase printable span.
- Stadium names are extracted from later printable spans and keyword-based heuristics.
- Team IDs are inferred by scanning for plausible 16-bit values in the expected range.

## Confirmed Team Fields

- `name`
  - Parsed from the first reliable name-like text region
- `stadium`
  - Parsed from later printable stadium-like text spans
- `team_id`
  - Heuristically detected from the decoded team payload
- stadium summary fields, when present in text
  - capacity
  - parking / car park
  - pitch quality

These fields are usable, but team parsing is still less exact than player parsing.

## Parser-Backed Linked Roster Data

`app/eq_jug_linked.py` provides the strongest current roster path for static team membership:

- teams are loaded from indexed `EQ98030.FDI` payloads
- large external-link records are parsed conservatively
- linked rows resolve player IDs against `JUG98030.FDI`

Confirmed roster row shape:

- one roster slot is 5 bytes
- byte `0`: `flag`
- bytes `1-4`: `player_record_id` (`uint32` little-endian)

Current parser-backed roster metadata includes:

- EQ record id
- short name
- stadium name
- full club name
- record size
- mode byte
- linked ENT count
- ordered roster rows

Parser-backed linked roster rows now also expose stable byte locations inside the
indexed EQ payload, which allows fixed-size in-place slot edits for this specific
roster table.

## Authoritative Same-Entry Roster Data

For teams whose `preferred_roster_match` resolves to `same_entry_authoritative`,
the project also has a partially decoded inline roster family inside the same EQ
entry as the team metadata.

Current confirmed row contract:

- roster rows are treated as 5-byte records inside the decoded EQ entry
- the leading 2 bytes are a `0x61`-XOR'd little-endian 16-bit PID candidate
- in the current authoritative dataset, the trailing 3 bytes are invariant filler:
  `0x61 0x61 0x61` (`tail_bytes_hex=616161`)

The same 5-byte tail shape is now also confirmed across the current preferred fallback
same-entry families surfaced by the probe (`known_lineup_anchor_assisted`,
`adjacent_pseudo_team_record_reassignment`, `anchor_interval_monotonic_same_entry`,
and `heuristic_circular_shift_candidate`). That proves the row shape is broader than
just `same_entry_authoritative`, even though the team-to-run mapping confidence is still
different across those provenance levels.

That means the current authoritative same-entry row shape is effectively:

- bytes `0-1`: XOR'd little-endian PID
- bytes `2-4`: constant filler `0x61 0x61 0x61`

The writer still preserves the observed tail bytes defensively, but this is now a
materially stronger contract than a blind 2-byte overlay.

## Write Safety Boundaries

- Team text edits are safest when they are same-size or preserve the surrounding container layout.
- Indexed container writes are more sensitive because payload-length changes can require rebuilding offsets.
- Linked roster parsing is stronger than general team-field parsing; treat those as separate confidence levels.
- Unknown bytes outside the targeted text or roster region should be preserved.
- The external EQ->JUG linked roster table can now be edited safely one slot at a time
  when the row shape stays `flag + player_record_id` (5 bytes, same-size overlay).
- Authoritative same-entry roster rows can now be edited safely one non-empty slot at a time
  by changing the PID field within the now-confirmed `xor_pid + 0x61 0x61 0x61` 5-byte shape.
- `team-roster-edit-same-entry` now also accepts the strongest confirmed fallback mapping,
  `known_lineup_anchor_assisted`, when the selected preferred rows still validate the
  same `xor_pid + 0x61 0x61 0x61` contract.
- Those two proven row contracts can also be batch-edited safely from one CSV plan through
  `team-roster-batch-edit`, which validates row-by-row but commits them as one fixed-size
  overlay write with one backup.
- The main team overlay can now edit a selected authoritative roster row directly from the
  roster panel for both of those safe contracts:
  - linked rows can change `flag` and/or `player_record_id`
  - same-entry authoritative rows can change the PID field while preserving the observed filler tail
- The GUI also exposes the same shared batch path through `Batch Edit Team Roster from CSV...`
  in the Tools menu for the current confirmed linked and same-entry authoritative contracts.
- Variable-length team payload rewrites are still unsafe outside those proven fixed-size overlays.

## Known / Partial / Unknown

## Known

- team subrecord separator pattern
- team name extraction
- stadium name extraction
- parser-backed linked roster rows (`flag + player_record_id`)
- safe in-place mutation of one parser-backed linked roster slot (`flag` / `player_record_id`)
- authoritative same-entry inline roster rows with the current stable `xor_pid + 0x61 0x61 0x61` shape
- the same `616161` tail shape across all currently selected preferred same-entry fallback families
- GUI selected-row editing for authoritative linked and same-entry roster slots
- CLI and GUI batch editing for the proven linked and supported same-entry roster slot contracts
- GUI inspection of the confirmed roster sources through `Inspect Team Roster Sources...`,
  which surfaces the same parser-backed linked rows and authoritative same-entry coverage
  that the CLI exposes through `team-roster-linked` / `team-roster-extract`
- In the full GUI, that roster-source view now renders into the persistent `Analysis` tab
  workspace so the current coverage report stays visible while the user moves between teams.
- the `team-roster-profile-same-entry` CLI path, which now profiles the authoritative same-entry
  tail bytes directly and confirms whether they remain invariant across the current dataset

## Partial

- exact location and layout of many team metadata fields
- reliability of inferred team IDs outside strongly parsed cases
- meaning of all larger team-payload regions

## Unknown or Not Yet Safe

- full synthetic team-record rebuilding
- broad team metadata rewriting beyond the proven text paths
- any “invented” structural writes to unresolved team regions
- structural rewrites for roster modes other than the proven external EQ->JUG link table
- whether non-authoritative / fallback same-entry families also share the same invariant tail
- broader write safety for provisional same-entry mappings beyond `known_lineup_anchor_assisted`
  (the row shape is now proven wider than `same_entry_authoritative`, but mapping confidence
  still needs to justify writes provenance-by-provenance)

## Confidence Guidance

- If you need the most trustworthy team membership view, use the parser-backed EQ-to-JUG linked roster path.
- If you need the safest current roster write path, use the parser-backed `team-roster-edit-linked`
  flow and keep the edit to one fixed-size linked slot at a time.
- If a team has `same_entry_authoritative` coverage, `team-roster-edit-same-entry` is also safe
  for replacing the PID in one visible non-empty slot. The same command also supports
  `known_lineup_anchor_assisted` when that preferred fallback is present (for example, the
  current Manchester Utd path), but it still refuses weaker provisional provenances.
- `team-roster-profile-same-entry --include-fallbacks` now profiles all preferred same-entry
  provenances together and currently confirms the same `616161` tail across every selected
  preferred family in the real dataset.
- In the GUI, the same safe contracts are now available from the Team overlay roster panel
  through `Edit Selected Slot...` or by double-clicking a loaded supported same-entry roster row.
- If you need to apply many proven slot edits at once, use `team-roster-batch-edit` (CLI) or
  `Batch Edit Team Roster from CSV...` (GUI). The current CSV plan supports:
  - `team`, `slot`
  - optional `source` (`linked` or `same_entry`)
  - optional `eq_record_id` / `team_offset` for disambiguation
  - linked edits: `player_id` and/or `flag`
  - same-entry edits: `pid`
- In the GUI, the confirmed read-side roster sources are also available from
  `Inspect Team Roster Sources...`, which is a structured notebook-style UI counterpart to the
  current stable CLI roster reporting paths, including preferred fallback same-entry provenance
  when one exists.
- If you need general team metadata outside confirmed fields, treat it as heuristic unless the code explicitly models it.
