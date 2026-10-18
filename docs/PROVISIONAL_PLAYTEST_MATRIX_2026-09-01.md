# Provisional playtest matrix: 2000/01–2025/26

## Status

This matrix provides 26 locally selectable, hash-locked **playtest targets**:
25 isolated calendar variants plus the existing 2015/16 known-good world
release. It is deliberately not a claim that 26 historical databases are
complete.

Each calendar variant keeps the complete 2015/16 world game tree intact and
regenerates only `MANAGPRE.EXE` for its target opening year. Its canonical
inventory receipt proves that every player database, team database, manager
database, kit and portrait byte is identical to the 2015/16 baseline.

The target matrix index is local-only and canonical:

```text
.local/provisional-playtests/pm99-2000-2025-provisional-playtest-r1.json
SHA-256: 8f9fb0af56522b28d0b84242fba7f88c025079b3b266f5ba9ec2b98dde83ae9f
```

Run `python3 tools/season_preset_browser.py` to inspect the local presets.
It discovers these installed playtest manifests automatically alongside each
season's source manifests; no JSON upload or hosted site is involved. The
matrix shows the 2015/16 known-good baseline separately from the 25
provisional calendar clones, plus the exact permitted output delta.

## What each row means

| Row kind | Game content | Calendar | Historical claim |
| --- | --- | --- | --- |
| `known-good-baseline` (2015/16) | Verified 2015/16 world release | 2015/16 | Existing 2015/16 engineering release only |
| `calendar-only-provisional` | Byte-identical 2015/16 player, club, manager, kit and portrait content | Target season's opening year | None for target-season database content |

The calendar variants are available for installation, launch, menu/navigation,
save-flow and calendar playtesting. They are not eligible for target-season
Stoke line-up screenshots or historical accuracy review: such a screenshot
would show 2015/16 Stoke content under a different clock and would be
misleading.

## Invariants

For every calendar variant, the builder requires all of the following:

1. Copy an existing game root into a new, never-before-used directory; it never
   edits the source release.
2. Reconstruct the source release calendar from the fingerprinted pristine
   executable and require its SHA-256 to equal the baseline executable.
3. Generate the target calendar from that same pristine executable.
4. Compare complete source and output inventories and accept exactly one changed
   path: `MANAGPRE.EXE`.
5. Run `validate-database` on the copied `JUG98030.FDI`, `EQ98030.FDI` and
   `ENT98030.FDI` before writing the immutable manifest.

The known-good 2015/16 workspace was checked before the matrix was built.
Runtime evidence is intentionally outside the immutable game receipt: it is
time- and environment-dependent and cannot affect a rebuild.

## Regenerate, verify, and change one thing

The local command surface for all 25 provisional targets is:

```bash
python3 scripts/season_playtest_commands_v1.py prepare
python3 scripts/season_playtest_commands_v1.py commands
python3 scripts/season_playtest_commands_v1.py play --season 2000-01 --session first-save
```

`prepare` never replaces an existing preset: it verifies it first, or creates
it in a new directory. `play` verifies the selected immutable preset, then
creates or resumes a separate named mutable session under
`.local/provisional-playtests/sessions/`. A player save therefore cannot alter
the hash-locked playtest preset. `commands` prints the 25 direct invocations.
All of these commands remain calendar-only provisional playtests under the
limitations above.

Build a fresh calendar-only clone with the exact same input contract:

```bash
python3 scripts/season_playtest_variant_v1.py create \
  --source-game-root .local/season-workspace-v1/2015-16-final-clean-game \
  --calendar-source-exe .local/season-pipeline-v2/pm99-base-clean/MANAGPRE.EXE \
  --output-root .local/provisional-playtests \
  --variant-id pm99-2000-01-calendar-playtest-r1 \
  --baseline-id pm99-2015-16-world-r0 \
  --baseline-season 2015-16 \
  --target-season 2000-01
```

The tool refuses to replace an existing output. Verify a build later without
modifying it:

```bash
python3 scripts/season_playtest_variant_v1.py verify \
  --variant-root .local/provisional-playtests/pm99-2000-01-calendar-playtest-r1
```

For a true data correction, do not hand-edit a cloned FDI/PKF/EXE. Start from a
strict season package and make a narrow `pm99-season-review-overrides-v1`
overlay with identity, expected-old-value and evidence hash. The current
2015/16 workspace already implements this source-only path through
`scripts/season_review_v2.py` and `scripts/season_workspace_v1.py`; rebuild to
a new release directory and compare its output inventory. Omitting that one
overlay is the deterministic revert. The other seasons need strict packages
before this same field-level correction path is historically meaningful.

## Local storage

The 25 full isolated copies consume roughly 10 GB. They are local-only cache
artifacts; no tracked repository file or baseline release is modified. Do not
delete a variant while it is being reviewed. When a replacement becomes
necessary, retain its manifest/receipts for traceability and remove only the
fully resolved individual variant directory after confirming it is not the
selected review target.
