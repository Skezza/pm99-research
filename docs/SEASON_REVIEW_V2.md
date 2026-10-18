# PM99 season review and correction workflow

A released PM99 game directory is evidence, not editable source.  After a
playtest, record each correction in a small canonical source overlay, create a
new season package, then make a new clean build.  Do not hand-edit FDIs, PKFs
or EXEs in a produced release folder.

The person reviewing the game does not need to author that overlay. They send a
plain change list; the release maintainer resolves it to the shared identity
and season package, then generates this low-level overlay from
[Editorial Timeline V1](EDITORIAL_TIMELINE_V1.md). This preserves a simple
editorial workflow without making an ambiguous player name a database write.

`scripts/season_review_v2.py` implements this feedback loop. It accepts only
proven PM99 fields: player facts and individual visible ratings; manager and
club metadata; the proven opening-lineup/formation/tactics fields; and player
portrait dispositions. It never opens or changes a generated game tree.

## Portrait review queue: fail open, but visible

Portraits are not a release blocker. A missing, bad, unsafe or uncertain image
becomes PM99's native no-photo state. It must disable any inherited archive or
loose minifoto, never use a 1998 carrier face, random replacement or a
placeholder.

The portrait stage produces an outcome for every player:

- `applied`; or
- `native-no-photo`, with a reason code and explanation.

The review queue emits only the latter. Each entry contains the player name,
club name, carrier ID, package declaration, resulting state, explicit PM99
native-no-photo state, reason code and reason. This is both human-readable and
machine-readable JSON.

For an older face receipt, normalise it and create the queue:

```bash
python3 scripts/season_review_v2.py normalise-face-receipt \
  --package .local/season-pipeline-v2/2015-english92-legacy-review-v2.json \
  --face-receipt .local/season-2015-16/english92-2015-16-editorial-v1-r2/face-stage-receipt.json \
  --output .local/season-pipeline-v2/2015-english92-portrait-results-v1.json

python3 scripts/season_review_v2.py portrait-queue \
  --package .local/season-pipeline-v2/2015-english92-legacy-review-v2.json \
  --portrait-results .local/season-pipeline-v2/2015-english92-portrait-results-v1.json \
  --output .local/season-pipeline-v2/2015-english92-portrait-review-queue-v1.json
```

The qualified English 2015 review queue has six deliberate native no-photo
rows: Ben Ledger (Scunthorpe United), Lee Marshall (Swindon Town), Jordan
Chiedozie (Cambridge United), Peter Denton (Hartlepool United), Joe Green
(Newport County), and James Needle (Yeovil Town). Their individual reasons are
in the local JSON queue, not hidden in a release note.

The workflow was also exercised against the earlier incomplete 2015 face run:
it produced a 92-row automatic-failure queue, split into 85
`face-stage-no-identity-safe-close-era-source` rows and seven
`face-stage-download-failed` rows. Those are distinct machine codes, while the
qualified release has only the six reviewed no-photo decisions above.

## Safe targeted feedback overlays

`pm99-season-review-overrides-v1` is a package-bound source overlay. It names
the exact SHA-256 of the package that was reviewed and contains an `expected`
value for every changed field. It fails rather than applying a comment to the
wrong player or a newer package. It also requires a reason and a hashed
evidence artifact/proof. Rating changes must add rating provenance and a
source; a new portrait must name all normal source/crop/conversion/container
artifacts. A known wrong portrait can always be changed to native no-photo.

The format is defined in
[pm99-season-review-overrides-v1.schema.json](../schemas/pm99-season-review-overrides-v1.schema.json).
This is the intentionally narrow list of editable feedback paths:

- Player name, date of birth, nationality, height, weight, primary position,
  fine roles, shirt number and individual visible ratings.
- Club name, ground, capacity, finance, division, opening XI/substitutes,
  formation and proven tactics-grid coordinates.
- Manager name.
- Portrait: `set-native-no-photo`, or an evidence-backed `set-applied`.

Apply an overlay to make a new source package and an application receipt:

```bash
python3 scripts/season_review_v2.py apply \
  --package season-2015-16.json \
  --overrides season-2015-16-review-r1.json \
  --derived-package-id pm99-2015-16-r1 \
  --output season-2015-16-r1.json \
  --receipt season-2015-16-r1-review-receipt.json
```

The original package is unchanged. The new package and receipt bind the input
package, feedback overlay and derived package hashes. The native V2 compiler
will consume that new package, followed by the normal clean build, audit,
two-build comparison and runtime qualification.

The current legacy cached-output bridge is deliberately immutable: it replays
an exact old package/output pair and rejects a different package hash. For a
legacy correction, use the proven legacy builder to make and audit corrected
output, then retain a new approved cache bundle. Once the native V2 compiler
stage is used, the overlay feeds the clean rebuild directly.
