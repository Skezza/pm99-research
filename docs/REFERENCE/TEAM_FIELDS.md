# Team Fields Reference

This is the authoritative team-record reference for the current codebase.

For container-level rules, use [../DATA_FORMATS.md](../DATA_FORMATS.md). For parser and loader behavior, cross-check [../../app/loaders.py](../../app/loaders.py), [../../app/models.py](../../app/models.py), and [../../app/eq_jug_linked.py](../../app/eq_jug_linked.py).

## Scope

This document describes the team and roster data the project can currently parse conservatively from `EQ98030.FDI`.

## Confirmed Team Sources

The project currently recognizes two main team-related paths:

1. `TeamRecord` parsing from `EQ98030.FDI` team subrecords
2. Parser-backed EQ-to-JUG linked roster extraction via `app/eq_jug_linked.py`

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

## Write Safety Boundaries

- Team text edits are safest when they are same-size or preserve the surrounding container layout.
- Indexed container writes are more sensitive because payload-length changes can require rebuilding offsets.
- Linked roster parsing is stronger than general team-field parsing; treat those as separate confidence levels.
- Unknown bytes outside the targeted text or roster region should be preserved.

## Known / Partial / Unknown

## Known

- team subrecord separator pattern
- team name extraction
- stadium name extraction
- parser-backed linked roster rows (`flag + player_record_id`)

## Partial

- exact location and layout of many team metadata fields
- reliability of inferred team IDs outside strongly parsed cases
- meaning of all larger team-payload regions

## Unknown or Not Yet Safe

- full synthetic team-record rebuilding
- broad team metadata rewriting beyond the proven text paths
- any “invented” structural writes to unresolved team regions

## Confidence Guidance

- If you need the most trustworthy team membership view, use the parser-backed EQ-to-JUG linked roster path.
- If you need general team metadata outside confirmed fields, treat it as heuristic unless the code explicitly models it.
