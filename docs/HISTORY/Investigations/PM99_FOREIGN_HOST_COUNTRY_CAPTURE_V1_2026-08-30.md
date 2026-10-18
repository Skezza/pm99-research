# PM99 foreign host-country capture V1 (2026-08-30)

## What this closes

The first world ledger had no way to distinguish an existing foreign carrier's
*host country* from a guess based on its EQ number or its current club name.
The normal PM99 preseason rival picker does expose that relationship visibly:
selecting a country flag produces its fixed grid of existing club carriers.

`scripts/foreign_host_mapping_v1.py` records this as a small, auditable map.
It binds a reviewed picker frame to the decoded EQ record shown by the base
database.  It never calls the result a competition table, because the picker
does not prove a domestic division or a continental draw pool.

## Spain capture

The runner capture `foreign_host_spain_tile_sweep_20260830` opened the Europe
map, chose the visible Spain flag at `(67,250)`, then stepped across the
twenty visible Spanish tiles.  The run is local under:

```
.local/runlogs/foreign-host-mapping/foreign_host_spain_tile_sweep_20260830/
```

The corresponding reviewed input is:

```
scripts/data/foreign-host-spain-20260830-v1.json
```

The first pass intentionally does **not** claim all twenty as complete. The
screen has only four friendly-opponent slots: clicking another shirt mutates
the provisional rival list, rather than providing an independent carrier
probe. The earlier explanation that transparent shirt pixels caused the later
repeats was incomplete. The verifier now accepts **one** reviewed post-click
frame per fresh preseason route and marks every later row in a multi-click
route `route-selection-capacity-exhausted`. This is a release guard, not a
cosmetic warning: a stale or stateful picker frame must never assign a club to
the wrong fixed carrier.

Use the reusable runner front door for a deterministic recapture. Create a
single-tile capture JSON for each shirt, start a fresh route for it, then
review and bind that one frame. The wrapper now refuses a multi-tile JSON. A
generic centre offset is not adequate because striped shirts can be transparent
at different x positions:

```bash
python3 scripts/foreign_host_capture_tile_v1.py --prepare \
  --capture scripts/data/foreign-host-spain-20260830-v1.json \
  --tile-index 4 \
  --output .local/season-pipeline-v2/foreign-host-spain-tile-4-candidate.json

scripts/run_foreign_host_country_capture_v1.sh \
  --capture .local/season-pipeline-v2/foreign-host-spain-tile-4-candidate.json \
  --local-game-dir .local/research-probes/dd6360-mode1-native-20260829 \
  --artifact-root .local/runlogs/foreign-host-mapping \
  --run-tag foreign_host_spain_tile4_fresh_20260830

# Inspect the screenshot, then bind its digest into a reviewed capture.
python3 scripts/foreign_host_capture_tile_v1.py --review \
  --capture .local/season-pipeline-v2/foreign-host-spain-tile-4-candidate.json \
  --capture-root .local/runlogs/foreign-host-mapping/foreign_host_spain_tile4_fresh_20260830 \
  --output scripts/data/foreign-host-spain-tile-4-20260830-v1.json
```

The source capture carries the reviewed SHA-256 for every expected frame. A
recapture is intentionally rejected if it overwrites those screenshots; copy
the successful capture to a new reviewed capture JSON and update the digests
only after visual review. That prevents a new runner frame from silently being
treated as the old approved evidence.

`compare_foreign_host_capture_frames_v1.py` remains useful for diagnosing a
single tile across independent fresh runs. The former 20-tile comparison only
proved the stateful selector behaviour; it cannot be promoted to a
one-carrier-per-shirt map.

Run the audit against any candidate base:

```bash
python3 scripts/foreign_host_mapping_v1.py \
  --capture scripts/data/foreign-host-spain-tile-4-20260830-v1.json \
  --capture-root .local/runlogs/foreign-host-mapping/foreign_host_spain_tile4_fresh_20260830 \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output .local/season-pipeline-v2/foreign-host-spain-20260830-report.json
```

## Safe use

An accepted result means only:

> This immutable EQ record belongs to the visible Spanish host group in the
> stock preseason picker.

It authorises assigning 2015 club content to that same fixed record, after all
normal roster/player/kit/photo contracts have passed.  It does **not**
authorise changing a country, division, league, draw pool, EQ order or carrier
count.  Those remain preserve-only pending an independently traced writer.
