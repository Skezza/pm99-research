"""Read current coach ownership/names against previously retained dated claims.

No source fetch, native write, recipe write or manager-case closure. A matching
surname is not proof of full identity. Ambiguous display names and owners stay
separate instead of being passed through a relaxed publication guard.
"""
from collections import Counter
from datetime import date

from scripts import season_kit_render_bindings_v1
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import audit_deferred_manager_tenures_20261016 as sources
from scripts import season_manager_display_repair_v1 as display
from scripts.season_package_display_alias_repair_v1 import _portable_source_text
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/cached-manager-delivery-20261016-v2'


def main():
    path = ROOT / 'deferred-tenure-source-audit-v2.json'
    original = pipeline.read_json_file(path)
    loaded = {}; rows = []
    for case in original['rows']:
        claims = [c for c in case['claims'] if c['original_download_receipt_verified']]
        if case['status'] != 'unanimous-reparsed-August1-tenure-candidate' or not claims:
            continue
        source = claims[0]; raw_path = registry.ROOT / source['path']
        if registry.sha256_file(raw_path) != source['sha256']:
            raise ValueError('retained manager raw source changed')
        parsed = sources.tenure(raw_path.read_bytes(), case['source_club_id'], date.fromisoformat(source['date']))
        if any(parsed[k] != source[k] for k in ('manager', 'source_manager_id', 'source_url', 'date')):
            raise ValueError('retained manager tenure no longer independently parses')
        for receipt in source['download_receipts']:
            if registry.sha256_file(registry.ROOT / receipt['receipt_path']) != receipt['receipt_sha256']:
                raise ValueError('original download receipt changed')
        season = case['season']
        if season not in loaded:
            release = registry.load_preferred_release(season)
            package = pipeline.read_json_file(release.package_path)
            holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI',
                                            ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
            loaded[season] = release, package, holders, names
        release, package, holders, names = loaded[season]
        club = next(c for c in package['clubs'] if c['id'] == case['club_id'])
        manager = next(m for m in package['managers'] if m['id'] == club['manager_id'])
        mid = manager['carrier_id']; actual = names[mid]
        short, reason = display.short_name(source['manager'])
        desired = _portable_source_text(short) if short else None
        owners = sorted(c['carrier_id'] for c in holders.get(mid, []))
        if owners != [club['carrier_id']]:
            classification = 'non-exclusive-native-owner-needs-separate-resolution'
        elif desired is None:
            classification = 'ambiguous-source-display-needs-explicit-reviewed-alias'
        elif actual.casefold() == desired.casefold():
            classification = 'native-surname-compatible-not-full-identity-proof'
        elif actual.casefold() == source['manager'].casefold():
            classification = 'native-full-name-compatible-needs-canonical-source-admission'
        else:
            classification = 'exclusive-native-visible-name-disagrees-with-dated-source'
        rows.append(dict(season=season, club=club['name'], source_club_id=case['source_club_id'],
            club_carrier=club['carrier_id'], manager_carrier=mid, current_recipe_manager=manager,
            current_native_name=actual, current_native_owners=owners,
            source_full_name=source['manager'], source_manager_id=source['source_manager_id'],
            source_short_name=desired, short_name_policy=reason, classification=classification,
            raw_source=source, source_tenure_reparsed=True, actual_current_release_id=release.release_id,
            native_ENT_sha256=registry.sha256_file(release.game_path / 'DBDAT/ENT98030.FDI'),
            native_EQ_sha256=registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI')))
    if len(rows) != 53:
        raise ValueError('original receipt-backed unanimous scope changed')
    result = dict(source_audit=dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path)),
        rows=rows, classes=dict(Counter(r['classification'] for r in rows)),
        native_writes=0, recipe_writes=0, manager_cases_closed=0,
        scope='Current native name/owner triage of53 retained exact-year source candidates; not final source-person collision admission or publication. Never count compatible surnames as verified complete identities.')
    retained(ROOT / 'current-native-tenure-triage-v1.json', result)
    print(dict(rows=len(rows), classes=result['classes'], native_writes=0, cases_closed=0), flush=True)


if __name__ == '__main__':
    main()
