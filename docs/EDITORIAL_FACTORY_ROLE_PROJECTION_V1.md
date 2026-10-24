# Source-bound editorial role projection

`season_editorial_factory_role_projection_v1` admits a narrow correction through
`season_source_verified_player_changes_v1`. It does not infer a historical fine
position from a player's reputation or replace compatible existing edits.

Admission requires the exact registered parent and retained source row/fixture,
provider identity, recipe person identity, sourced DOB and broad position to
agree with native readback. The fixture year must match the season start year.
An unknown/fallback DOB cannot qualify. The recipe must explicitly preserve its
old fine roles, and all six native slots must still equal the clean factory
carrier. That factory player must have a different name/DOB and a different
broad position, compatible with its original role but incompatible with the
current player's broad position.

The admitted editorial defaults are defender 4, midfielder 9 and forward 12.
These are compatible representatives, not sourced historical fine positions.
The plan records that distinction. Proven stale secondary roles are cleared;
all six role bytes are guarded, including unchanged empty slots. Goalkeepers,
compatible roles, explicit overlays and insufficient evidence remain untouched.

The existing common writer changes only the selected recipe fine-role field
and bounded JUG role bytes. It preserves nationality, DOB, names, ratings,
ownership, orders, tactics, kits, photos and all other native bytes. Source
reconstruction re-runs the same admission checks. A prepared plan, passing test
or successful build is not installation or runner verification.
