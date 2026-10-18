# World fixed-carrier content-ledger baseline (2026-08-30)

## Result

The foreign-world programme now has a reproducible content-authoring ledger.
It is deliberately separate from both the database editor and the previous
English 2015 build scripts.

`scripts/world_fixed_carrier_ledger_v2.py` read the verified clean V2 base and
generated a baseline-locked registry of the game's existing mode-1 carrier
slots. It then generated an empty `2015/16` world ledger and audited it.
Neither operation writes a PM99 database file.

The generated registry/ledger are local build artifacts, not repository data:

```text
.local/season-pipeline-v2/world-fixed-carriers.json
.local/season-pipeline-v2/world-2015-16-ledger.json
.local/season-pipeline-v2/world-2015-16-ledger-audit.json
```

## Baseline result

| Item | Result |
| --- | ---: |
| Fixed mode-1 foreign carriers | 451 |
| Existing foreign roster slots | 9,390 |
| Minimum / maximum slots on one carrier | 1 / 55 |
| Carriers below current compiler's 16-row minimum | 8 |
| Mode-1 non-`dd6360` linked player rows | 1 |
| Shared baseline JUG carrier IDs in the mode-1 graph | 36 |
| Completed sourced foreign 2015/16 carriers | 0 |

The empty ledger is intentional and truthful: the English 2015/16 release is
not evidence that the other 451 carriers have been historically sourced.

The registry hash for this verified base was:

```text
209e55136da3e0432603c15d2b577aba64a009bd7396a467cafeece2ed9d051a
```

Every season ledger contains that hash. A different baseline needs a new
registry and cannot silently reuse the existing assignments.

## What the ledger enforces

- A source file is content-addressed. Club, manager, player, ratings and
  portrait facts all reference captured SHA-256 source artifacts.
- A completed carrier contains every pre-existing roster slot, with the same
  slot index, JUG ID and row order. It cannot silently transfer, add, remove
  or reorder a player.
- One historical person cannot be assigned to two different JUG carriers.
  Conversely, when legacy PM99 shares a JUG carrier between slots, every
  occurrence must have exactly the same historical identity/content.
- Every completed player has an `applied` portrait or an explicit
  `native-no-photo` reason. `unresolved` is allowed only while research is
  still draft/blocked.
- No country, division, draw pool, competition or membership field exists in
  this format.

## Exact remaining blockers

1. Enter and hash-capture historical sources for all 451 carrier records and
   9,390 existing player slots. The current audit correctly reports all 451 as
   unassigned.
2. Thirty-six shared mode-1 JUG IDs must receive a compatible single identity
   or be documented as blocked; they cannot be independently repurposed.
3. Broad position and the six compact tactical-role candidates are compiler
   fields with live-game proof. Shirt numbers, opening XI/tactics ordering and
   finance are still preserve-only for mode 1.
4. Foreign topology (country, division, draw pool and competition membership)
   is a scope exclusion. This ledger adds no back door around that decision.

This closes the "untracked world content" gap. It does not claim a completed
world 2015/16 database.
