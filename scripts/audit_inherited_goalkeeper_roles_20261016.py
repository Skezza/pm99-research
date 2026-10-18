"""Discover donor-GK-only roles on authored outfield identities, without writes.

The narrow candidate class requires matching declared/native broad positions,
an explicitly inherited detailed role, and an original factory goalkeeper at
the same carrier. This is not an invented detailed historical position review.
"""
from collections import Counter
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts import season_historical_roster_audit_v1 as roster
from scripts.finalize_season_release_v1 import DEFAULT_BASE
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

OUTPUT = registry.ROOT / '.local/consolidated-audit-20261009/inherited-GK-role-discovery-20261016.json'


def selected(player, native, roles, factory):
    facts = player['facts']
    return (player.get('policy') != 'preserve-existing-mode1'
        and facts.get('primary_position') in ('D','M','F')
        and native['position'] == facts['primary_position']
        and facts.get('fine_roles') == {'policy':'preserve-existing-mode1'}
        and [r for r in roles if r != 98] == [0]
        and factory['position'] == 'G'
        and roster.normalise(player['name']) == roster.normalise(native['name'])
        and roster.normalise(factory['name']) != roster.normalise(native['name']))


def main():
    if OUTPUT.exists():
        raise ValueError('completed discovery must not repeat')
    original = (DEFAULT_BASE / 'DBDAT/JUG98030.FDI').read_bytes()
    factory = {e.record_id: roster.native_player(e.decode_payload(original), e.record_id)
        for e in IndexedFDIFile.from_bytes(original).entries}
    reports = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        data = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
        entries = {e.record_id:e for e in IndexedFDIFile.from_bytes(data).entries}
        candidates, conflicts = [], []
        for label, package, path in layers.package_layers(release):
            clubs = {c['id']:c for c in package['clubs']}
            for player in package['players']:
                carrier = player['carrier_id']
                if carrier not in factory or carrier not in entries:
                    continue
                raw = entries[carrier].decode_payload(data)
                try:
                    native = roster.native_player(raw, carrier)
                    _, roles = read_indexed_native_roles(raw, carrier)
                except (ValueError, RuntimeError, IndexError) as exc:
                    conflicts.append(dict(carrier_id=carrier,reason=str(exc)))
                    continue
                if selected(player, native, roles, factory[carrier]):
                    candidates.append(dict(layer=label, player_id=player['id'], carrier_id=carrier,
                        name=player['name'], source_name=player.get('source_name'),
                        club=clubs[player['club_id']]['name'],
                        declared_broad_position=player['facts']['primary_position'],
                        native_broad_position=native['position'], native_roles=roles,
                        donor_name=factory[carrier]['name'], donor_broad_position=factory[carrier]['position'],
                        proposed_conservative_role={'D':4,'M':9,'F':12}[native['position']],
                        historical_flank_or_specialism_claimed=False))
        row = dict(season=season, release_id=release.release_id, manifest_sha256=release.manifest_sha256,
            package_sha256=registry.sha256_file(release.package_path),
            JUG_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
            candidates=candidates, candidate_count=len(candidates), native_read_failures=conflicts)
        reports.append(row)
        print(dict(season=season,candidate_count=len(candidates),native_read_failures=len(conflicts)),flush=True)
    retained(OUTPUT,dict(schema='pm99-donor-GK-only-role-on-authored-outfield-discovery-v1',
        factory_JUG_sha256=registry.sha256_file(DEFAULT_BASE/'DBDAT/JUG98030.FDI'),seasons=reports,
        candidate_count=sum(r['candidate_count'] for r in reports),
        by_broad_position=dict(Counter(c['native_broad_position'] for r in reports for c in r['candidates'])),
        native_read_failure_count=sum(len(r['native_read_failures']) for r in reports),
        game_or_recipe_writes=0, runtime_semantic_confirmation_required=True,
        scope='Only demonstrable inherited factory GK donor role on an authored same-broad-native outfielder. Broader position/ownership queues unchanged.'))


if __name__ == '__main__':
    main()
