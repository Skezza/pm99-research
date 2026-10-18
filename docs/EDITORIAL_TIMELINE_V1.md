# Editorial Timeline V1

## Purpose

The season package describes one PM99 materialisation. Its `player-123` and
`club-456` IDs are package records bound to PM99 carrier slots; they are not a
safe way to recognise a real person or club across 26 seasons.

`pm99-editorial-timeline-v1` is the small shared source layer above season
packages. It contains:

- one reconciled identity for each real club and person;
- a binding from that identity to the carrier record used in each season;
- time-scoped editorial amendments, with a reason and evidence reference.

It is source data, never a game folder, FDI, PKF or executable patch.

## Normal editing workflow

The maintainer does **not** write JSON review overlays. They send an ordinary
change list, for example:

```text
2015/16
- Bojan Krkic: shooting should be 86, not 82.
- Remove the portrait on [player]: it is the wrong person.
- Stoke: Britannia Stadium capacity should be 27,740.
```

The editor/release maintainer resolves the named person or club to its shared
identity, attaches the evidence already retained for that season, and records
one amendment in the timeline. A name that could mean two people is not
guessed: the response names the candidates and asks for the intended one.

For a build, the timeline produces a new guarded
`pm99-season-review-overrides-v1` overlay for that specific season package.
The existing review mechanism then verifies the current expected value and
creates a new derived package. A stale correction therefore cannot quietly
land on a replacement carrier record.

```text
plain-English feedback
  -> curated editorial timeline amendment
  -> freshly generated, package-hash-locked review overlay
  -> derived season package
  -> clean PM99 materialisation, audit and playtest
```

The feedback is entered once. An amendment can apply to one season, a run of
seasons, or every season in which the same identity has a binding. It is not a
hand-maintained chain of package patches.

## Identity guardrail

Every strict native V2 package now requires:

- `clubs[].identity_id`; and
- `players[].person_id` and `managers[].person_id`.

Those IDs are editorial identities, deliberately separate from `carrier_id`.
One person can have both `player` and `manager` roles over time. A native
package must make this assignment deliberately, using the season source and
recorded evidence.

The legacy 2015 package is intentionally not auto-filled. Its old ledger has
multiple carrier records with identical player name, birth date and
nationality. Treating that as proof of identity would silently merge records
that might be duplicate imports, not the same real person. The migration keeps
that fact visible; reconciling those records is a native-source authoring task.

`seed` will refuse a package without these IDs rather than manufacture them.
That is an important protection for the long-term programme.

## Commands

These are maintainer/CI commands. They are not a required user interface.

```bash
# Inspect an older package first. Candidate duplicates are listed but never
# auto-merged into a real-world identity.
python3 scripts/season_editorial_timeline_v1.py audit-package \
  --package .local/season-pipeline-v2/2015-english92-legacy-a.json \
  --output work/2015-16-identity-audit.json

# A native, identity-complete package establishes the initial shared map.
python3 scripts/season_editorial_timeline_v1.py seed \
  --package seasons/2015-16/season-package.json \
  --timeline-id pm99-editorial-2000-2026 \
  --output seasons/editorial-timeline.json

# Validate the durable shared source.
python3 scripts/season_editorial_timeline_v1.py validate \
  --timeline seasons/editorial-timeline.json

# Create the exact package-bound review overlay for a clean rebuild.
python3 scripts/season_editorial_timeline_v1.py build-overlay \
  --package seasons/2015-16/season-package.json \
  --timeline seasons/editorial-timeline.json \
  --override-id pm99-2015-16-editorial-r1 \
  --output work/2015-16-editorial-r1.overrides.json
```

All files are canonical JSON and hashable. The `build-overlay` command requires
complete bindings for that season and requires the amendment's evidence
artifact to be present in the target package. It can change only the fields
already proven safe by the review contract.

## What becomes authoritative

The original PM99 installation remains immutable. It is always the clean base.
The authoritative historical source is:

1. the identity-complete season package for season-specific facts, assets,
   carriers, lineup and tactics; and
2. the shared editorial timeline for cross-season identity and corrections.

A released game directory is disposable output. We never hand-edit it after a
test. When a feedback batch is accepted, it becomes a named source amendment;
the next build starts from the clean base and regenerates all applicable
changes. Periodic source checkpoints may fold a settled package revision into
the season package for readability, but the original package, timeline and
receipt remain retained so the result is reproducible.

## Remaining work before 26 complete seasons

The implementation removes the structural duplication problem. It does not
manufacture historical data. Each season still needs an identity-complete
source package, evidence-backed player/club/manager data, assets and the usual
clean build/audit/playtest. The foreign fixed-carrier lane may update proven
content but remains unable to change country, division, competition membership
or draw topology until executable-level research proves such writes.
