# Mode-1 managed-club boundary (2026-08-29)

## Result

Foreign modern carriers can be selected as pre-season opponents, but cannot be
used as the manager's club through the normal new-game selector.  Selecting
Spain and F.C. Barcelona during the first-rival picker leaves the managed club
as Arsenal.  The game dashboard labels Barcelona as `CPU` and Arsenal as the
player's club.

This is a boundary on what a normal dashboard route proves.  It is not a
statement that Barcelona's database record is unused: the same screen reads
Barcelona's manager link and club name.  It does mean that clicking `GROUND`
or `FINANCE` from that dashboard opens the English managed club's data.

## Capacity controls and foreign-opponent proof

The first dashboard/`GROUND` route remains a negative control: it is scoped to
the English club the user manages, so it cannot be used as evidence about the
selected foreign opponent.  The same bounded Barcelona mutation was then
tested through an actual Barcelona-versus-Arsenal pre-season match, whose
half-time panel names both clubs and reads the home stadium data.

The bounded mutation is:

- EQ record `1`, F.C. Barcelona / Camp Nou, mode `1`, record size `700`.
- Signed seated-capacity lane changed from `120000` to `123456`.
- The FDI payload remained `2005` bytes; standing capacity remained `0`.
- Only the seated lane bytes changed: raw payload offset `93`, file offset
  `7172` (two value bytes differ for these numbers).
- The runner mounted the mutated `EQ98030.FDI` hash
  `6e93d9a04ab9dda6826f7e2a02bf9581b58fcdd9937f66acc6b3090006ce87ef`.

The negative-control Ground screen showed **Arsenal / Emirates Stadium /
60,338 seats**, not Barcelona. It proves the dashboard boundary, not a
foreign capacity effect.

The fresh friendly control screen showed **F.C. Barcelona / Camp Nou /
120,000 spectators**. With the same game flow and only the 93–94 capacity
bytes altered, the half-time screen showed **F.C. Barcelona / Camp Nou /
123,456 spectators**. This is the missing mode-1 runtime proof for the
seated-capacity lane.

## Evidence

- Mutation receipt:
  `.local/research-probes/mode1-barcelona-capacity-20260829/mutation-receipt.json`
- Mounted-file receipt:
  `artifacts/mode1_dashboard_route/mode1_barcelona_capacity_20260829/dbdat_override.sha256`
- Dashboard after Barcelona selection:
  `artifacts/mode1_dashboard_route/mode1_barcelona_capacity_20260829/screens/30_pretransfer_inspect_02.png`
- The negative-control Ground screen:
  `artifacts/mode1_dashboard_route/mode1_barcelona_capacity_20260829/screens/33_inspect_ground.png`
- Foreign-opponent baseline, 120,000:
  `artifacts/mode1_dashboard_route/mode1_barcelona_opponent_screen_20260829/screens/36_inspect_opponent.png`
- Foreign-opponent mutation, 123,456:
  `artifacts/mode1_dashboard_route/mode1_barcelona_capacity_123456_verified_20260829/screens/36_inspect_barcelona_halftime.png`

## Consequences

1. Mode-1 seated capacity is **green** for existing parsed carriers.  It is a
   bounded signed lane, not permission to touch standing capacity or other
   stadium metadata.
2. Mode-1 finance remains **amber**. The dashboard's
   `FINANCE` route is only evidence for the club the user manages.
3. The half-time page exposes foreign `TACTICS` and `LINE-UP` labels, but
   native clicks on either control leave that page unchanged. The normal
   friendly route therefore still does **not** expose a foreign opening XI or
   tactical grid. Their mode-1 candidate remains preserve-only until a real
   before/after UI or loader proof exists.
4. The pre-match `LINE-UPS` control is not an opponent-XI screen. It only
   changes the Match Options display toggle from `OFF` to `ON`; the captured
   page still contains no Barcelona XI or tactical coordinates. It therefore
   cannot be used as initial-state evidence either. See
   `artifacts/mode1_dashboard_route/mode1_barcelona_prematch_lineups_20260829/screens/33_inspect_match_lineups.png`.
4. Reusable runner helpers must describe this honestly.  The route helper
   `run_mode1_dashboard_route_probe.sh` is intentionally documented as a
   pre-season-*rival* probe, not a foreign dashboard probe.
