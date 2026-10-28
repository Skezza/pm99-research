# Annual squads and opening-lineup additions

Some captured season pools contain an annual squad plus players independently
recovered from the club's first league lineup. The combined pool must not be
described or checked as though every row appeared on the annual page.

The full-cohort identity witness now verifies those components separately:

- Annual rows must reproduce the original annual capture exactly.
- Each explicitly marked opening addition needs a unique numeric player ID in
  the original target-club first XI, an original hash-bound profile, and matching
  published name and date of birth.
- The original domestic opening fixture must contain eleven starters and belong
  to the target year. Its date must match the captured cohort date.
- The existing checks for native player identity, exclusive active ownership,
  complete roster correspondence, ambiguous cohorts and unchanged inputs remain.

Profile additions prove identity and opening membership. They do not certify all
secondary physical facts, ratings or a historical formation. The saved witness
records the annual proof and each original profile proof separately. Existing
annual-only witnesses retain their original verification output.

The source verifier does not approve a build or a release. A club correction
still needs separately sourced manager evidence, exact native write scope,
SOURCE reconstruction, and relevant runtime evidence before installation.
Where the default label planner refuses a coach-name collision, retain that
refusal. A paired correction must explicitly verify the counterpart's own club,
fixture and exclusive native manager ownership; an opponent's coach is not
evidence for an unrelated club.

Implementation: `scripts/season_historical_club_label_full_cohort_optin_v2.py`.
Focused regression and tamper cases:
`scripts/test_full_cohort_mixed_opening_sources_v1.py`.
