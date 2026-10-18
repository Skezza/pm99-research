# Season quality QA v1

`pm99-season qa` is the release-quality gate for a generated season. It is
deliberately separate from the fast structural `validate` command:

```bash
./pm99-season validate 2020-21
./pm99-season qa 2020-21
./pm99-season qa all
```

The command exits zero only when every requested season has no blocker. A
candidate may still compile, launch and reach Line-Up while failing QA; that
candidate is **runner-proven**, not **quality-approved**.

## Checks

- The preferred game tree and required runtime files exist.
- The exact resolved season package passes the package contract.
- Every English club agrees with its dated opening-manager source layer.
- Ratings use the package contract's inclusive 0..100 byte range; known outfield players cannot have
  goalkeeper-like Handling, and goalkeepers cannot have implausibly low
  Handling.
- Birth dates are plausible at 1 August of the season; present heights and
  weights are plausible. Missing secondary facts are reported as warnings,
  following the agreed fallback policy.
- Every written opening XI contains exactly one goalkeeper.
- Written managers have the expected active club ownership in the compiled
  `EQ98030.FDI`/`ENT98030.FDI` graph. Manager names use accent-insensitive
  comparison because the game's storage may transliterate them.
- Handling is decoded from compiled `JUG98030.FDI` and compared with the
  recipe using stable carrier IDs. Package-declared compact `dd6360` reads
  take precedence over the cross-entry `dd6361` biography scan, and valid
  `dd6361` carriers outside that biography index use the compiler's proven
  tail-byte readback contract.
- Compiler output hashes and the season calendar executable match their
  receipts/inputs.
- Compiled compact-kit archives match their materialisation receipts, and
  every changed bitmap has the required 8-bit OS/2 dimensions. Missing visual
  approval remains an explicit warning because structural correctness cannot
  establish that a kit looks right.
- Matching-calendar runner evidence reached Line-Up and contains one genuine
  Line-Up screenshot.

For 2015/16, English source QA uses the build-36 English-92 manifest because
the later worldwide effective package is an overlay, not a complete English
recipe. This distinction is what exposes the compiled manager collisions
without incorrectly blaming the source ledger.

## Reports

Per-season reports are written to:

```text
.local/season-qa-v1/<season>/qa-report.json
```

The batch summary is written to:

```text
.local/season-qa-v1/qa-report.json
```

Each blocker includes an affected-row count and bounded samples. Warnings are
non-blocking editorial queues. Reports are local generated evidence and do not
contain proprietary database binaries.

## Remediation loop

Fix source or deterministic transformation logic, rebuild only the affected
season, then run:

```bash
./pm99-season validate <season>
./pm99-season qa <season>
./pm99-season play <season>
```

Do not hand-edit compiled files to satisfy QA. The recipe and compiler receipt
must remain the reproducible source of truth.

## Final registered-release sweep — 2026-09-13

The repaired, runtime-proved preferred releases were audited again and the
passing reports were bound back to their exact package and game-tree hashes:

```bash
./pm99-season qa all --jobs 3 \
  --output-root .local/season-qa-v2/rc-quality-20260913-r1-final
./pm99-season record-qa \
  .local/season-qa-v2/rc-quality-20260913-r1-final all
./pm99-season validate all
```

Result: 26 passed, zero blockers and 122 retained editorial warnings. See
`POST1999_26_REGISTERED_RELEASE_CLOSEOUT_2026-09-13.md` for the exact boundary
between technical verification and remaining historical/visual review.

## First 26-season baseline — 2026-09-07

Command:

```bash
./pm99-season qa all
```

Result: 26 audited, 0 quality-approved, 26 failed. This does not retract the
structural/playable candidates: all 26 preferred game trees and package
contracts passed. It means they cannot yet be described as historically
quality-approved.

Passing evidence:

- 26/26 preferred game trees available.
- 26/26 package contracts valid.
- 2,392/2,392 dated English manager assignments match their recipes; zero
  source mismatches or missing joins.
- 26/26 compact-kit sets pass archive-hash and bitmap-format readback.
- 25/26 matching-calendar runner proofs pass.
- 25/26 calendar inputs pass; 2015/16 lacks the standard cached calendar
  input.
- Zero compiler-receipt output hash mismatches (2015/16 has no standard
  compiler receipt and is warned separately).

Blocker queues (counts can overlap because one player can fail recipe and
compiled checks):

- Player rating plausibility: the initial report counted 11,599 rows. Review
  showed that 22 per season were legal zero-valued preserved placeholders,
  not invalid ratings. The real systematic issues were 7,093 implausibly low
  goalkeeper Handling values across the 25 post-1999 packages and 3,934
  outfield Handling values above 20 in 2015/16.
- Compiled Handling/readback: 10,028 rows across 26 seasons.
- Temporally impossible birth dates: 1,815 rows across 15 seasons, concentrated
  in the earlier databases.
- Opening XI goalkeeper composition: 39 clubs across 18 seasons.
- Compiled manager links: 36 English clubs in 2015/16 only. The source ledger
  and build manifest agree 92/92, but later worldwide compilation overwrote
  shared manager carriers. This includes Diego Simeone/Newcastle United,
  Jackie McNamara/Southampton and Eduardo Berizzo/Stoke City.
- Matching-calendar runtime proof: 2004/05 only.
- Calendar provenance: 2015/16 only.

Non-blocking queues cover missing secondary player facts, foreign-manager
target-season evidence and kit visual approval. Automated kit correctness does
not claim that the rendered designs look historically or aesthetically right.

## Position-aware remediation — 2026-09-07

The provisional package normalizer now applies both deterministic rules:

- known outfield positions (`D`, `M`, `F`): Handling 1..20;
- goalkeepers: Handling at least `max(35, quality - 12)`.

Unknown whole-record preservation rows are left byte-for-byte alone. Every
change is recorded in `handling-normalisation-audit.json`; acquired inputs and
previous playable candidates are not overwritten.

The compiler's separately anchored `dd6361` Handling pass now covers both club
modes. Its existing signature, nine-skill anchor and post-write readback remain
mandatory. The independent QA reader was also corrected so it does not confuse
numeric carrier IDs found by two different family scanners.

Focused 25-season result:

```text
.local/season-quality-remediation-v1/qa-matrix-v2.json
25 seasons checked
25 passed manifest rating plausibility
25 passed compiled Handling readback
25 passed compiled manager ownership
25 passed compiler output hashes
```

The matrix is a **clean-static quality-remediation** gate, not a new playable
release claim. It deliberately retains the existing runtime/calendar/kit
evidence until the corrected database files are promoted into new complete
runtime candidates.

Remaining historical queues are 1,815 date/identity findings and 39 opening-XI
goalkeeper-composition findings. The date queue is mostly evidence that a 2015
fallback player identity remains in a target-season club; changing only the
birth year would conceal the source gap, so these rows require target-season
roster backfill or an explicit native preservation decision.

The separate 2015/16 quality revision corrected all 3,934 outfield Handling
values and passes compiled Handling readback. It is not promoted: the legacy
world overlay still needs a composed English/world manager allocation so that
the verified 92 English manager links cannot be reused by foreign clubs. The
foreign kit appearance issue also remains open.

Re-run the focused post-1999 binary audit with:

```bash
python3 scripts/audit_season_quality_remediation_v1.py \
  --output .local/season-quality-remediation-v1/qa-matrix-NEXT.json \
  --jobs 4
```
