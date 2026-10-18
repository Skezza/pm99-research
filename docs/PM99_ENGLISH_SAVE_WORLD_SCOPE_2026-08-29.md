# Game-facing world scope for an English-managed PM99 save (2026-08-29)

**Status: closed scope milestone.** This document defines what the eventual
world build must change and what it must preserve. It is not a claim that the
world content has been compiled yet.

## Purpose

The target is the data PM99 consumes while the player manages an English club.
It is not a catalogue-quality database viewer and it is not a requirement to
perfect every field stored on an unplayable foreign carrier.

Foreign clubs cannot be selected as the manager's club through the normal
new-game flow. A normal game can nevertheless select one as a CPU pre-season
opponent, render its identity, and expose its players through the offer/profile
route.

## In scope for a world-season build

| Game-facing surface | Required data | Evidence |
| --- | --- | --- |
| CPU opponent identity | Existing club short/full/ground names, seated capacity, active manager link and compact UI kit | Barcelona is selected as Arsenal's CPU rival; match screens name Barcelona, Camp Nou and its manager, and the compact kit tile is live. |
| Transfer/scouting/profile | Existing player name, core facts, visible skills, roster owner and mini-photo/no-photo state | The foreign offer/profile routes prove `dd6360` player facts and current club resolution from the external roster graph. |
| Foreign squad source | Complete roster transaction between existing carrier rows | Barcelona/Real Madrid two-row control changes the offer list and the profile club in an untouched game. |
| Game-facing competition opponents | Existing foreign carrier identity is live after a draw; continental candidate-pool membership stays baseline-preserved until its source/writer is traced | Manchester United's Round 2 resolves to existing EQ 2151 Valletta, and a runtime `Valletta` -> `Test Valletta` indexed-name rebuild changes both fixtures. The English save still has no foreign domestic-table view. |

## Deliberately out of scope unless gameplay evidence appears

- Foreign manager biography/career prose and unproved display-name segments.
- Viewer-only historical annotations, source URLs and descriptive metadata.
- Foreign starting-finance candidates: preserve the baseline unless a targeted
  experiment proves an effect on AI or another player-visible simulation.
- Foreign tactics/starting XI beyond the existing baseline. The mode-1 grid is
  demonstrably consumed and validated, but there is no proof that changing it
  produces a player-visible result needed for the English-managed game.
- Unproved 3D/large-kit and home/away asset surfaces.
- Unknown tails, `attr0..attr2`, and all other preserve-only bytes.

## Compiler rule

For every foreign carrier used by the season build, change only a field with
both a bounded file contract and an English-save gameplay reason. Preserve all
other bytes. A content source being available is never, by itself, a reason to
write a field.

## Next research gate

The named-draw/carrier-read gate is closed: PM99 selects EQ 2151 Valletta and
reads its rebuilt variable-length name live. Trace the candidate-pool
membership source next, then prove one reversible pool transaction—or prove
that it is generated/executable and preserve it. The game's own English table
has no foreign domestic-league surface, so this remains a narrower and more
honest target than a guessed country/division field. See
[`PM99_ENGLISH_COMPETITION_RUNTIME_SCOPE_2026-08-29.md`](HISTORY/Investigations/PM99_ENGLISH_COMPETITION_RUNTIME_SCOPE_2026-08-29.md).

## Full-world release gate

Do not describe the database as a "fully updated world DB" until all of the
following are true:

1. the continental candidate-pool membership source and its permitted
   transaction are runtime-proven, or the release explicitly preserves the
   affected foreign topology;
2. a sourced season manifest has been compiled into the actual PM99 database
   files, rather than displayed only in a viewer;
3. every changed file has a receipt and parser/reopen validation, with all
   preserve-only bytes unchanged;
4. a fresh English-managed game proves the chosen club, squad, player
   profiles/photos, CPU opponents and relevant competition screens; and
5. the release notes list every deliberate baseline-preserved surface.
