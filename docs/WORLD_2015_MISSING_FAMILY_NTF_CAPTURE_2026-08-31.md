# 2015 missing-family dated squad capture (2026-08-31)

`scripts/capture_2015_missing_family_squads.py` acquires historical club
appearance tables from National Football Teams (NTF) for the missing-country
families in the 2015 world source draft.  It is a read-only source step: it
does not assign carriers, write PM99 data, alter an executable, or redistribute
the downloaded HTML.

The source catalogue is country constrained.  A club is selected only when an
explicit reviewed alias exactly matches a club link on that country's dated
league index.  Calendar-year leagues use NTF's `2015` index/page; European
split-year leagues use `2015_1` and the player table must say `2015/16`.
Every index and club page is cached locally with a SHA-256 digest and the
canonical capture retains the source URL and digest.  No club URL can be
used by two carrier candidates.

## Reproduction

```text
python3 scripts/capture_2015_missing_family_squads.py \
  --draft .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json \
  --cache-root .local/external-sources/cache.national-football-teams-2015 \
  --output .local/season-pipeline-v2/world-2015-missing-family-ntf-capture-20260831.json
```

The local receipt produced on 2026-08-31 contains 81 country-scoped club
captures across 27 families, 924 appearance-table player rows, and 81 of the
117 non-special missing-family carrier candidates in this catalogue.  The
remaining 36 candidates are retained under `unresolved_carriers` with exact
reasons.  The wider source draft still has 144 unresolved carrier gaps: this
capture deliberately scopes out already-covered countries, the five
identity-closed selector conflicts, special/free/youth pools, and families
without an explicit public catalogue entry.

The unresolved reasons are meaningful rather than silent drops:

* `club-page-has-no-dated-2015-16-player-rows` means the exact dated NTF page
  exists but has no appearance rows for the requested season;
* `no-exact-2015-country-index-club` means the country index had no exact
  reviewed club link;
* `no-reviewed-country-club-alias` means no alias was approved, so the script
  intentionally did not guess a historical identity.

NTF's table is an appearance-based historical player list and is not promised
to be a complete registration list.  Shirt number, height, and weight are
therefore explicitly unresolved in each captured row.  These captures are
inputs for later review and are not automatically source-ready for a fixed
PM99 roster capacity.
