# PM99 2003/04 all-country intake

Status: **source and fixed-carrier intake complete; not a strict V2 package,
build, runtime-qualified database, or delivered season.**  This directory is
an auditable starting point for a world update.  It deliberately leaves every
unproved identity, carrier mapping, rating, kit, portrait, manager and opening
lineup as a blocker.

## Captured source scope

`sources/footballsquads-2003-04.json` is a canonical capture of every dated
2003/04 catalogue present in the local FootballSquads cache at
`footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).

| Input | SHA-256 | Coverage |
| --- | --- | --- |
| `sources/footballsquads-2003-04.json` | `3a6cd06a652d57f30433914092f941feeeda9340891b19a29bbc4e8277fbee3e` | 335 clubs / 9,654 players in the available Australia, England, France, Germany, Holland, Italy, Portugal, Scotland and Spain catalogues. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Immutable clean-base inventory: 451 foreign carriers / 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `df1706eff19ffa836d6f242ba91db3764366812a333a985944a250c1a8e51ba1` | Empty, registry-locked 2003/04 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `3a3ecc0fb01d774525d0f535e77000592a423bb5e095f51ca083ad2433e91c29` | Deterministic intake audit with explicit release blockers. |

The capture has 17 competition catalogues.  It is **not** proof that this
cache is a complete representation of the PM99 world or of 2003/04 club
membership; it is only the dated source material available locally.

The source leaves at least one fact unresolved for every player row:

| Unresolved field | Rows |
| --- | ---: |
| nationality | 9,654 |
| weight | 750 |
| height | 700 |
| shirt number | 192 |
| birth date | 154 |
| primary position | 41 |

These counts are facts of the input capture, not permission to infer missing
values.  The source also contains no reviewed ratings, manager decisions, kit
art, portrait/no-photo decisions, opening fixtures, formations or tactical
coordinates.

## Fixed-carrier constraint

The carrier registry is derived from the immutable
`pm99-gog-en-1998-clean` database.  It pins the following source files:

| File | SHA-256 |
| --- | --- |
| `DBDAT/ENT98030.FDI` | `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238` |
| `DBDAT/EQ98030.FDI` | `e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c` |
| `DBDAT/JUG98030.FDI` | `95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844` |

No historical club has been assigned to a foreign carrier.  The audit reports
all 451 carriers as `unassigned`, zero complete player slots, no kit or
portrait decisions, and 36 pre-existing shared player carriers.  The
registry is capacity/layout evidence only; it is not historical evidence of a
club, country, division, draw pool or competition membership.

## Candidate-only foreign carrier leads

The following separate artifacts derive **review leads only** from the
unmodified assignment and its name-token candidate queue.  They do not amend
the fixed-carrier ledger, approve an identity, or authorise any PM99 write.

| Input or derived artifact | SHA-256 | Result |
| --- | --- | --- |
| `foreign-carrier-assignment.json` | `16733e2ede472accaf994232641d67730b323ac98b930f1a09bfc0672d48c408` | Unmodified assignment with six reviewed Spain host-country observations and no identity rows. |
| `foreign-carrier-candidate-queue.json` | `02408fc3114dd86cd32276347369873b0ab985a281016a847e7338c9f23be373` | Six single name-token, capacity-compatible candidate leads. |
| `foreign-carrier-candidate-proposal.json` | `9b4b28ad3d2b8d979311067864a276af49d2a286076fb5d319610d5489d82c46` | Deterministically derived candidate proposal. |
| `foreign-carrier-assignment-candidates.json` | `fa5c92dbe2cb29f5f53b40a3819ec2c4d32d03be629ce7494e7f21968a3e2fcf` | Separate candidate ledger; it has no `approved` rows. |
| `foreign-carrier-assignment-candidates-audit.json` | `72763b3b80fd69c4cb0fa9bb640f7c44b37252a97e6440b0abd8d1391639db59` | Six `candidate` rows, 445 unassigned carriers, and result `identity-assignment-incomplete`. |

The candidate records are carrier 1 → Barcelona, 2 → Deportivo La Coruña,
3 → Zaragoza, 4 → Real Madrid, 5 → Athletic Bilbao, and 7 → Valencia.  Each
is a same-host-country source-name lead with sufficient fixed-slot capacity,
not a proven historic identity.  Every row retains blockers for independent
identity approval and a complete club/player/manager/kit/portrait/runtime
transaction.  The source competition catalogue remains provenance only and
is not a PM99 membership or division claim.

## Calendar feasibility evidence

The verified clean `MANAGPRE.EXE`
(`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`)
was copied and safely patched locally for 2003/04.  The local-only receipt
`.local/builds/2003-04-calendar/calendar-receipt.json` records 853 recognised
operands (50 for 1998 and 803 for 1999), target year 2003, rollover year 2004,
and generated executable SHA-256
`10d089bc815d0d758b00529739ef2caaa26428d60865b577f5467b192b2412bc`.
This proves the clock patch profile accepts the base executable; it is not a
database build or release claim.  The executable and receipt stay local.

## Stoke City evidence and screenshot status

The capture contains one Stoke City squad source:
`eng/2003-2004/d1/stoke.txt`, SHA-256
`28e48ad8516bcfdf2fb83cbbb1045c661a218a5f325c1e032a5fffe9758feda5`,
labelled by the source as English Football League Division One.  It contains
26 squad rows.  It does **not** establish an opening match, starting XI,
substitutes, formation, PM99 carrier mapping or tactical coordinates.

Consequently, there is no reliable Stoke City lineup screenshot.  A screenshot
would be meaningful only after a strict, provenance-complete package has two
matching clean builds and runtime qualification tied to their release hash.

## Reproduce this intake

```bash
python3 scripts/capture_footballsquads_season.py \\
  --source-root .local/external-sources/cache.footballsquads \\
  --season 2003-2004 \\
  --country australia --country eng --country france --country ger \\
  --country holland --country italy --country portugal --country scots \\
  --country spain \\
  --output seasons/2003-04/sources/footballsquads-2003-04.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \\
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \\
  --registry-id pm99-base-clean-fixed-carriers \\
  --output seasons/2003-04/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \\
  --registry seasons/2003-04/fixed-carrier-registry.json \\
  --ledger-id pm99-2003-04-fixed-carrier-intake --start-year 2003 \\
  --output seasons/2003-04/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \\
  --registry seasons/2003-04/fixed-carrier-registry.json \\
  --ledger seasons/2003-04/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \\
  --registry seasons/2003-04/fixed-carrier-registry.json \\
  --ledger seasons/2003-04/fixed-carrier-ledger.json \\
  --output seasons/2003-04/fixed-carrier-intake-audit.json

python3 scripts/foreign_carrier_candidate_proposal_v1.py \\
  --registry seasons/2003-04/fixed-carrier-registry.json \\
  --source-capture seasons/2003-04/sources/footballsquads-2003-04.json \\
  --assignment seasons/2003-04/foreign-carrier-assignment.json \\
  --queue seasons/2003-04/foreign-carrier-candidate-queue.json \\
  --output seasons/2003-04/foreign-carrier-candidate-proposal.json

python3 scripts/foreign_carrier_candidate_proposal_v1.py \\
  --registry seasons/2003-04/fixed-carrier-registry.json \\
  --source-capture seasons/2003-04/sources/footballsquads-2003-04.json \\
  --assignment seasons/2003-04/foreign-carrier-assignment.json \\
  --queue seasons/2003-04/foreign-carrier-candidate-queue.json \\
  --proposal seasons/2003-04/foreign-carrier-candidate-proposal.json

python3 scripts/foreign_carrier_assignment_v1.py \\
  --registry seasons/2003-04/fixed-carrier-registry.json \\
  --source-capture seasons/2003-04/sources/footballsquads-2003-04.json \\
  --assignment seasons/2003-04/foreign-carrier-assignment.json \\
  --proposal seasons/2003-04/foreign-carrier-candidate-proposal.json \\
  --output seasons/2003-04/foreign-carrier-assignment-candidates.json

python3 scripts/foreign_carrier_assignment_v1.py \\
  --registry seasons/2003-04/fixed-carrier-registry.json \\
  --source-capture seasons/2003-04/sources/footballsquads-2003-04.json \\
  --assignment seasons/2003-04/foreign-carrier-assignment-candidates.json \\
  --output seasons/2003-04/foreign-carrier-assignment-candidates-audit.json
```

## Required work before delivery

1. Establish declared world scope and capture dated, identity-safe source
   evidence for every club, player, manager, kit, portrait/no-photo decision
   and opening lineup.
2. Reconcile stable real-world identities and every unresolved player fact;
   make reviewed, source-backed carrier assignments that preserve PM99
   topology and resolve all shared-carrier conflicts consistently.
3. Add reviewed ratings, kits, portraits/no-photo states, managers and opening
   data, then create a complete strict `pm99-season-package-v2` package.
4. Produce two clean byte-identical builds from the verified base, validate
   their hashes and contents, and attach runtime proof for the exact release
   inventory, including a Stoke City lineup screenshot where Stoke is in the
   playable scope.

Until each gate passes, this is an intake milestone only and must not be
presented as a delivered 2003/04 database.
