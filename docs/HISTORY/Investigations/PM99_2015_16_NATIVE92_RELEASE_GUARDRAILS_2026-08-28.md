# PM99 2015/16 native-92 release guardrails

## Scope

This is a like-for-like replacement of PM99's existing English 92-club
carrier set: 20 Premier League, 24 Championship, 24 League One and 24 League
Two clubs.  It does not add teams, competitions or promotion/relegation rules,
and it does not modify the executable.

The picker has only twenty cells per panel.  It is evidence for selecting a
club, but not evidence that only eighty English teams exist or that a carrier
number implies a division.

## Required compiler rules

For all 92 carriers, the compiler must:

1. use the indexed variable-length EQ string writer for club, stadium and
   full-club names;
2. write the club's 2015/16 roster, manager, capacity and only runtime-proven
   finance and initial-tactics lanes;
3. preserve or prove the competition membership/order state before assigning
   a club to a carrier;
4. render its kit to the same carrier in every compatible kit archive; and
5. apply a proven minifoto or flag the record as incomplete.  An unrelated
   old PM99 photo is never an acceptable substitute.

## Mandatory proof gates

* Structural: 92 parsed carrier records and a valid linked roster for every
  club.
* Membership: new-game captures prove all four intended divisions.  The run
  must catch a club appearing in its old PM99 division.
* Runtime: inspect a representative club, squad, manager, finances, tactics,
  kit and minifoto in each division.
* Portrait: every player has an identity-qualified source/crop receipt, or
  the release is explicitly marked incomplete.
* Product: the browser editor uses the same variable-length EQ writer as the
  season compiler and has parser plus runtime regression coverage.

## Known non-database scope

League display names and calendar date are separate executable patcher work.
3D skin/hair appearance is a separate SIMULDAT asset/preset investigation and
is not inferred from a player portrait or position.
