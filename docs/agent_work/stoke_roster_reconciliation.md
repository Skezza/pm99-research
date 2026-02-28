# Stoke Roster Reconciliation (1998-08-08 v Northampton Town)

Date: 2026-02-25

## Inputs Used

- User-provided lineup screenshot (matchday squad, Saturday 8 August 1998)
- User-provided PDF of Stoke squad surnames (`/home/joe/Documents/2.pdf`)
- External context for full-name reconstruction:
  - Wikipedia `1998–99 Stoke City F.C. season` (squad statistics + early season match context)

## Reconstructed 20-Player Matchday Squad (for DB comparison)

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

## Current DB Extraction Results (`DBDAT/JUG98030.FDI`)

### `club-investigate "Stoke City" --include-heuristic` (default settings)

- Exact full-name matches in club index: **10 / 20**
- Club index size: **142** names (after alias-aware matching for `Stoke`, `Stoke C.`)

Matched (default):
- Carl Muggleton
- Larus Sigurdsson
- Richard Forsyth
- Kevin Keen
- Ray Wallace
- Peter Thorne
- Kyle Lightbourne
- Simon Sturridge
- Ben Petty
- Robert Heath

Missing (default):
- Clive Clarke
- Bryan Small
- Chris Short
- Phil Robinson
- Graham Kavanagh
- Stuart Fraser
- Dean Crowe
- David Oldfield
- Steve Woods
- Neil MacKenzie

### `club-investigate ... --heuristic-context 10000` (recall-oriented, noisy)

- Exact full-name matches in club index: **12 / 20**
- Club index size: **1174** names (precision degrades heavily)

Additional matches (wide-context only):
- Clive Clarke
- Stuart Fraser

## Separate Coverage Check (not club-linked)

Across the broader heuristic player scan (not requiring Stoke association), exact full-name matches exist for **13 / 20**.

This confirms multiple “missing” Stoke players are present in the DB but not yet being linked to Stoke by current club-association logic.

## Key Observations

- Alias-aware entry/query matching (`Stoke`, `Stoke C.`) materially improved recall for trainee-style blobs:
  - `Ben Petty` and `Robert Heath` now match via nearby `Stoke` mentions.
- Some true Stoke players (e.g. `Clive Clarke`, `Stuart Fraser`) only become discoverable with very large context windows because `Stoke` references are far away in large multi-player biography blobs.
- Large context windows recover more true positives but produce very large, noisy candidate sets.
- `Phil Robinson` remains a notable miss in current Stoke club extraction despite surname-level hits (e.g. `Les ROBINSON`) and a known in-game lineup presence.

## Working Conclusion

The DB contains enough signal to reconstruct a meaningful portion of a real in-game Stoke squad now, but reliable full-squad extraction will require one of:

1. Better parsing of structured player subrecords / team linkage, or
2. A roster-guided reconciliation pass (using known squad names/surnames from PDFs/screenshots), or
3. Improved biography-blob association logic with confidence controls and false-positive suppression.

## Useful Output Files (local)

- Combined Stoke export: `/tmp/stoke_city_players.json`, `/tmp/stoke_city_players.csv`
- Strict-only Stoke subset: `/tmp/stoke_city_players_strict.json`, `/tmp/stoke_city_players_strict.csv`
- Roster reconciliation CSV: `/tmp/stoke_roster_reconciliation.csv`
