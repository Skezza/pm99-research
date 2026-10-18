# Safe Source-Club Selection Manifests V1

## Purpose

`season_safe_source_club_selection_v1.py` converts only a narrowly defined,
mechanically proven subset of the collision-proposal queue into the existing
hash-bound `pm99-season-source-club-selection-manifest-v1` format.

It is a source-authoring aid, not a database build, release, runtime, or
historical-completeness claim. It writes new manifest files and one receipt
only; it does not alter a raw intake, its source credits, an allocation, a
draft package, a fixed carrier, or any PM99 file.

## Fail-closed policy

For every proposed pair, all of these conditions must hold before a manifest
entry is emitted:

1. The proposal has exactly two hash-bound selectors and one of the collision
   report's direct duplicate-label methods: organisation/abbreviation equality
   or a bare name plus a generic terminal suffix.
2. Every same-person evidence item traces exactly those two selectors.
3. Exactly one selector is an explicit opening source:
   `competition_catalog: soccerbase-august` and
   `source_path: soccerbase/team/<positive-id>/august`.
4. The other selector is non-August and has exactly one allocation assignment
   with the same full source identity and club name. It stays the canonical
   fixed-carrier identity; only its sourced player rows may later be replaced
   by the opening source through the existing selection projection.
5. Neither selector appears in any `ambiguous-player-interclub-overlap` item.
   Those overlaps are recorded as rejected in the receipt and never become
   automatic selections.

There is one further fail-closed boundary: a hash-bound known-conflict
exclusion manifest is mandatory input. It records prior adjudications which
the generic collision report cannot represent safely. An exclusion must bind
the report and collision-matrix hashes, current source intake and capture
hashes, one exact direct-proposal selector pair, and the named people found in
both raw source rows. It can only block automatic output; it cannot add a
selection.

The current exclusion input is
`.local/season-safe-source-club-selection-v1/known-interclub-exclusions-v1.json`.
It protects the known 2016/17 Braintree Town/Dover inter-club concern around
Jamie Grimes and Tyrone Marsh: its exact `Dover Athletic`/`Dover` report pair
is explicitly excluded pending dated opening evidence. `North Ferriby
United`/`Nth Ferriby` remains nonselectable because it does not satisfy the
collision report's exact direct-alias condition.

The generated manifest binds the immutable source-intake hash and source
capture hash. The downstream selection projection embeds the whole manifest
and source credits, so both the raw evidence and the generated decision remain
reviewable.

## Reproduce

Use a new output root. Existing roots are deliberately never replaced.

```bash
python3 scripts/season_safe_source_club_selection_v1.py \
  --proposal-report .local/season-source-club-selection-proposals-v1/20260904-r1/proposal-report.json \
  --collision-matrix .local/season-source-collision-matrix-v1/20260904/collision-matrix.json \
  --exclusion-manifest .local/season-safe-source-club-selection-v1/known-interclub-exclusions-v1.json \
  --output-root .local/season-safe-source-club-selection-v1/REVISION
```

The command validates the canonical proposal report, verifies that it is bound
to the supplied collision matrix, rechecks each source intake and allocation,
then writes one `selection-manifest.json` per season and a canonical
`safe-selection-receipt.json`. Running without `--output-root` is read-only
validation and reports the deterministic receipt hash.

The receipt records each safe selection's proposal ID, exact duplicate-label
method, same-person evidence count, canonical allocation carrier, explicitly
excluded known conflicts, and every rejection. It is the appropriate place to
review why a candidate was not selected; it does not conceal ambiguous source
claims by silently choosing an owner.

## Verified 25-season receipt

The current clean run is at
`.local/season-safe-source-club-selection-v1/20260904-r2/`:

- receipt: `safe-selection-receipt.json`
  (`011cb079cc1c99e9e985c041da08518e5952b26940e5796509d3eff0095bb648`)
- exclusion policy:
  `known-interclub-exclusions-v1.json`
  (`ac4e6e39ad2a3f8eb56572fdeba2bb80f60dc2ec5b07646ed8673d8872821083`)

It writes 25 source-selection manifests. Of 75 direct-label candidate pairs,
74 meet every automatic safety rule across 16 seasons. All 144 reported
ambiguous player/inter-club overlaps remain rejected. The single explicit
known conflict is the 2016/17 Dover pair: it is excluded, leaving four
auto-safe 2016/17 aliases (Aldershot Town, Forest Green Rovers, Sutton United,
and Torquay United). North Ferriby remains nonselectable under this policy.

## Boundaries

An emitted manifest is provisional source input only. A later source-selection
projection, fresh package-authoring replay, package validation, materialisation
and target-neutral runtime evidence remain required. It does not demonstrate a
playable game or historical accuracy by itself.
