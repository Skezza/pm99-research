# World fixed-carrier content ledger V2

`scripts/world_fixed_carrier_ledger_v2.py` is the reusable authoring boundary
for the foreign part of a historical PM99 season. It separates two things that
must not get mixed up:

1. the immutable PM99 carrier slots and roster rows present in the approved
   baseline; and
2. sourced historical content assigned to those slots for one season.

It is deliberately not a database writer. It never edits PM99 files and it
has no country, division, competition, draw-pool or membership field.

That makes it suitable for every season from 2000/01 onward: create the fixed
carrier registry once for an approved base, create one hash-locked ledger per
season, capture sources and review data, then compile only the fields that
have a runtime contract.

## 1. Register the carrier baseline

Run this against a clean, approved PM99 `DBDAT` directory:

```bash
python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat /secure/pm99-base/DBDAT \
  --registry-id pm99-base-world-carriers \
  --output seasons/base/world-fixed-carriers.json
```

The registry fingerprints `EQ98030.FDI`, `JUG98030.FDI` and `ENT98030.FDI`,
then records all modern mode-1 carriers, their exact roster slot index, JUG
carrier ID, flag, player family and current final manager link. It does not
infer a league from record order or from the mode byte.

The expected PM99 corpus has 451 mode-1 carriers. The registry also records
pre-existing shared JUG IDs. Those are a real allocation constraint, not
permission to give one player record two historical identities.

## 1a. Bind historic clubs to reviewed host carriers

Before creating a foreign content transaction, bind its immutable carrier to a
reviewed preseason-picker host-country capture and a dated squad capture:

```bash
# Build a one-tile fresh-route capture, run it on the PM99 runner, inspect its
# screenshot, then create a host mapping report. Do not use a multi-click sweep.
python3 scripts/foreign_carrier_assignment_v1.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers.json \
  --source-capture .local/season-sources/footballsquads-2015-16.json \
  --host-report .local/season-pipeline-v2/foreign-host-spain-20260830-report.json \
  --host-report .local/season-pipeline-v2/foreign-host-spain-tile-4-report.json \
  --initialise --assignment-id world-2015-16-fixed-carriers \
  --output .local/season-pipeline-v2/world-2015-16-carrier-assignments.json

# Apply small, reviewable season decisions without changing the source ledger.
python3 scripts/foreign_carrier_assignment_v1.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers.json \
  --source-capture .local/season-sources/footballsquads-2015-16.json \
  --assignment .local/season-pipeline-v2/world-2015-16-carrier-assignments.json \
  --proposal scripts/data/2015-16-foreign-spain-identity-proposal-v1.json \
  --output .local/season-pipeline-v2/world-2015-16-carrier-assignments-derived.json
```

`foreign_carrier_assignment_v1.py` makes the mapping reproducible and fails
closed if the PM99 base, historic source capture, picker screenshot, country,
carrier capacity or source club are inconsistent. Its `approved` state means
only **identity assignment is supported**. It is not a complete carrier
transaction and cannot be described as a database release until the remaining
club, manager, player, kit, portrait/no-photo and runtime gates below pass.

The historic source's `competition_catalog` is retained for provenance only.
It must never be used as a PM99 division, membership or draw-pool write.

## 2. Create a season ledger

```bash
python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/base/world-fixed-carriers.json \
  --ledger-id world-2015-16 \
  --start-year 2015 \
  --output seasons/2015-16/world-fixed-carrier-ledger.json
```

The empty ledger is useful: it truthfully says that zero world carriers have
been researched rather than quietly falling back to 1998 content. It includes
the registry hash, so changing the base must produce a new registry and new
season ledger.

### Optional FIFA 16 review prefill

The local FIFA 16 snapshot can accelerate human work without granting itself
authority it does not have:

```bash
python3 scripts/prepare_2015_world_fifa16_drafts.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers.json \
  --base-ledger .local/season-pipeline-v2/world-2015-16-ledger.json \
  --fifa16-player-csv .local/season-2015-16/fifa16-player-stats.csv \
  --output-ledger .local/season-pipeline-v2/world-2015-16-fifa16-prefill-ledger.json \
  --output-report .local/season-pipeline-v2/world-2015-16-fifa16-prefill-report.json
```

It only creates **blocked**, fixed-slot draft rows where one current PM99 club
name has one exact normalised FIFA club-name match and enough complete FIFA
player rows for its existing roster capacity. Player rows are assigned in
ascending FIFA kit-number / player-id order solely to make review repeatable;
that is explicitly *not* an opening-XI, tactics, PM99 ordering or membership
claim. It never writes PM99 data.

Every generated row retains explicit blockers for club metadata, manager, kit,
portrait/no-photo decisions, slot review, foreign membership, and the
unproven mode-1 role/position/shirt-number/opening-state lanes. Unsupported
nationalities become PM99's visible `XXX` placeholder and are listed by FIFA
player ID in the report; they cannot quietly become a historical nationality.
The command accepts only an empty hash-locked ledger, so it cannot overwrite
or merge reviewed editorial decisions by accident.

### Incremental foreign core-writer QA package

The prefill can also derive a **strict but deliberately partial** native V2
package. It is for exercising the proven foreign core-player writer before
the actual historical content ledger is complete; it is not a world release.

```bash
python3 scripts/derive_2015_world_fifa16_core_package.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers.json \
  --blocked-ledger .local/season-pipeline-v2/world-2015-16-fifa16-prefill-ledger.json \
  --base-tree .local/season-pipeline-v2/pm99-base-clean \
  --output-package .local/season-pipeline-v2/world-2015-16-fifa16-core-package.json \
  --output-report .local/season-pipeline-v2/world-2015-16-fifa16-core-package-report.json
```

It preserves existing fixed roster rows, manager carrier/name, club ground and
capacity, shirt numbers, opening state, kit and portrait archives. It writes
only the mode-1 `dd6360` player name, nationality, birth date, height, weight,
all ten stored profile skills and the six fine-role candidates. The compiler receipt must show
`preserved-mode1-unproven` opening/finance and every selected carrier in
`mode1_dd6360_core_written_carrier_ids`. A game generated from this package
is a labelled incremental runtime-QA build, never evidence that the preserved
lanes are correct for 2015/16.

Where a modern full name cannot fit an existing foreign carrier's *variable*
name payload, the derivation tries the full name, then a review-recorded
`A. Surname`, then the surname. It does not use fixed-field truncation. Every
chosen display alias is listed in the package report for editorial correction.

Before composition, run the no-write topology guard against the candidate
tree. It must report `changed_carrier_count: 0`; the foreign derivation also
refuses a tree that fails this condition.

```bash
python3 scripts/audit_foreign_mode1_roster_topology.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers.json \
  --dbdat <candidate-tree>/DBDAT \
  --output <candidate-tree>/foreign-mode1-topology-audit.json
```

The core package has no source-approved portraits. Before any game profile
capture, materialise its `unresolved` rows as PM99's real no-photo state. The
stage disables a matching inherited MINIFOTO entry and removes a loose
override; it never substitutes a carrier face.

```bash
python3 scripts/materialise_native_no_photo_v2.py \
  --package .local/season-pipeline-v2/world-2015-16-fifa16-core-package.json \
  --game-tree <compiled-tree> \
  --receipt <compiled-tree>/native-no-photo-receipt.json
```

### Reproducible English-plus-foreign incremental proof

The first safe composition must start from the corrected English tree, not
from the earlier English output which changed foreign roster tails.  This is
an executable **incremental proof** for nine foreign carriers / 194 players;
it is not a claimed worldwide 2015/16 release.

```bash
set -euo pipefail
root=.local/season-pipeline-v2
base=$root/english92-mode0-append-2015-16-20260830-b/game
tag=english92-mode0-append-2015-16-20260830-b
registry=$root/world-fixed-carriers-$tag.json
ledger=$root/world-2015-16-ledger-$tag.json
prefill=$root/world-2015-16-fifa16-prefill-ledger-$tag.json
package=$root/world-2015-16-fifa16-core-package-$tag.json
output=$root/world2015-english92-plus-foreign-core-20260830/game

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat "$base/DBDAT" --registry-id world-fixed-carriers-$tag \
  --output "$registry"
python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry "$registry" --ledger-id world-2015-16-$tag --start-year 2015 \
  --output "$ledger"
python3 scripts/prepare_2015_world_fifa16_drafts.py \
  --registry "$registry" --base-ledger "$ledger" \
  --fifa16-player-csv .local/season-2015-16/fifa16-player-stats.csv \
  --output-ledger "$prefill" --output-report "$root/world-2015-16-fifa16-prefill-report-$tag.json"
python3 scripts/derive_2015_world_fifa16_core_package.py \
  --registry "$registry" --blocked-ledger "$prefill" --base-tree "$base" \
  --output-package "$package" \
  --output-report "$root/world-2015-16-fifa16-core-package-report-$tag.json"

# Create a new output directory; do not alter $base in place.
mkdir -p "$(dirname "$output")"
cp -a "$base" "$output"
python3 scripts/season_package_compiler_v2.py \
  --base-tree "$base" --tree "$output" --package "$package" \
  --receipt "$(dirname "$output")/foreign-core-compiler-receipt.json"
python3 scripts/materialise_native_no_photo_v2.py \
  --package "$package" --game-tree "$output" \
  --receipt "$(dirname "$output")/foreign-core-native-no-photo-receipt.json"
python3 scripts/audit_foreign_mode1_roster_topology.py \
  --registry "$registry" --dbdat "$output/DBDAT" \
  --output "$(dirname "$output")/foreign-mode1-topology-audit-after-no-photo.json"
```

The final audit must say `changed_carrier_count: 0` out of all 451 foreign
mode-1 roster tails.  The compiler rejects a requested foreign player if
writing it would remove that player from an unselected mode-1 owner.  This
means an incremental candidate can shrink when the safe shared-JUG rule
excludes a proposed carrier; it must never "repair" that by changing a donor
club's roster.

For a runner profile proof, copy a small JSON file naming the registry,
package, compiler receipt, native-no-photo receipt and topology-audit hashes
with `--provenance-file`; both runner wrappers store it as
`input-provenance.json` beside their remote-visible `dbdat_override.sha256`.
The Rüdiger proof uses the game-wide **Search Player By Name** route because
the pre-season Italy picker visibly exposes only a subset of the fixed Italian
carriers.  A picker label must not be inferred from EQ record order.

That proof is deliberately DBDAT-only: it visibly establishes a changed Roma
player name, club, nationality, physical data, core ratings and native
no-photo state.  It does **not** apply the separate executable clock patch,
so PM99's original 1998 start date makes a 1993-born Rüdiger appear as age 5.
Never use that run as date-patch evidence; a dated public release composes the
clock patch as its own, independently qualified artifact.

Each completed carrier update contains:

- sourced club identity, ground and capacity;
- one explicit era-correct kit decision, with approved kit source material;
- the existing manager carrier, sourced manager identity/name;
- one row for **every existing roster slot**, with the same slot index and
  JUG carrier ID as the registry;
- player identity, facts, ratings and source references;
- one explicit portrait decision per player: `applied` or
  `native-no-photo`.

Every source is a content-addressed local capture: an id, title, kind and
SHA-256. This is intentionally stronger than retaining a website URL that may
later change. The data can separately record human-readable source notes in
the capture artifact itself.

`native-no-photo` is the fail-open portrait policy. It needs a short reason and the
player remains in the build. `unresolved` is allowed only while a carrier is
`draft` or `blocked`; a `complete` carrier cannot hide an unresolved portrait.
The audit lists every disposition, so a manual game review can turn “wrong
face” into an explicit no-photo or approved replacement instead of an
untracked fix.

## 3. Validate and audit coverage

```bash
python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/base/world-fixed-carriers.json \
  --ledger seasons/2015-16/world-fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/base/world-fixed-carriers.json \
  --ledger seasons/2015-16/world-fixed-carrier-ledger.json \
  --output work/2015-16/world-content-audit.json
```

The audit is the release-facing answer to “what remains?” It reports:

- the number of all 451 carriers that are unassigned, draft, blocked or
  complete;
- completed roster-slot, kit and portrait/no-photo counts;
- all mode-1 non-`dd6360` player rows;
- pre-existing shared JUG carrier IDs; and
- the permanent foreign-topology preservation rule.

The ledger validator rejects:

- a different base registry hash;
- a new/reordered player carrier, changed roster flag, or manager relink;
- a person assigned to two different JUG/ENT carriers;
- conflicting content assigned to a baseline-shared JUG carrier;
- uncited club/player/manager facts;
- a completed carrier without approved kit source material;
- a completed carrier with a missing or unresolved portrait decision; and
- any unrecognised field, including a guessed membership/division field.

## How it joins the compiler

The ledger is source authority, not the compiler's input package. A future
adapter will derive a strict `pm99-season-package-v2` only when each requested
row fits the currently proven write surface.

Today the V2 compiler can make a fixed mode-1 transaction for existing
`dd6360` carriers: player name, nationality, broad position, date of birth,
height/weight, the ten stored profile values (including Handling) and the six
fine-role candidates; club strings/capacity; and the existing final manager
link. The isolated `dd6361` row has a byte-preserving core route. It does not
write shirt number, opening state, finance, roster movement or foreign
topology. Those omitted historical facts remain visible in the ledger and
appear as compile blockers rather than being silently discarded.

This gives us a sustainable flow for 26 seasons:

```text
approved base registry (once)
  → one source ledger per season
  → review corrections as new source-ledger revisions
  → strict package derived for the fields that are proven
  → clean materialisation, audit and playtest
```

No release folder is ever hand-edited. A review note becomes a small, sourced
change to the season ledger, then a new reproducible build.

## Current blockers for a fully historic world release

The ledger makes these visible; it does not pretend they are solved:

1. Historical source content still has to be captured for each of the 451
   carriers and their existing roster slots.
2. Historical shirt numbers, foreign opening XI and tactics need their own
   mode-1 contracts. The static tactics grid is read by PM99, but its player
   ordering has not yet been tied to the immutable foreign roster slots.
   Broad position and fine-role candidates are proved compact write surfaces.
3. Shared baseline JUG IDs need a compatible single identity or an explicit
   blocker; they cannot be independently repurposed in two places.
4. Country, division, continental draw pool and competition membership are
   scope exclusions. The ledger deliberately cannot write them.

The complete machine grammar is in
[`pm99-world-fixed-carrier-ledger-v2.schema.json`](../schemas/pm99-world-fixed-carrier-ledger-v2.schema.json);
cross-record and baseline integrity checks live in the Python validator.
