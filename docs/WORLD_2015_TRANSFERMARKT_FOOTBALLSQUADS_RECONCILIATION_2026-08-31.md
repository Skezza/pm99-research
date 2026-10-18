# 2015/16 Transfermarkt–FootballSquads identity reconciliation

This lane closes the 125 Transfermarkt club names that did not have a strict
FootballSquads name match. It uses a country-scoped, explicit override table
for legal names, transliterations and known historical names. It does not use
similarity scores, infer a carrier, or write PM99 data.

## Reproduce

```bash
python3 scripts/reconcile_2015_transfermarkt_footballsquads_identities.py \
  --footballsquads-capture .local/season-sources/footballsquads-2015-world-hybrid.json \
  --opening-fixture-receipt .local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json \
  --source-draft .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json \
  --output .local/season-pipeline-v2/world-2015-transfermarkt-footballsquads-identity-reconciliation-20260831.json
```

The receipt SHA-256 binds the exact FootballSquads capture, Transfermarkt
fixture receipt, source-carrier draft and override table. Every resolved row
retains the FootballSquads selector (`country_catalog`, competition, source
path and source hash), the Transfermarkt club/game identity and any existing
source-draft carrier reference.

## Result

| Scope | Count |
| --- | ---: |
| Transfermarkt receipt clubs | 218 |
| Existing strict country/name matches | 93 |
| Explicit override matches | 125 |
| Resolved source identities | 218 |
| Unresolved source identities | 0 |
| Source-draft carrier references | 175 |
| Existing carrier source gaps examined | 149 |
| Gap identities closed by exact source evidence | 5 |
| Carrier gaps still unresolved | 144 |

The five identity-closed carrier gaps are 250 Empoli, 421 Hertha Berlín, 871
Lokeren, 1111 Zurich and 1112 Young Boys. Their exact dated FootballSquads
squads are already selected by carriers 221, 410, 856, 1108 and 1110
respectively. They therefore remain carrier-level selector conflicts: the
receipt closes the identity/source question but does not reuse a selector or
claim a carrier closure.

The exact unresolved carrier IDs are retained in the receipt's
`source_gap_reconciliation` rows with status `unresolved`; no country-family
substitution is performed. The 144 comprise the 135 no-captured-country rows
plus the nine capacity/no-exact-source rows left after the five exact
selector-conflict candidates.

## Evidence policy

* The 125 overrides are explicit source-code data, keyed by
  `(country_catalog, Transfermarkt name)`. The run fails if an override is
  stale, missing from the current unmatched set, or points to a missing
  FootballSquads identity.
* A direct strict identity match is accepted only when country and strict
  club key are unique. Duplicate FootballSquads identities remain ineligible.
* A selected source-draft carrier ID is informational only. It does not
  authorize assignment, roster-slot mapping, membership changes or PM99
  writes.
* Transfermarkt opening fixtures remain dated manager/XI/formation/stadium
  facts. FootballSquads remains the full-squad source. Kits, portraits,
  ratings and opening-slot order require separate evidence.

Tests are in
`scripts/test_reconcile_2015_transfermarkt_footballsquads_identities.py`.
