# 2022/23 all-country world intake

**Status: blocked intake; not a PM99 database release.**

This directory records the first reproducible 2022/23 source and carrier
intake.  It must not be described as a completed `pm99-season-package-v2`, a
playable build, or a historically complete world update.  No player, club,
manager, rating, kit, portrait, **approved historical carrier assignment**, or
opening-lineup fact has been inferred from another season or from the baseline
database.

## Captured source scope

`sources/footballsquads-2022-23.json` is a canonical capture of every
`2022-2023` FootballSquads cache file present on 2026-08-31.  It pins the
CC0-1.0 `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` and every individual source-file
hash.

| Fact | Value |
| --- | ---: |
| Capture SHA-256 | `b37f25b540fbc946596eddb691808eb09a1b96fc05dd317e2fe5fb013ef2365b` |
| Country catalogs | 22 |
| Competition catalogs | 33 |
| Club-squad records | 565 |
| Player rows | 17,580 |
| Rows with one or more unresolved facts | 2,285 |

The included country catalogs are Australia, Austria, Belgium, Croatia,
Czech Republic, Denmark, England, France, Germany, Greece, Hungary, Italy,
Mexico, Netherlands, Poland, Portugal, Russia, Scotland, Spain, Switzerland,
Turkey, and Ukraine.  This is the complete dated coverage in the local cache;
it is **not** proof of coverage for every country represented by PM99.

The source gaps are explicit in each row and total: 2,168 height values,
2,260 weight values, 279 dates of birth, 24 shirt numbers, two nationalities,
and two primary positions.  The capture also contains source-specific
competition phases (including Mexico Apertura and Clausura), which require
identity-safe reconciliation before any one historical squad is assigned to a
carrier.

Stoke City is present as 35 captured rows in
`eng/2022-2023/flcham/stoke.txt` (source SHA-256
`fbea8dfd0d44e74d8f99dfeef9071c8fc7bccf6e26d8e096d70f4baef16c25fe`).
This is a squad-list source, not opening-lineup evidence.

## Fixed-carrier intake

The registry was generated directly from the verified clean base
`pm99-gog-en-1998-clean`, whose inventory fingerprint is
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

| File | SHA-256 | Result |
| --- | --- | --- |
| `fixed-carrier-registry.json` | `c057fa90f34d04a08cdbcce6351870c8cb729155b40b9d40b98121743c3db370` | 451 immutable foreign carriers / 9,390 roster slots |
| `fixed-carrier-ledger.json` | `f2cf8232a21e7aa32c94601e60f97d1b698267be8ba789edea3dcc02ea8c83c6` | Empty, schema-valid 2022 ledger |
| `fixed-carrier-intake-audit.json` | `45ed18c3ec42a00d8c9fbecc9e4520bf371f213ed145cce7e678dd7605ec6dac` | Release-blocking audit |

The audit reports all 451 carriers as unassigned, zero complete player slots,
and 36 shared baseline player carriers that need one consistent proven identity
or an explicit unresolved decision.  The registry is a binary capacity/layout
record only.  It is not evidence of a historical club, country, division, draw
pool, or competition mapping.

## Candidate-only foreign-identity milestone

The candidate-only coordinator derives a separate overlay from six reviewed
Spanish host-country rows and the source capture.  It changes neither the
empty immutable base assignment nor the fixed-carrier ledger, writes no PM99
content or binaries, and grants no identity approval.  A candidate is only an
editorial lead whose normalised club-name tokens and roster capacity meet the
guarded selection rule.

| File | SHA-256 | Result |
| --- | --- | --- |
| `foreign-carrier-assignment.json` | `fbf1c923be60165d5dcbbcec3160b0912406b352dd477dcdf4d8e9f892d1795a` | Unchanged base: zero assignments |
| `foreign-carrier-candidate-queue.json` | `41bc919fd26fc91fde8d2c4109693cc72ff33b6674ad0772a0b53ac14b5112f1` | Unchanged reviewed queue: five single leads and one no-lead row |
| `foreign-carrier-candidate-proposal.json` | `00a6ecc94dffcaa943a0d2b2db618270e9134e71c37a4144fefb0c14897fbad4` | Five deterministic candidate-only proposals |
| `foreign-carrier-assignment-candidates.json` | `69fb85f367b807d13aefecf10f1fc7301dfa6ba148b97ec3d7d03890bb415d37` | Separate, candidate-status overlay |
| `foreign-carrier-assignment-candidates-audit.json` | `2576c73aa8f06b4b53129675da0da2b137a6d12d4db6d75bc2d794c18706c342` | `identity-assignment-incomplete`; 5 candidate / 446 unassigned |

The only derived leads are carrier 1 → Barcelona, carrier 3 → Zaragoza,
carrier 4 → Real Madrid, carrier 5 → Athletic Bilbao, and carrier 7 →
Valencia.  Each has a single same-country FootballSquads source selector and
enough source rows for the immutable carrier capacity.  They remain blocked on
editorial identity approval and complete club, manager, player, kit,
portrait/no-photo, opening-evidence, build, and runtime transactions.

**Carrier 2 remains unassigned.**  Its reviewed host is Spain and its baseline
display name is `R.C. Deportivo`, but its queue row has no source-name-token
candidate.  No substitute source club was selected.  Shared-carrier work is
outside this milestone and remains untouched.

## Calendar capability proof

The local-only calendar proof was produced from the verified baseline
`MANAGPRE.EXE` (`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`).
It produced `.local/season-builds/2022-23/calendar/MANAGPRE.EXE` with SHA-256
`dddbc8d1188f5e55bbbdff41ece611e8f795fae7e7a2baa7a269fa45a9437d57`;
the receipt records 853 patches targeting 2022 with a 2023 rollover.  This
only proves the calendar transform.  It is neither a compiled season nor
runtime qualification.

## Validation and reproduction

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2022-2023 \
  --output seasons/2022-23/sources/footballsquads-2022-23.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-2022-23-fixed-carriers \
  --output seasons/2022-23/fixed-carrier-registry.json
python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2022-23/fixed-carrier-registry.json \
  --ledger-id pm99-2022-23-fixed-carrier-intake \
  --start-year 2022 \
  --output seasons/2022-23/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2022-23/fixed-carrier-registry.json \
  --ledger seasons/2022-23/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2022-23/fixed-carrier-registry.json \
  --ledger seasons/2022-23/fixed-carrier-ledger.json \
  --output seasons/2022-23/fixed-carrier-intake-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2022-23
python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2022-23/fixed-carrier-registry.json \
  --source-capture seasons/2022-23/sources/footballsquads-2022-23.json \
  --assignment seasons/2022-23/foreign-carrier-assignment.json \
  --queue seasons/2022-23/foreign-carrier-candidate-queue.json \
  --proposal seasons/2022-23/foreign-carrier-candidate-proposal.json
```

Ledger validation passes.  The audit correctly fails the world release gate;
its blockers are `world-content-incomplete` and
`baseline-shared-player-carriers`.  The candidate proposal validation also
passes; its separately derived audit correctly remains incomplete.

## Required work before delivery

1. Establish complete dated source coverage for the declared PM99 world scope,
   then reconcile club, manager, and player identities without merging
   different competition phases by assumption.
2. Complete every fixed-carrier assignment and player slot with provenance;
   resolve all shared baseline carriers consistently.
3. Record sourced ratings, kits, portraits or native-no-photo states, and
   opening-lineup/formation evidence.
4. Produce and strictly validate a complete season package; make two clean,
   byte-identical builds and run the finished inventory.
5. Only after those gates pass, capture a real Stoke City runtime lineup
   screenshot and record its safe local path and SHA-256.  No screenshot is
   present for this blocked intake.
