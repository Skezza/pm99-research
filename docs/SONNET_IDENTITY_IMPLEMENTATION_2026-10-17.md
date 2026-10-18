# Provider-scoped player identity: implementation note (2026-10-17)

Scope: the "immediate identity fixes" from
`ADVERSARIAL_REVIEW_LEAD_ASSESSMENT_2026-10-17.md`. Source-tooling code and
fixture tests only. No release, recipe, game asset or registration changed, and
no existing release was re-audited or rebuilt.

## Representation and compatibility

Optional player key `source_identity` = `{"provider": "transfermarkt",
"player_id": "<digits>"}`. The ID is a string taken literally from a
`/profil/spieler/<id>` link (canonical positive integer, no leading zero, at
most 18 digits) and is meaningful only inside its provider. Providers are an
explicit table (`scripts/season_player_identity_v1.py` `PROVIDER_ID_PATTERNS`,
the schema's `$defs/source-identity`, and
`season_package_v2.SOURCE_IDENTITY_PATTERNS`; a test keeps them in step).

* Absent key = unknown. Never `null`, never inferred from a name; a link with a
  non-canonical id also stays unknown. Legacy captures, intakes, drafts,
  packages and recipes stay valid and unchanged (the key is only added when
  present; summary/coverage counters for it appear only when greater than 0).
* Present-but-malformed (extra keys, other provider, bad id, non-string) is
  rejected by every consumer: `canonical_player`, `compose`, intake
  `_validate_player`, the schema and the bespoke `validate_package` check
  (which runs even without the `jsonschema` package).

## Handoff chain

`SquadParser`/`parse_squad` and `parse_squad_with_dom_fallback` ->
`canonical_player` -> `build_capture` ->
`compose_season_source_captures_v1.compose` ->
`pm99_simple_season_v1._normalise_capture` ->
`season_source_intake_from_allocation_v1.adapt` (unchanged passthrough, tested)
-> `season_source_intake_v1.build_intake` (`_validate_player`; the row hash
covers the identity) -> `season_source_package_builder_v1.build_draft`
(`_person_candidate`, recipe player `source_identity`, stale identity removed)
-> `season_package_v2.validate_package` / schema ->
`pm99_season_qa_v1.audit_season`.

Behavioural notes:

* Parsers: rows with an ID collapse only by (provider, ID). Identical repeated
  markup collapses; a repeat with different facts, or two IDs in one row, is an
  error (the squad page becomes an explicit capture gap), never a silent pick.
  Rows without an ID keep the previous name-keyed collapse and are never merged
  with an identified row.
* `compose` fails on malformed identities and on one ID described with a
  different name or birth date. The same ID in several clubs is kept.
* Intake rejects the same ID twice in one club.
* Builder: an identified row's duplicate key is the provider ID, so namesakes
  with different IDs are no longer treated as one person, and the same ID in
  two clubs goes through the existing earliest-opening-fixture rule or is
  excluded as an unresolved conflict. Rows without an ID keep name+birth-date.
  The conflict report shows the ID key as `normalised_name="source-identity"`,
  `birth_date="<provider>:<id>"` (same convention as the existing
  `opening-source-player-id` key).
* Pre-existing break found and fixed on the way: `build_capture` clubs carry
  `source_competition_code`, which `foreign_carrier_assignment_v1` and
  `season_source_intake_v1` reject (exact club field sets). `_normalise_capture`
  now removes it from the canonical club and keeps it in the normalisation
  receipt (`club_source_competition_codes`).

## Audit and QA policy

`season_player_identity_v1.audit_entries` is candidate screening only
(`duplicate_free_verified` is always `false`; `screening` is
`complete-provider-identity` only when every row has a valid ID). It reports
same-provider-ID candidates (strong, independent of birth date; with club and
number differences and conflicting name/birth-date fields), name+birth-date
candidates (kept for unknown or cross-provider IDs), distinct-ID namesakes (not
merged), malformed identities, and rows with neither ID nor birth date. Stable
keys: `provider-id:<provider>:<id>` and `name-birth-date:<hash>`. Nothing is
dropped or resolved; a loan or transfer is indistinguishable from a duplicate
here.

`pm99-season qa` (`audit_season`) now stores `checks.player_identity` (exact
`counts`; lists capped at 100) and emits:

| Finding | Level |
| --- | --- |
| malformed identity | blocker `player-identity-metadata-malformed` |
| one provider ID on several recipe players | blocker `player-provider-id-repeated` |
| one provider ID with conflicting name/birth date | blocker `player-provider-id-metadata-conflict` |
| players without a provider ID | warning `player-provider-identity-missing` |
| neither ID nor birth date | warning `player-duplicate-screening-insufficient-facts` |
| name+birth-date candidates | warning `player-name-birth-date-candidates` |
| distinct-ID same name+birth date | warning `player-distinct-provider-id-namesakes` |

Existing releases carry no IDs, so they gain only warnings. The existing
strict package guard for name+birth-date duplicates is unchanged and still
applies to players with distinct IDs. `validate_package(strict=True)` also
rejects a repeated provider ID (non-strict drafts keep it as audit data, as
with name+birth date). A blocker means "inconsistent recipe", not a historical
verdict.

## Known limitations

* Lead review closed the profiled-opening-addition gap after this note's
  original Sonnet version: the materialiser now retains an identity only when
  its literal Transfermarkt profile URL agrees with the declared source ID.
  External/unknown-provider URLs remain unknown; disagreements fail closed.
  Existing reconciled intake rows already retain their original facts. The
  builder now uses the same provider key for identified annual and opening
  rows. Legacy unqualified opening IDs retain their old behavior.
* A mixed ID / no-ID same-name+birth-date pair is not caught by the builder's
  per-row key; the package-level guard and the QA warning cover it when a birth
  date exists.
* `supplement_2015_ntf_with_transfermarkt.supplement` still joins to NTF rows by
  name (legacy); added Transfermarkt rows now also carry their ID.
* Only Transfermarkt is a registered provider. No historical verification, no
  existing release data and no live Transfermarkt page was exercised by Sonnet.
  The lead subsequently replayed 154 cached 1990 squad pages twice: 3718 player
  rows retained IDs, zero parser errors or missing IDs, identical outputs.
  This is parser coverage, not full recipe or playable-game validation.

## Independent lead review

The lead compared all scripts/schemas to the pre-worker archive rather than
relying on Git (many files are untracked). It additionally hardened numeric ID
path boundaries and provider hosts, distinguished explicit null metadata from
absent identity, and added 17 negative/compatibility tests in
`scripts/test_season_identity_adversarial_review_v1.py`. The focused suite,
including the opening materialiser, passed 139 tests. The original Sonnet
result remains unchanged in the JSONL transcript. Preferred and retained release
catalogue hashes match the pre-worker values; no actual games were edited.
