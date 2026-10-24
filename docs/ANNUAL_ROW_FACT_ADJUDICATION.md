# Annual squad rows and independent player facts

The optional annual-row identity policies admit narrowly scoped birthday and
nationality corrections through the existing source-backed player-change
writer. They do not move players, choose clubs, recalibrate ratings or replace
whole season packages.

`annual-source-row-person-identity-v1` requires the retained annual source row,
recipe actor and native birthday to agree. Official named profile sources then
supply the corrected facts. This existing policy remains strict.

`annual-source-row-with-opening-fixture-provider-id-v1` additionally permits an
explicitly recorded wrong annual birthday preimage. It requires the same
hash-bound annual row in preallocation and intake, exact actor/source identity,
unique native club ownership and matching native preimage. A retained first
league match sheet must show the full-name profile link and numeric provider
player ID inside the requested club's starting XI. Club aliases, competition,
season, exact date and the sole first-matchday token are checked. Matchdays 11
and 21 do not satisfy matchday 1.

The annual row supplies no numeric provider ID: the match-sheet link supplies
it. This is not evidence that a separate provider profile page was captured.
Independent named official fact sources still have to agree; the fixture does
not certify the corrected birthday or nationality itself. No missing fact may
be invented to satisfy these guards.

Both policies use the existing adjudicator, exact native byte masks, recipe
binder and SOURCE reconstruction. The binder removes fallback declarations
only for facts actually supplied. Unselected actors and unrelated database
bytes must remain unchanged. Source inputs and native preimages are immutable;
a correction against a later parent must be rebound and verified.

Relevant implementation: `scripts/season_annual_row_identity_guard_v1.py`,
`scripts/season_annual_fixture_identity_bridge_v1.py`,
`scripts/season_adjudicated_player_facts_v1.py` and the shared
`scripts/season_source_verified_player_changes_v1.py` dispatch.

Focused checks, from the workspace root:

```sh
PYTHONPATH=.:upstream/pm99-skezmod-db-editor .local/venvs/season-pipeline/bin/python -m pytest -q scripts/test_season_annual_fixture_bridge_v1.py scripts/test_season_annual_row_identity_guard_v1.py
```

Portable parser tests use synthetic HTML; retained-corpus tests explicitly skip
only when their local source inputs are absent. Existing but invalid evidence
must fail validation. Missing evidence is not verified correctness.
