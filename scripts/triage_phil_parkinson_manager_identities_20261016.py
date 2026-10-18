"""Reparse original numeric manager identities behind four fullname collisions.

This is evidence for the next coupled identity admission, not a game fix or
approval of an inherited same-name Aalesund coach slot.
"""
from datetime import UTC, date, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_20261016 as old
from scripts import audit_deferred_manager_tenures_20261016 as histories
from scripts import season_august_manager_tenures_20261016 as batch
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    files = histories.index(); receipts = histories.receipt_index(); rows = []
    for season in ('2020-21', '2023-24', '2024-25', '2025-26'):
        actual = registry.load_preferred_release(season)
        package = pipeline.read_json_file(actual.package_path)
        report = pipeline.read_json_file(old.REVIEWS / season / 'opening-review.json')
        reports = {c['club_id']: c for c in report['clubs']}
        for club in package['clubs']:
            if club['name'] not in ('Altrincham', 'Wrexham', 'Sunderland', 'Aalesund'):
                continue
            source = reports.get(club['id'], {}).get('evidence', {}).get('source_club_id')
            proof = (histories.inspect(files.get(source, []), source, date(int(season[:4]), 8, 1), receipts)
                if source is not None else dict(status='no-original-exact-club-binding', claims=[], unusable=[]))
            rows.append(dict(season=season, club=club['name'], club_id=club['id'], source_club_id=source,
                current_release_id=actual.release_id, current_manifest_sha256=actual.manifest_sha256,
                current_manager=next(m for m in package['managers'] if m['id'] == club['manager_id']),
                original_tenure_inspection=proof))
    output = batch.ROOT / 'phil-parkinson-original-identities.json'
    retained(output, dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', rows=rows,
        native_writes=0, recipe_writes=0, deferred_cases_closed=0,
        conclusion='Original Altrincham coach84629 and Wrexham coach3540 are distinct published people despite identical names. Sunderland2020 lacks cached August1 history; Aalesund2024 has no positive original club binding here. Use typed provider IDs only after bounded target/owner admission, not name-only merging.'))
    print(dict(original_identity_rows=len(rows), native_writes=0, deferred_cases_closed=0), flush=True)


if __name__ == '__main__':
    main()
