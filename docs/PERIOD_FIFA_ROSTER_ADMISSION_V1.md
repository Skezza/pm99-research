# Period FIFA identities with dated opening rosters

The opening-identity exchange accepts an explicit
`exact-target-fifa-and-dated-premier-league-roster-v1` admission policy.
It reuses the normal compiler, identity exchange, publication and SOURCE replay;
it does not create another database writer.

The two sources answer different questions:

- An exact target-edition FIFA row supplies the full identity, date of birth,
  period nationality, positions, physical facts and ten mapped abilities.
- An original official Premier League August squad-number PDF establishes
  membership of the named destination club. It does not prove a starting XI,
  matchday bench, appearance or transfer date.

Both retained files are hash-bound and reparsed. The supported FIFA editions are
15 through 23. The selector must identify one full-name/date-of-birth/player-ID
combination; contradictory updates and ambiguous published aliases are refused.
Published whole given names and surnames may omit middle names. The complete
FIFA identity remains in `source_name`, and IDs use `person-fifa-` rather than
pretending to be Transfermarkt identities. Outfield handling is capped at 20.
The roster's source shirt number is retained as evidence; this identity-only
write path preserves the native slot's shirt controls and does not claim to
have applied that number.

This route supports the two 2017/18 Stoke admissions, Harry Souttar and Thibaud
Verlinden. It is not a claim that FIFA supplies historical ownership, that every
season has these sources, or that the same source route works for 1990.

Known-person moves can separately use a literal published FIFA short name while
retaining the full source identity. They preserve existing ability vectors.
An explicitly selected official named biography can correct a contradictory
birthday without claiming that the biography establishes opening membership.
The original contradictory FIFA row is preserved.

For selected foreign mode-1 clubs, the separate opt-in
`foreign-mode1-profile-identities-with-opaque-opening-controls-preserved-v1`
permits identity corrections only when the recipe already declares preserved
mode-1 membership and opening controls. It requires an exact non-English club
set and native mode 1, rejects authored order/complete-opening changes, and
checks byte-identical EQ and unchanged selected-player startup controls.
Those controls do not establish a historically correct foreign AI XI. Existing
English starter guards remain in force.

Validation covers original-source binding, negative identity/publisher/date
cases, existing exchange behavior, native unchanged-data checks, SOURCE A/B
comparison and targeted original runner frames before installation. The
implementation and tests are `scripts/season_fifa_dated_roster_admission_v1.py`
and `scripts/test_season_fifa_dated_roster_admission_v1.py`.
