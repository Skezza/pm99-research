# PM99 world carrier scope (2026-08-28)

## The useful definition of "every club internationally"

PM99 has 543 modern club records in `EQ98030.FDI`:

| Record mode | Count | Current meaning |
| --- | ---: | --- |
| `0` | 92 | English playable-club profile layout |
| `1` | 451 | Other-club / non-playable profile layout |

The 451 mode-1 records include the vast majority of the game's foreign clubs.
They are the realistic international scope for a historical PM99 database.

Mode is a **record layout**, not a country or competition flag.  It therefore
cannot be used to infer that a particular club is foreign: two old English
records are mode 1, while all 92 proven English 2015 carriers are mode 0.

"Every real club in the world" is a different project.  PM99 has fixed carrier,
player, competition and asset capacity.  Adding clubs beyond the existing 543
would be executable/engine expansion work, not a safe database replacement.

## What is already safe

- The authoritative indexed EQ→JUG parser now resolves a roster for all 543
  modern carriers. This is a structural roster map, **not** permission to
  change mode-1 roster links or a reliable country/competition map.
- The final manager link in every one of the 543 EQ records is parser-backed.
  Existing-final-ID replacement is runtime-proven in both layouts: Barcelona
  proves the mode-1 `1069 -> 1641` link.  Its variable-length manager surname
  rebuild is also proven in both ENT profile families; the separate
  full-profile display-name segment and biography/career prose remain
  preserve-only.
- Variable-length club, full-club and stadium strings have a parser-backed
  rebuild and were proven at runtime on a foreign club profile.
- The 92 English carrier transaction is proven as a complete club state:
  name, stadium, roster, manager link, kit, opening lineup and tactics.  A
  mode-1 carrier has the same proven text, manager, roster, core `dd6360`
  player and compact UI kit lanes, but not a complete mode-1 opening-state or
  competition transaction.

## What is not yet a global editor contract

- Broad writes for foreign-player families. The player corpus has 11,479
  indexed records and the current indexed-directory audit decodes and parses
  all 11,479. That is **syntactic parsing**, not semantic write coverage. In
  particular, the generic `dd6360` marker is three or four bytes after the
  native metadata cursor, so it produces credible-but-wrong foreign facts.
  The native cursor is now audited for all 9,353 `dd6360` rows, but its writer
  and mode-1 runtime behaviour must still be proved. Two legacy birth-year
  encodings (JUG 28453 and 29678) remain preserve-only.
  The carrier inventory now makes the pilot size precise: mode-1 club rosters
  contain 9,211 `dd6360` links and just one `dd6361` link (Marcus Bignot,
  JUG 10958, at Kidderminster Harriers).  The first two foreign player
  fixtures therefore need to cover the `dd6360` gap-3 and gap-4 cursors;
  the lone `dd6361` mode-1 row remains a separately named regression proof.
- Competition membership and continental/international competition structure.
  No raw "division" field is known or safe to expose.
- Mode-1 external roster rows are consumed by the foreign offer list and the
  player profile's club resolution, but only when the source and target rows
  are updated as one transaction. The 2026-08-29 Barcelona/Raúl control found
  35 baseline duplicate JUG ids; generated historical data must be unique
  until duplicate/loan semantics are traced. Row-count/flag semantics and a
  country-wide opening-state proof remain open.
- Foreign compact UI kit art is fully addressed by existing carrier id:
  `MINIESC`, `NANOESC` and `RIDIESC` each contain every modern carrier's
  `EQ96<id>.BMP` record.  Barcelona's changed selector tile proves that route.
  The large `BIGCAMP`/`BIGESC` archives are English-only in stock PM99 and
  must not be populated for foreign clubs.  Other kit render surfaces remain
  unproved.

## Recommended next milestone: world-carrier contract pilot

Do not start by curating hundreds of clubs.  First prove a small representative
set of existing mode-1 carriers—one club each from several countries and at
least one non-European league—through a disposable game run.

The pilot must provide:

1. a registry for all 451 carriers (country, visible competition, slot and
   record form), explicitly separating mode from nationality;
2. write/read/runtime contracts for club strings, manager link and the actual
   player-family shapes used by the sample clubs;
3. player identity, nationality, positions, core attributes and minifoto
   proofs for those shapes, with opaque records preserved;
4. a roster/asset transaction audit, including kits; and
5. game screenshots of club profiles, player profiles, transfer/search paths
   and affected competition views.

If that pilot is clean, the data programme can cover **every existing PM99
world-club carrier** for a season.  If it exposes a family-specific failure,
we limit or preserve that family instead of corrupting hundreds of clubs.
