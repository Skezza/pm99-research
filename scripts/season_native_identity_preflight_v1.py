"""Read-only new-person preflight against a registered game's actual identities.

Matches require historical review; no spelling-based merge is automatic.
Inherited actors are inspected even when their recipe DOB is a preserve policy.
A clean result does not exhaust every possible alias. No game is edited.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "upstream/pm99-skezmod-db-editor"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from app.fdi_indexed import IndexedFDIFile
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_package_compiler_v2 as compiler
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def normalise_name(value):
    name = re.sub(r"^\s*#\d+\s+", "", str(value).casefold())
    return "".join(char for char in unicodedata.normalize("NFKD", name)
                   if char.isalnum())


def audit(season, release_id, child_path):
    release = registry.load_registered_release(season, release_id)
    child_path = Path(child_path)
    child = pipeline.read_json_file(child_path)
    parent = pipeline.read_json_file(release.package_path)
    if child["season"] != parent["season"]:
        raise ValueError("child recipe and registered parent seasons differ")
    actors = {actor["carrier_id"]: actor for actor in parent["players"]}
    person_ids = {actor["person_id"] for actor in parent["players"]
                  if isinstance(actor["person_id"], str)}
    introduced = [actor for actor in child["players"]
                  if isinstance(actor["person_id"], str)
                  and actor["person_id"] not in person_ids]
    owners = {}
    for club in parent["clubs"]:
        for player_id in club["roster_player_ids"]:
            owners.setdefault(player_id, []).append(
                dict(carrier=club["carrier_id"], name=club["name"]))
    jug_path = release.game_path / "DBDAT/JUG98030.FDI"
    raw = jug_path.read_bytes()
    identities, failures = {}, []
    parsed_count = 0
    for entry in IndexedFDIFile.from_bytes(raw).entries:
        try:
            payload = entry.decode_payload(raw)
            native = roster.native_player(payload, entry.record_id)
            fields = compiler._read_native_dd6360_fields(payload, native["name_end"])
            dob = (f"{fields['birth_year']:04}-{fields['birth_month']:02}-"
                   f"{fields['birth_day']:02}")
            actor = actors.get(entry.record_id, {})
            names = [native["name"], *native["name"].split(","),
                     actor.get("source_name", ""), actor.get("name", "")]
            row = dict(carrier=entry.record_id, native_name=native["name"],
                       native_dob=dob, recipe_policy=actor.get("policy"),
                       recipe_person_id=actor.get("person_id"),
                       owners=owners.get(actor.get("id"), []))
            for name in {normalise_name(value) for value in names if value}:
                identities.setdefault((name, dob), {})[entry.record_id] = row
            parsed_count += 1
        except Exception as error:
            failures.append(dict(carrier=entry.record_id, error=str(error)))
    rows = []
    for actor in introduced:
        dob = actor["facts"].get("birth_date")
        result = dict(new_carrier=actor["carrier_id"],
                      new_name=actor.get("source_name"), new_dob=dob,
                      parent_native_name_dob_matches=[])
        if not isinstance(dob, str):
            result["status"] = "source-DOB-unavailable-no-identity-approval"
        else:
            names = {actor.get("source_name", ""), actor.get("name", "")} - {""}
            matches = {carrier: row for name in names
                       for carrier, row in identities.get(
                           (normalise_name(name), dob), {}).items()}
            result["parent_native_name_dob_matches"] = list(matches.values())
        rows.append(result)
    return dict(
        utc=datetime.now(timezone.utc).isoformat(), season=season, parent=release_id,
        parent_package_sha256=registry.sha256_file(release.package_path),
        parent_native_jug_sha256=registry.sha256_file(jug_path),
        child_sha256=registry.sha256_file(child_path),
        new_actor_count=len(introduced), parsed_native_records=parsed_count,
        unparsed_records=failures, rows=rows,
        qualification=("Native DOB and complete names plus published comma aliases. "
                       "Matches require review; absence is not exhaustive alias proof. "
                       "Unparsed records and unavailable source DOBs remain explicit. "
                       "Existing person-ID moves need separate ownership checks. "
                       "Read-only; no release or historical closure credits."))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season")
    parser.add_argument("parent_release")
    parser.add_argument("child_recipe", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("existing evidence must not be overwritten")
    result = audit(args.season, args.parent_release, args.child_recipe)
    pipeline.write_canonical_json(args.output, result)
    matches = sum(bool(row["parent_native_name_dob_matches"])
                  for row in result["rows"])
    print(f"{result['new_actor_count']} new identities; "
          f"{result['parsed_native_records']} Native records read; "
          f"{len(result['unparsed_records'])} unread; {matches} review candidates")


if __name__ == "__main__":
    main()
