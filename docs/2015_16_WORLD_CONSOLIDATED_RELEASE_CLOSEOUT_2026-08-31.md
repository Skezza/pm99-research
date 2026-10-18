# 2015/16 worldwide consolidated release closeout

## Result

The consolidation milestone is closed. The worldwide database is now built
from the verified clean 2015 English layer, not from a cumulatively modified
foreign database. Database records, portraits and kits all have separate,
hashable receipts.

## Release coverage

| Area | Final result |
| --- | --- |
| Foreign club carriers | 451 fixed carriers; no additions, removals or country moves |
| Dated full-source clubs | 395 |
| Foreign player carriers | 9,177 unique native carriers |
| Dated player writes | 8,112, including 48 partial-source rows |
| Source depth omitted | 177 players across 76 clubs because native squad capacity is fixed |
| Manager writes | 174; 273 unidentified/shared manager entities preserved |
| Ratings | 3,688 FIFA fallback, 4,374 deterministic context, 5 keeper guards, 1,110 preserve/partial |
| Foreign portraits | 3,350 applied; every other package player explicitly native no-photo |
| Foreign compact kits | 268 applied; 127 sourced-club fallbacks named |
| Competition topology | Preserved exactly |

There are no fabricated editorial-rating labels and no random portrait
substitutions. Missing images fail open and remain editable later.

## Proof

- Workspace validation and final clean compilation pass.
- Two clean compilations reproduce the same JUG, EQ and ENT hashes.
- The clean-base audit passes with every fixed roster tail unchanged.
- 250 PM99RE script tests pass. Twelve launcher tests are environment-blocked
  by the runner dirty-check; the actual runner routes below execute
  successfully.
- Repository boundary and `git diff --check` pass.
- Stoke runtime proof:
  `upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_clean_final_guarded_stoke_20260831/summary.json`.
- Barcelona opponent proof:
  `artifacts/mode1_dashboard_route/world2015_clean_final_barcelona_opponent_20260831/summary.json`.

## Run locally

```bash
cd /home/joe/pm99-research/.local/releases/pm99-2015-16-world
wine ./MANAGPRE.EXE
```

## Repeatability

Future seasons use the same workspace, strict package, editorial timeline and
clean compiler. The 2015 portrait rebinder exists only to migrate conversions
made before clean carrier binding; new seasons bind assets to package
identities from the start. User feedback is added to the permanent editorial
timeline and a new clean release is compiled—released binaries are never
edited in place.
