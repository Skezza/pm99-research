# PM99 Season-Package Compiler V2

`scripts/season_package_compiler_v2.py` is the first native binary-writing
adapter for Season Pipeline V2. It compiles one strict canonical
`pm99-season-package-v2` document into an already-created, clean copy of a
verified PM99 base.

It is deliberately not an import of old 2015 ledgers or a patcher for a
previous release folder. The package is the authority. The base is read-only.
The output is a disposable materialisation.

## Current write contract

The compiler writes only these database files:

- `DBDAT/JUG98030.FDI`: player names, nationality, date of birth, height,
  weight and nine native skills.  The wider English mode-0 lane also includes
  proven broad position, roles, shirt number, opening order and dd6361
  handling.  A mode-1 carrier is deliberately narrower: its dd6360 name,
  core facts, nine skills, one primary fine role and paired broad-position
  bytes are writable. Secondary role lanes, shirt number, unknown controls
  and Handling remain unchanged.
- `DBDAT/EQ98030.FDI`: club name, ground name, full club name, seated
  capacity and existing manager links.  Mode 0 additionally has finance,
  opening tactics and parser-backed terminal roster-tail writes.  Mode 1 is a
  fixed-carrier transaction: the existing rows, flags and slot order are
  verified and retained, rather than rewritten.
- `DBDAT/ENT98030.FDI`: existing manager-profile names.

It verifies that those files in the materialisation initially match the base
byte-for-byte. It writes no backups, caches, runtime state, screenshots,
browser data or logs into the game tree. The V2 build-plan runner therefore
has a small and exact file surface to police.

The compiler fails closed when a carrier is absent, in the wrong family, has
no safe variable-name anchor, has an unsupported roster tail, or asks for an
unproven write. It also refuses to take a player from an unselected donor club
unless that donor roster can be parser-read, safely shortened and remains at
least 20 players deep.

There are intentional limits:

- It requires a strict native V2 package. A legacy-migrated package cannot
  claim that status merely because its old output can be replayed.
- It writes finance and opening tactics only for runtime-proven EQ mode 0.
  Mode 1 may receive the narrow fixed-slot transaction above, but cannot set
  finance, opening XI/tactics, shirt number, roles/positions, row count,
  row order, row flags, division, country or competition membership.
- A fresh mode-1 `dd6360` directory entry remains a hard error: PM99 can list
  it but cannot safely open its profile. A native package can instead declare
  one bounded `recycle_from_mode1_carrier_id` allocation. It must pair an
  exclusive mode-0 `dd6361` carrier with exactly one appended dd6361 clone,
  leave that clone in its original mode-0 roster, copy an existing mode-1
  dd6360 donor, and match the donor's primary role to one of the old carrier's
  stored dd6361 roles. The compiler verifies both roster graphs and records
  every such allocation. Any other cross-family reuse is rejected.
- Mode-1 `dd6361` remains a hard error. The one live foreign exception is a
  deliberately visible research gate, not a reason to use the English writer
  on a different layout.
- dd6360's tenth visible Handling value is preserved and listed in the
  compiler receipt. The compiler does not guess an adjacent-byte writer.
- It does not write league membership, kits, portraits or the calendar. Those
  are separate V2 stages with their own contracts and receipts.

## Editorial review and fine tuning

### Source-bound Italian opening-XI exception (2026-10-08)

`season_italian_opening_layer_v1.py` supports three explicitly reviewed clubs:
Milan 2000/01, Palermo 2005/06 and Atalanta 2006/07. It rederives original source
reviews against immutable registered releases, binds exact native identities and
ordered roster preimages, removes only reviewed stale/duplicate target links,
then applies the complete exclusive-owned startup-order permutation. It never
rewrites removed shared player records, guesses flag semantics, or grants
historical clearance to retained reserves. The compiler invokes pruning before
capturing the mode-1 roster baseline; later fixed-count/ownership guards remain.

This integration is not yet a certified factory rebuild of those full packages.
An actual factory attempt stopped at the existing unrelated duplicate-person
gate; it was not weakened. `./pm99-season build` supports an explicitly labelled
source-bound **known-good reconstruction** for an unchanged Italian-layer recipe:
reapply its plan to the immutable source release and prove the entire resulting
game inventory equals the repaired release. An additional unsupported recipe
edit is a hard error, never discarded. `--resume` verifies and reuses an already
completed candidate. Building alone does not make a candidate preferred; final
runner evidence and coordinated publication are separate requirements.

See [Italian opening-XI delivery](ITALIAN_OPENING_XI_DELIVERY_2026-10-08.md)
for source authority, evidence scope and unresolved historical queues.

Do not modify the downloaded/released game folder after testing it. Send the
release maintainer a normal change list; they record an evidence-backed
amendment in [Editorial Timeline V1](EDITORIAL_TIMELINE_V1.md), generate a
small canonical review overlay, rebuild from the same base, then publish the
new resulting revision.

An overlay is hash-locked to one package and can change only practical review
fields: player name/facts/individual rating values, manager name, safe club
metadata/roster/opening state, and portrait status. It cannot change a
division or competition membership. Its exact format is
[`pm99-season-review-overrides-v1.schema.json`](../schemas/pm99-season-review-overrides-v1.schema.json);
`scripts/season_editorial_timeline_v1.py build-overlay` is the normal writer.
Its compact, sorted JSON bytes are part of its identity. The compiler delegates
the overlay to `season_review_v2`, which derives a named in-memory V2 package
before it even opens the clean materialisation. A stale expected value,
duplicate target field, unknown target, unsupported field or package-hash
mismatch is therefore a no-write failure. The retired experimental
compiler-only overlay shape is explicitly versioned
`pm99-season-review-overrides-legacy-compiler-v0` and is not accepted by this
CLI or by a build plan.

The portrait status is intentionally only a request to the portrait stage:
`unresolved` and `native-no-photo` must result in PM99's native no-photo
state. The compiler receipt already lists the affected player IDs; the portrait
stage adds the attempted source/crop/conversion reason. It must not reuse a
carrier's 1999 face or block a database build.

## Direct use

The direct adapter is useful to produce a reference output while preparing a
reviewed build plan. It does not make the output a release by itself.

```bash
scripts/season_package_compiler_v2.py \
  --base-tree /secure/pm99-base \
  --tree work/2015-16-reference/game \
  --package seasons/2015-16/season-package.json \
  --overrides seasons/2015-16/reviews/first-gameplay-pass.json \
  --derived-package-id pm99-2015-16-r1 \
  --receipt work/2015-16-reference/compiler-receipt.json
```

`--receipt` is optional and must be outside the game tree. It is an execution
report, not a source input and not a substitute for the V2 release manifest.

## Build-plan integration

The real release route names this script as one hashed local command in
`pm99-season-build-plan-v2`. Its declared output paths are exactly, in lexical
order:

```text
DBDAT/ENT98030.FDI
DBDAT/EQ98030.FDI
DBDAT/JUG98030.FDI
```

Its command arguments are:

```text
--base-tree {base-tree}
--tree {materialisation-tree}
--package {season-package}
```

For a review release, declare the overlay as an external artifact with its
SHA-256 and add a deterministic, named source revision:

```text
--overrides {external-artifact:review-overrides}
--derived-package-id pm99-2015-16-r1
```

The stage receipt must include the overlay's hash-locked external-artifact
descriptor; the compiler receipt records both source and derived package
hashes plus the review-application receipt. The overlay is applied to a deep
copy in memory; neither the canonical source package nor a previous game
directory is modified. The equivalent explicit source step is
`season_review_v2.py apply`, which writes the derived package first and then
invokes the compiler without `--overrides`.

First generate a non-release reference materialisation to obtain the exact
three-file and final-tree inventories. Review those bytes and create the
canonical plan. Then let the build-plan runner create two fresh final trees;
both inventories and release manifests must match before runtime testing.

`scripts/test_season_package_compiler_v2.py` uses entirely synthetic PM99
containers to prove this adapter performs a real JUG/EQ/ENT rewrite, accepts a
hash-locked review overlay, and runs twice through the V2 build-plan runner
with byte-identical output. It also proves the mode-1 guard: a fixed foreign
carrier may alter only its proven core lanes; an attempted secondary-role,
shirt-number, row-flag or roster-order change is rejected before the
materialisation tree is touched. A separate synthetic transaction proves that
the mode-0 clone/mode-1 recycle route preserves both linked roster graphs and
rejects a loose role match.
