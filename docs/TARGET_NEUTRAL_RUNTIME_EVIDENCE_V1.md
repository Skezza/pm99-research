# Target-neutral runtime evidence preflight

`scripts/season_runtime_evidence_preflight_v1.py` is the release-bound hand-off
before a real PM99 runner capture for one historical season and one selected
club. It does not launch PM99 or create a screenshot. Its output is a
write-once plan which binds all of the following together:

- a strict canonical V2 season package;
- the final release manifest and the exact finished game-tree inventory;
- one independently recorded target-club selector profile; and
- the package's manager and opening XI expected in the captured Line-Up UI.

This prevents a common false proof: using a correct screenshot from the wrong
build, wrong season, wrong club, or inherited 2015 Stoke selector coordinates.
The resulting receipt is explicitly `preflight-passed-runtime-not-executed` and
is not a playable or runtime-success claim.

## Runtime profile

Create one canonical JSON file per chosen club, beside the final revision. The
profile is an input, not an inferred carrier property: selector coordinates
must be discovered and reviewed for the actual target build. `routes` is
lexicographically sorted and must include both `line_up` and `squad`.

```json
{
  "capture": {"profile_count": 2, "routes": ["line_up", "squad"]},
  "club": {"carrier_id": 100, "id": "club-100", "name": "Example Town"},
  "schema_version": "pm99-target-club-runtime-profile-v1",
  "season": "2000-01",
  "selector": {
    "division_select_x": 555,
    "division_select_y": 111,
    "team_name": "Example Town",
    "team_select_x": 321,
    "team_select_y": 222
  }
}
```

The profile's `club` object must exactly match the V2 package. `selector.team_name`
is the expected PM99 picker label and can only differ from `club.name` where a
reviewed display alias makes that necessary. Coordinates remain explicit because
they depend on the running picker layout, not on the fixed carrier ID.

## Preflight command

Run only after the two clean builds, final materialisers, and release metadata
exist. All paths below refer to a final, immutable revision; do not point the
command at static-ingress candidates or mutable playtest sessions.

```bash
python3 scripts/season_runtime_evidence_preflight_v1.py \
  --season-package "$REV/season-package.final.json" \
  --release-manifest "$REV/release/season-manifest.json" \
  --game-tree "$REV/build-a/game" \
  --runtime-profile "$REV/runtime-profiles/example-town.json" \
  --worker runner-1 \
  --run-tag season-2000-01-example-town-r1 \
  --output "$REV/runtime-preflight/example-town-r1.json"
```

The receipt contains an exact `launch.argv` and shell-escaped
`launch.shell_command`. It carries the selected `DBDAT` directory and calendar
executable from the inventory-verified game tree, plus the target club's own
team/division coordinates and requested routes. It also records the expected
manager, fixture date, formation (if known), and ordered opening XI from the
package so a reviewer has a concrete comparison target.

## After the preflight

Use the command embedded in the receipt, retain the runner summary and all
screens under that exact run tag, then verify that the runner reached the
declared target club and both requested routes. Only hashes for screenshots
actually produced by that successful route may be attached to the separate
release attestation.

The existing runner wrapper retains legacy `run_stoke_*` filenames. The
preflight passes target-specific `--team-name` and selector values, but does
not claim that a legacy-labelled wrapper itself is target-season proof. The
runner summary and captured UI must confirm the planned target club before the
screenshots can close the runtime gate.
