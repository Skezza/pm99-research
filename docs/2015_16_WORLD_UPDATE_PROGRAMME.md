# 2015/16 PM99 world update programme

## Objective

Produce one historically grounded 2015/16 PM99 database using the game's
**existing** world-club capacity. It will not add clubs or alter the executable.

For **every real international club carrier** PM99 already contains, across
every country and league the game represents, the completed release must set
the 2015/16 club identity, stadium, manager link/name, squad, player facts and
attributes, opening lineup, opening tactics, kit and portrait/no-photo
decision. A club which disappeared or is no longer appropriate to that fixed
league slot is repurposed as the historically correct 2015/16 club for that
slot.

## What is known at the start

- PM99 has 543 modern club records: 92 English mode-0 carriers and 451
  other-club mode-1 carriers. Mode is a record-layout marker, not a country
  marker.
- The authoritative indexed EQ→JUG parser exposes all 543 modern carriers and
  their linked roster rows. The older general team view exposed 532 entries;
  it must not be used as a carrier-count or league-membership authority. The
  current league audit still records 319 low-confidence assignments and 9
  review assignments, mostly caused by old sequential assumptions. That is
  evidence to replace, not a basis for a bulk historical rewrite.
- A fixed-carrier assignment now has its own reviewed input contract:
  `scripts/foreign_carrier_assignment_v1.py` links one immutable carrier,
  one fresh-route preseason-picker host-country proof and one dated historical
  club source. It deliberately accepts no country/league inference from EQ
  record ranges. The old all-shirt Spain sweep is diagnostic only because the
  rival picker holds four mutable friendly slots; every carrier needs a fresh
  single-tile route before it is assigned.
- International player records use multiple shapes. The current
  indexed-directory audit decodes and syntactically parses all 11,479 records.
  The native `dd6360` cursor now has foreign runtime proof for nationality,
  date, height, weight, broad position and all ten stored profile-skill bytes,
  and a constrained no-growth variable-name rebuild; it covers 9,211 of the
  9,212 mode-1 roster rows. The complete six-candidate fine-role window is
  runtime-proven. The single linked `dd6361` row has a separate
  byte-preserving core writer. This does not make unknown controls, shirt
  numbers or opening-state fields safe to write.
- Foreign club variable strings have runtime proof. Existing final manager
  links are runtime-proven for mode 0 and mode 1: Barcelona's ENT 1069
  surname control and 1069→1641 relink show `Test Mgr` and `Hiddink` in the
  live game. Variable-length manager names and full-profile prose still have
  no write contract. Competition membership and complete opening-state
  transactions do not yet have world-wide runtime proof.  Compact foreign kit
  art is now proven through the three existing carrier-keyed UI archives;
  large/3D surfaces remain out of scope.

## Delivery gates

1. **World carrier registry**
   Create a registry of each carrier's proven game-facing country-picker,
   club slot, record mode, player-family mix, manager link, image availability
   and exact runtime evidence. Bind historical clubs with the assignment ledger
   only after a fresh single-tile picker route. Special records such as
   All-Stars, selections and free players are explicitly separated from club
   carriers. Do not label an invisible foreign domestic division as fact.

2. **Foreign topology preservation**
   This release deliberately makes no country, foreign membership, division,
   promotion/relegation, draw-pool or competition write. It keeps every
   existing carrier in its current PM99 topology and replaces only the club
   content assigned to that carrier. The named-opponent route is retained as a
   read-back check that an edited carrier is still consumed by the game, not as
   a reason to reverse engineer or alter a foreign league table.

3. **Mode-1 fixed-carrier compiler lane**
   This first safe bulk lane is now implemented in
   `scripts/season_package_compiler_v2.py`.  It can re-identify an existing
   mode-1 club, ground, seated capacity and linked manager, then re-identify
   each *existing* dd6360 player carrier with a bounded variable name,
   nationality, broad position, date, physicals, all ten stored profile skills
   and its six fine-role candidates. It proves that the roster's
   exact player IDs, row order and flags remain as in the base before it
   writes.  The one `dd6361` row has a separate byte-preserving core route.
   No membership, country, division, finance, opening state, shirt number,
   row count or row order is written. This gives the season programme a
   reusable safe content carrier while the remaining game semantics are
   researched.

   The next runtime pilot must take representative fixed-carrier changes from
   several player families through club, player, transfer/search, league and
   compact-kit/portrait views.  The compiler contract is not a substitute for
   those visual proofs.
   Verify club, player, transfer/search and league views.

4. **Sourced 2015/16 manifests**
   The authoritative per-season authoring form is the
   [World fixed-carrier content ledger V2](WORLD_FIXED_CARRIER_LEDGER_V2.md):
   one immutable base registry and one source ledger for the opening date.
   Every player and manager row records the source and confidence. Unknown
   fringe players are retained only with a clear fallback policy; every club
   needs an approved era-correct kit source, and portrait outcome is always a
   verified photo or PM99's native no-photo state. The
   older fixed-carrier V1 document is only the final package/EQ audit guard;
   it is not a competing authoring manifest.

5. **World compiler and asset pipeline**
   Apply complete carrier transactions, never isolated name or roster changes.
   The initial transaction is intentionally a fixed-slot one, not a silent
   movement/reorder writer. Preserve opaque player records and unknown
   competition bytes. Generate kit and minifoto receipts independently so bad
   art cannot be confused with bad database structure. A missing credible
   portrait is an explicit native no-photo disposition, with player/carrier
   and reason recorded; it never blocks the database build.

6. **Runtime release proof**
   Start fresh games and inspect all four English league tables, the seeded
   continental-championship surface and a resolved foreign-opponent route,
   plus sampled clubs and players from every represented country. The release
   requires zero duplicate player links, correct English table cardinality,
   valid manager links, asset integrity and no startup/modal regression. The
   final corpus audit also requires a portrait/no-photo disposition for every
   compiled player. Foreign opening XI/tactics are a separate release gate:
   the game reads the static grid, but source-player-to-grid ordering must be
   proved before a generated formation is allowed to replace the base grid.

## Definition of done

The 2015/16 world update is complete only when every existing real club carrier
PM99 actually uses has a 2015/16 identity and the runtime proof above. It does
**not** mean adding clubs beyond PM99's capacity, inventing leagues that PM99
does not represent, or changing unproven continental competition logic.
