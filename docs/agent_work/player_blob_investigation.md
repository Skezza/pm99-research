# Player Blob Investigation Notes

Date: 2026-02-25

## Scope

Investigate why some player-name hits (example: `Peter THORNE`) are found by search but do not resolve to a reliable roster record / team ID, and build tooling to discover club-associated players from player data blobs.

## Findings (Current)

- There are at least two important classes of player-name hits in `DBDAT/JUG98030.FDI`:
  - **Strict subrecord hits**: separator-delimited player subrecords inside large decoded entries (new source label: `entry-subrecord (strict)`).
  - **Heuristic blob hits**: scanner matches inside larger biography/news/history text blobs (existing source labels `scanner (marker)` / `scanner (no marker)`).
- `Peter THORNE` is currently a **heuristic blob hit**, not a strict roster/subrecord hit.
  - Heuristic search finds `Peter THORNE` at `0x001C1DBC`.
  - Strict search returns no match for `Peter Thorne`.
  - Therefore no parser-certified `team_id` is available for that hit yet.
- Nearby-club extraction from the enclosing decoded blob for `Peter THORNE` shows:
  - `Swindon Town (97)`
  - `Swindon Town`
  - `Blackburn Rovers`
  - `Hartlepool United`
  - `Stoke City`
- This supports a **context-based association** workflow for background players, but it remains heuristic.

## Tooling Added (Investigation Support)

- `player-search --strict`
  - Uses sequential entry-boundary scan plus strict player subrecord extraction.
  - Avoids many embedded-text false positives.
- `player-investigate`
  - Compares heuristic vs strict matches for a player name.
  - Shows enclosing decoded entry + nearby club-like mentions.
- `club-investigate`
  - Finds players associated with a club mention using two evidence tiers:
    - strict subrecord context (higher confidence)
    - scanner-only heuristic context (lower confidence; optional)
  - Now builds a **confidence-ranked club index** (`club_index`) and supports export (`--export .json/.csv`)
  - Can attempt a **derived club->team record** resolution using `EQ98030.FDI` (`--teams-file`, auto-infer by default)
  - Exposes strict subrecord header probe bytes (for reverse-engineering the missing team linkage)

## Stoke City Example (Current Evidence)

Command:

```bash
python3 -m app.cli club-investigate DBDAT/JUG98030.FDI "Stoke City" --include-heuristic
```

Observed useful output:

- **Strict subrecord context matches** (example set included):
  - `Rob MARSHALL`
  - `Paul MILES`
  - `Darren HARMON`
  - `Richard NUGENT`
  - `Steve BERRY`
  - `Eddie KING`
  - `Russell STOCK`
- **Heuristic context matches** can include background/non-strict names, and with larger heuristic context can include:
  - `Peter THORNE`

Notes:

- `club-investigate` uses `--heuristic-context 800` by default for heuristic matches to catch broader biography references (including cases like `Peter THORNE`).
- Strict subrecord associations are generally more precise than scanner-only associations.
- `club-investigate` now also matches query aliases (e.g. `Stoke`, `Stoke C.`) in nearby text and in entry prefiltering, which improves recall for trainee/abbreviated biography entries.
- `club-investigate --json` now emits a ranked `club_index` payload that can be exported directly:

```bash
python3 -m app.cli club-investigate DBDAT/JUG98030.FDI "Stoke City" \
  --include-heuristic --export stoke_club_index.csv
```

- Current CSV export includes:
  - confidence score/band
  - best evidence type
  - strict vs heuristic evidence counts
  - strict subrecord group-byte probe(s)
  - derived team linkage fields (when resolvable)

## New Reverse-Engineering Clue (Strict Subrecord Header)

- Strict Stoke subrecord matches currently share a common **subrecord group byte**:
  - `subrecord_group_byte = 0x4B` for the observed strict Stoke set
- This is extracted from the raw strict subrecord prefix (separator-delimited chunk), e.g. prefix patterns like:
  - `dd6360 75 4b 60 ...`
  - `dd6360 74 4b 60 ...`
- Interpretation (working hypothesis):
  - byte 3 varies per player (likely per-player slot/index within the container)
  - byte 4 (`0x4B` for Stoke sample) may be a **club/group code**
- This is not yet a decoded canonical PM99 `team_id`, but it is a useful clustering signal for strict subrecords.

## Stoke Matchday Roster Reconciliation (8 Aug 1998 screenshot + PDF surnames)

Using:
- the user-provided lineup screenshot (Northampton Town vs Stoke C., 8 Aug 1998), and
- the user-provided surnames PDF,
- plus external roster context (Wikipedia 1998–99 Stoke City season page),

the following 20-player matchday squad was reconstructed for comparison against DB extraction:

- Carl Muggleton
- Clive Clarke
- Bryan Small
- Larus Sigurdsson
- Chris Short
- Richard Forsyth
- Kevin Keen
- Ray Wallace
- Peter Thorne
- Phil Robinson
- Graham Kavanagh
- Kyle Lightbourne
- Stuart Fraser
- Dean Crowe
- David Oldfield
- Simon Sturridge
- Steve Woods
- Neil MacKenzie
- Ben Petty
- Robert Heath

Current extraction coverage (code-only, `JUG98030.FDI`):

- **10/20 exact full-name matches** in `club-investigate "Stoke City" --include-heuristic` (default heuristic context)
  - includes `Ben PETTY` and `Robert HEATH` after alias-aware entry/query mention matching (`Stoke`)
- **13/20 exact full-name matches** exist somewhere in the broader player DB heuristic scan (not necessarily Stoke-associated by current club logic)
- **12/20 exact full-name matches** can be surfaced in `club-investigate` with a very large heuristic context window (e.g. `--heuristic-context 10000`), but precision degrades heavily (club index size explodes)

Implication:
- The data is sufficient to recover a meaningful portion of a real in-game squad already.
- Remaining misses are primarily parser/association limitations (especially long-distance biography references and some absent/variant name forms), not a complete lack of signal.

## Derived Team Resolution Status (Current Limitation)

- `club-investigate` can optionally resolve the club query to `EQ98030.FDI` team records (derived linkage only).
- In the current parser coverage, `gather_team_records()` on `DBDAT/EQ98030.FDI` loads only a subset (e.g. 24 teams), and `Stoke City` is not currently resolved there.
- Result:
  - `resolved_teams = []` for `Stoke City` at present
  - `derived_team_linkage` remains `unresolved` in exported rows

## Working Hypothesis

- The PM99 player file mixes:
  - structured/semi-structured player subrecords (often parseable names, weak/no team IDs with current parser), and
  - richer narrative/biography text blobs containing player names plus club history.
- “Star” players are more often represented in strict subrecord form, while some “background” players may only be discoverable heuristically from biography blobs.

## Next Technical Targets

1. Decode the strict player subrecord header bytes well enough to convert group-byte clues (e.g. `0x4B`) into canonical club/team IDs.
2. Improve `EQ98030.FDI` team parsing coverage so derived club->team resolution succeeds for clubs like `Stoke City`.
3. Add optional filtering to `club-investigate` export (`--min-confidence`, strict-only / heuristic-only) for curation workflows.
4. Add a roster-reconciliation helper that accepts known squad names (or surnames) and reports:
   - exact match
   - surname candidate(s)
   - confidence band
   - likely false positive / likely miss

## Caveats

- Club association from nearby text is **not** the same as a canonical roster/team ID.
- A player biography may mention multiple clubs; “current club” inference is not yet deterministic.
- Large heuristic contexts improve recall (e.g., `Peter THORNE`) but increase false positives.
