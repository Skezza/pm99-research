# Post-1999 26 registered releases: technical closeout

Date: 13 September 2026

## Outcome

All 26 worldwide season candidates from 2000/01 through 2025/26 are now
registered, locally playable and technically verified. Each preferred release
is bound to its season package, compiler/build receipts, complete game-tree
inventory, runtime attestation and final QA report.

This is the end of the automated engineering milestone. It is not a claim that
all historical and visual editorial work is complete.

## Reproduce, inspect and play

```bash
./pm99-season status
./pm99-season validate all
./pm99-season qa all --jobs 3
./pm99-season evidence all
./pm99-season play 2014-15
```

For a new deterministic release build, use a new release ID. An interrupted
batch can continue without rebuilding completed, hash-verified seasons:

```bash
./pm99-season build all \
  --release-id rc-quality-YYYYMMDD-rN \
  --jobs 3 \
  --resume \
  --register
```

The preferred-release catalogue is
`data/preferred-season-releases-v1.json`. It is the only season selection used
by status, validation, QA, play and runtime-proof commands.

## Final automated evidence

The final QA sweep at
`.local/season-qa-v2/rc-quality-20260913-r1-final/qa-report.json` reports:

- 26 seasons checked;
- 26 passed;
- zero blockers;
- 122 explicitly retained editorial warnings.

Every season has genuine runtime evidence from the exact registered release at
Stoke City's Line-Up screen. `./pm99-season evidence all` resolves and
hash-checks the 26 screenshots. Runtime proof now rejects a screenshot unless
OCR sees Stoke on the Line-Up screen; it also selects the Stoke row when the
screen initially opens on the opponent. This closed false positives discovered
with Watford, Burnley and Bolton during the proof run.

The zero-blocker checks cover package validity, compiled manager ownership,
position-aware Handling, representable nationalities, date plausibility,
opening-XI composition, club objective inputs, calendar identity, compiler
outputs and compact-kit binary/bitmap format.

## What remains for editorial review

The 122 warnings are visible work queues, not hidden release failures:

- all 26 seasons retain foreign clubs whose target-season managers lack an
  independent dated source;
- all 26 have missing secondary player facts which are allowed to preserve a
  safe fallback or remain unknown;
- all 26 still need explicit visual approval of the kits in-game;
- 25 contain one or more suspiciously flat or elite-heavy team rating
  distributions;
- 19 contain a nationality that PM99's native country table cannot represent.

The automated kit checks prove archive integrity, dimensions, palette/bitmap
compatibility and successful game loading. They do not prove that every kit's
shading, pattern or colours are historically or aesthetically correct. The
same distinction applies to ratings and provisional foreign managers.

These releases should therefore be described as **technically verified,
playable alpha/RC candidates**. User gameplay review can now produce small
recipe corrections without regenerating unrelated data.

## Failure and state rules now enforced

- A failed or interrupted batch never replaces the preferred catalogue.
- `--resume` reuses only finalized candidates whose hashes still verify.
- QA status is recorded only after a passing report is bound to the exact game
  path and package hash.
- A QA report is rehashed during release validation, so later mutation makes
  validation fail.
- Before QA is recorded, status says `not reviewed`; it no longer invents a
  zero-warning result.
- Runtime evidence is bound to both the release-manifest hash and full output
  inventory fingerprint.

The invalid 2015/16 Watford attestation was removed but its evidence and
rejection record were retained. Disposable remote overlays from interrupted or
rejected proof attempts were specifically unmounted and deleted; registered
releases and valid local evidence were not removed.
