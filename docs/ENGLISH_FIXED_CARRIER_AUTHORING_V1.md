# English fixed-carrier authoring V1

`scripts/season_english_fixed_carrier_authoring_v1.py` is the season-neutral
input gate for PM99's runner-proven native English mode-0 carriers. It does not
modify the existing 2015/16 release and does not claim that an authoring plan
is a playable database.

The gate accepts either a canonical FootballSquads season capture or its
lossless `pm99-season-source-intake-v1` projection, the native selector map,
and separately hash-bound opening-XI, manager, kit and rating layers. This
separation means changing one rating or kit does not rediscover or reorder
unrelated source data.

The four layer schemas are deliberately small:

- `pm99-season-opening-layer-v1`: `clubs` rows keyed by `club`, with exactly
  eleven `first_xi` names and at least those eleven players in
  `opening_squad`; additional players proven at the club either on that date
  or during the opening window through 31 August fill the carrier up to the
  configured limit. September and later arrivals are excluded.
  `squad_snapshot_policy` is either
  `at-club-on-first-league-fixture-date-exclude-later-arrivals` or
  `opening-window-through-august-31-exclude-september-and-later-arrivals`,
  `fixture_date`, `source_url`, and a sourced or deterministically inferred
  `formation`.
- `pm99-season-manager-layer-v1`: `rows` keyed by `club`, with non-empty
  `manager_name` and `source_url`. There is no native manager fallback.
- `pm99-season-kit-layer-v1`: `clubs` keyed by `club`, with policy
  `historical-target-season` and a `source_url`.
- `pm99-season-rating-layer-v1`: `rows` keyed by `club`; each selected player
  has all ten PM99 visible ratings on the compiler's 0..100 input scale.

The selected squad is the sourced first league XI followed by declared
opening-squad players in the layer's stable order, capped at 11--25 players.
Players present in a full-season source but absent from `opening_squad` are
excluded, preventing January arrivals from leaking into an August database. Missing
nationality, height, weight, birth date or shirt number remains an explicit
secondary-fact gap for the compiler's logged fallback policy. It does not
block authoring. Missing XI identity, manager, kit, or rating does block it.
Portraits default to an explicit no-image decision.

The compiler input requires a fresh binary preflight. Reusable players must be
owned only by selected mode-0 clubs. Additional records may only be appended
from a parser-valid, exclusively mode-0 `dd6361` template. Borrowing a shared
foreign player carrier is forbidden. Managers similarly require one writable
ENT record per selected club, followed by reopen and byte-scope validation.

Example:

```bash
python3 scripts/season_english_fixed_carrier_authoring_v1.py \
  --source .local/builds/2000-01-intake-replay/footballsquads-2000-01.json \
  --selector-map .local/selector_maps/core80_clean_native_eq_map_20260828.json \
  --openings <2000-01-opening-layer.json> \
  --managers <2000-01-manager-layer.json> \
  --kits <2000-01-kit-layer.json> \
  --ratings <2000-01-rating-layer.json> \
  --output-audit <2000-01-english-authoring-audit.json> \
  --output-compiler-input <2000-01-english-compiler-input.json>
```

The compiler-input file is written only when all 92 selected clubs pass the
editorial gates. The picker map exposes only 80 visible cells, but runtime
league-table evidence proves the complete, non-contiguous 20/24/24/24 native
membership (including carrier IDs 3306 and 3311). All 92 carriers are
rewritten; the twelve non-picker records must never be preserved as a smaller
Core80 release. The JSON audit is
always written and contains exact blockers and any genuine over-capacity rows.

## Clean-base allocation and V2 merge

`season_english_mode0_package_adapter_v1.py` is the deterministic consumer for
the resulting `pm99-english-mode0-compiler-input-v1` document. It takes a
strict foreign Season Package V2 plus a clean base tree and produces one
strict merged package. Planning is read-only: it hashes but never changes the
base JUG, EQ or ENT files.

The adapter reuses a `dd6361` player carrier only when every parser-backed EQ
owner is one of the selected mode-0 English teams. When that finite pool is
exhausted, it assigns monotonically increasing new carrier IDs and declares an
explicit `append_from_carrier_id` using the largest eligible template. An ENT
manager carrier must be unlinked or linked exclusively from selected teams.
Foreign package carrier collisions are rejected. The allocation receipt lists
every team, manager and player carrier and binds the plan to all input hashes.

```bash
python3 scripts/season_english_mode0_package_adapter_v1.py \
  --english-input <2000-01-english-compiler-input.json> \
  --foreign-package <2000-01-foreign-package-v2.json> \
  --base-tree <verified-clean-game> \
  --package-id pm99-2000-01-world-v2 \
  --output-package <2000-01-world-package-v2.json> \
  --output-receipt <2000-01-english-carrier-allocation.json>
```

Missing secondary player facts are materialised with logged, deterministic
position/season defaults. A missing portrait becomes `native-no-photo`.
Ratings of 100 on the authoring scale are bounded to PM99 V2's maximum 99.
The proven mode-0 roster writer requires at least 16 players even though the
editorial authoring gate can accept an exact XI; therefore an 11--15-player
club remains an explicit binary-materialisation blocker until more opening
squad members are sourced.
