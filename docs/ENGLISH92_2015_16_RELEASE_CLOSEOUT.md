# 2015/16 English-92 release closeout

## Delivered build

The generated game is local-only at:

```text
.local/season-2015-16/english92-2015-16-build16-native-dd6360/game
```

It is a four-division 2015/16 English database, built without a fixed-width
rename fallback. The build contains:

- 92 clubs in the original competition-safe carrier blocks: 20 Premier League,
  24 Championship, 24 League One and 24 League Two;
- 2,299 linked players and 92 linked opening managers;
- variable-length player and manager names, core player biography, nationality,
  height, weight, broad position and core skills;
- 2015/16 club names, grounds, capacities, opening finance where the team mode
  has a proven finance contract, and linked club rosters;
- 2,299 player minifoto assignments, including 991 required loose
  `DBDAT/MINIFOTO/J96*.BMP` records;
- 92 PM99-scale 2015/16 home-kit renders in the five native kit archives;
- a separately version-checked calendar executable that rebases the game to
  2015/16 (853 recognised date operands; 2015 start, 2016 rollover).

`release-audit.json` is the machine-readable closeout receipt. It checks every
roster link, every native reserve-family payload, every portrait assignment,
all kit render counts, and the calendar patch before reporting success.

Every player has a face assignment rather than a generic silhouette. The
portrait receipt keeps per-record provenance and crop data. Ryan Lane uses a
dated 2013 Plymouth Argyle source; Ian Gayle is explicitly marked as an
official 2023 identity fallback after no redistributable target-era portrait
could be found. Neither is silently represented as an exact 2015 photograph.

## Runtime finding and repair

The initial full build exposed a real League Two error: Accrington Stanley
could start a new game but PM99 raised `Application cannot continue` when its
Squad screen opened. Removing the portrait layer did not change the failure.

The cause was the `dd6360` reserve-player family. Its decoded bytes 2--4 are
the family signature (`dd6360`); the generic player serializer treated byte 2
as a squad-number field and overwrote it. Static parsing still looked plausible,
but the game rejected the roster at runtime.

The repaired compiler keeps the variable-length native name writer, then writes
only the anchored native semantic block in place. All 218 affected records now
retain their signatures. A field-level audit verifies their primary role,
broad position, nationality, date of birth, height, weight and nine core skills
against the release ledger. The full-asset runner run for Accrington reaches
both the squad and a player profile.

## Runner evidence

The runner exercised the corrected DBDAT, full portrait layer and calendar EXE
as one disposable game copy. The following ten runs all report `success: true`,
reach the dashboard, open the squad/player profile route and have no blocking
error modal:

| Club shown in game | Player profile shown | Runner tag |
| --- | --- | --- |
| Arsenal | Kieran Gibbs | `english92_2015_build16_bio_arsenal` |
| Aston Villa | Brad Guzan | `english92_2015_build16_bio_aston` |
| Bournemouth | Artur Boruc | `english92_2015_build16_bio_bournemouth` |
| Birmingham City | Tomasz Kuszczak | `english92_2015_build16_bio_birmingham` |
| Blackburn Rovers | Simon Eastwood | `english92_2015_build16_bio_blackburn` |
| Bristol City | Frank Fielding | `english92_2015_build16_bio_bolton` |
| Barnsley | Adam Davies | `english92_2015_build16_bio_barnsley` |
| Blackpool | Colin Doyle | `english92_2015_build16_bio_blackpool` |
| AFC Wimbledon | James Shea | `english92_2015_build16_bio_wimbledon` |
| Accrington Stanley | Ross Etheridge | `english92_2015_build16_accrington_full` |

The Bristol City tag reflects the runner selector's historical coordinate grid;
the screenshot/profile is the authority for the club actually selected.

## Editor guardrails discovered here

1. Do not route `dd6360` records through the generic serializer. Use an
   anchored native writer, preserve its header and unknown bytes, and prove a
   25-player runtime roster after a change.
2. Treat a complete 24/25-player EQ roster as a game requirement. The parser
   can read a 20-player tail, but a fresh game can refuse to continue with it.
3. Team membership is the rebuilt EQ-to-JUG link table, not a guessed player
   header field. Allocate a player only once and remove a foreign donor link
   atomically.
4. `dd6360` saved secondary roles and shirt-number bytes remain read-only:
   primary role is written, but the full secondary-role and shirt-number
   controls remain `dd6361`-only until they have their own runtime contract.
5. A minifoto transaction has two legal targets: an existing `MINIFOTO.PKF`
   bitmap or a loose `DBDAT/MINIFOTO/J96<record-id>.BMP`. The browser editor
   must package both, with a manifest and hashes.
6. Kit art is separate from club metadata and keyed by carrier EQ id. A team
   rename or league move must not silently inherit a 1999 bitmap.
7. The historical calendar is an executable companion patch, not a database
   editor field. It needs its own version fingerprint and receipt.

## Deliberate accuracy boundaries

- The build uses a safe, position/rating-balanced 4-4-2 opening state. It is
  not a date-certified opening XI or bespoke opening tactical shape for every
  club; those require a separate match-sheet/tactics source ledger.
- 16 lower-league players use an explicitly marked PM99 tier/position skill
  baseline where no identity-safe edition rating was found. The ledger names
  every one; they must not be presented as individually source-rated.
- Two original English carrier teams are mode 1. Their opening finance is
  preserved rather than written through the mode-0 finance contract.
- Manager names and team links are updated; manager biography/career prose is
  preserve-only and may remain in its original language.
- The kit renders preserve 2015/16 colour/pattern identity at PM99 resolution,
  not sponsor/manufacturer detail. Thirteen BIGCAMP kit records do not exist in
  the original archive and are recorded as absent rather than fabricated.

These boundaries are release metadata, not hidden caveats: a future seasonal
compiler or the browser editor should surface them before generating a file.
