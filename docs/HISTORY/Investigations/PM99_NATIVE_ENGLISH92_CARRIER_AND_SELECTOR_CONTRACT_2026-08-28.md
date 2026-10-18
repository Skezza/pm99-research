# PM99 Native English 92-carrier and selector contract (2026-08-28)

## Corrected result

PM99 has an existing native English **92-club** carrier set.  It is the
original 20 + 24 + 24 + 24 four-division shape.  A 2015/16 replacement can
therefore reuse those carriers without adding clubs, changing the executable,
or changing promotion/relegation rules.

The new-game picker is a different, narrower surface: it shows four panels
of twenty shirt icons (80 user-selectable cells).  Those cells are not a
complete model of the competition.  The other twelve English carriers still
participate in the game and affect which clubs appear in the picker.

The earlier ``Core80`` conclusion was wrong because it treated the visible
picker cells as the complete competition.  Leaving twelve carriers untouched
allowed old 1998 club identities such as Bradford City to reappear in the
2015 picker.  It must not be used as a release shape.

## Runtime evidence

Two runner controls establish this boundary.

1. ``english80_2015_core_build4_selector_runtime_nativeclick_20260828``
   wrote 80 selected carriers but preserved twelve others.  Old lower-league
   clubs leaked into the selector.  This is a release-blocking counterexample,
   not an OCR issue.
2. ``english92_2015_build24_all_panels_nativeclick_20260828`` ran the
   existing full 92-carrier database through all four picker panels.  Every
   displayed club was drawn from the rewritten 92-carrier dataset.  No
   executable or competition-count patch was used.

That second control established capacity only. It is now superseded for
membership by four fresh games of the native 2015 candidate: the Premier
League, Championship, League One and League Two table screens each show the
complete intended 20/24/24/24 club set. See
`PM99_ENGLISH_LEAGUE_CARRIER_MEMBERSHIP_CONTRACT_2026-08-28.md` for the four
screen captures and their build hashes.

## Variable-length team string control

The compiler's indexed EQ string rewriter changed record 322 from ``Bolton
W.`` to ``Bolton Wanderers Test`` and also grew the full club name.  The
single-change database reopened through the parser and the real game selected
the new label in the original First Division picker position.  Evidence:

``variable_team_string_control_bolton_fullgame_20260828``.

Variable-length team strings are therefore a real runtime lane.  The public
editor command still rejects them because its generic container writer only
permits equal-size edits.  That is a product implementation gap, not a
reason to fall back to fixed-length historical names.

## Release consequences

The 2015/16 release must:

1. rewrite all 92 existing English carriers;
2. keep every 2015/16 club on the carrier whose runtime competition membership
   is proven to produce the intended division;
3. write club strings through the variable-length indexed EQ writer;
4. rewrite each carrier's roster, manager, kit, finances, initial XI/tactics
   and portraits; and
5. run a new-game proof of all four divisions, not just static file checks.

The carrier-membership milestone is now closed: the exact native 92-ID
registry, source-ledger guardrail and four runtime tables prove it. The
remaining picker wrinkle is separate: a full rewritten database must capture
its own 20 selectable clubs per panel. The editor and historical compiler must
publish that post-build audit instead of predicting human-manager availability
from the 1998 picker IDs.
