# Opening-date identity reconciliation V1

An historical PM99 database represents one date, not a whole season. A player
who joined a second club in January must not appear for both clubs in a new
game started in August. This check is now a required source gate for every
native season package.

## What the check does

`scripts/reconcile_opening_date_identities_v1.py` compares a candidate package
with every club's certified first-fixture XI and bench.

- The candidate key is normalised display name + date of birth + nationality.
  It is deliberately conservative: it flags something that needs review; it
  does not claim the rows are definitely the same human.
- If exactly one existing carrier appears in its dated first-fixture evidence,
  the tool retains that one and declares every other carrier a source
  replacement slot.
- Otherwise, it produces a named queue. A dated decision must retain one
  carrier or explicitly replace every candidate when the person was outside
  the selected PM99 scope at the snapshot.
- It does not delete a row, move a player by editing an output folder, or make
  up a replacement. A club's full opening-date roster ledger supplies the
  actual replacement person and facts.

The decisions and resulting receipt are canonical JSON and hash-bound to the
specific package and first-fixture reconciliation. Changing either makes the
old decision unusable.

## 2015/16 English result

The first run against the legacy-derived English 2015 source found 126
same-person candidate groups:

| Evidence route | Groups | Result |
| --- | ---: | --- |
| First-fixture XI/bench | 110 | One carrier is retained, and an existing duplicate carrier needs a real opening-date replacement. |
| Dated editorial decisions | 16 | All resolved; one player, Elvis Manu, must be replaced at both English carriers because neither club was his on 8 August 2015. |
| Outstanding membership decisions | 0 | No one is silently retained based on a full-season roster page. |

The combined receipt names **128 replacement carrier slots**. That number is a
work queue, not a permission to fill those slots with generic players. The
next authoring pass must source the actual opening-date squad member for each
slot, give them one shared person identity, facts, rating provenance and an
explicit portrait/no-photo outcome.

The 16 dated decisions live in
[`scripts/data/2015-16-opening-date-identity-decisions-v1.json`](../scripts/data/2015-16-opening-date-identity-decisions-v1.json).
They retain their source links as editorial evidence labels. A strict release
will additionally capture the relevant source content in the asset store and
bind it as a V2 source artifact; a URL alone is intentionally not sufficient
for strict provenance.

## Commands

```bash
# Create a package-specific queue from a clean candidate package and the
# certified first-fixture source.
python3 scripts/reconcile_opening_date_identities_v1.py \
  --package seasons/2015-16/season-package.json \
  --opening-lineups sources/2015-16/first-fixtures.json \
  --output work/2015-16-opening-date-identity-queue.json

# Apply only the dated editorial membership decisions. This writes a receipt,
# never a game database.
python3 scripts/reconcile_opening_date_identities_v1.py \
  --package seasons/2015-16/season-package.json \
  --opening-lineups sources/2015-16/first-fixtures.json \
  --decisions seasons/2015-16/opening-date-identity-decisions.json \
  --output work/2015-16-opening-date-identity-resolution.json
```

`season_package_v2.py validate --strict` independently rejects unresolved
same-person candidate rows. This means a package cannot accidentally bypass
the queue just because its `person_id` fields happen to be unique.

## Repeatable 2000–2026 workflow

For each season:

1. choose and record the snapshot date;
2. capture the opening fixture and full opening-date squad source;
3. bind actual people and clubs to shared editorial identities;
4. run this reconciliation and resolve every candidate with dated evidence;
5. author the named replacement rows in the season source;
6. create a fresh strict package, assets, clean materialisation, audit and
   runtime playtest.

The shared timeline carries accepted corrections across seasons by real person
or club identity. Each season package carries only the time-specific facts and
the carrier assignment for that year. Thus a later report such as “Bojan
shooting should be 86” becomes one source amendment and a clean rebuild—not an
unrepeatable modification of a released 2015 game directory.
