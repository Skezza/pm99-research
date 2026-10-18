"""Compile the complete sourced Barnet squad onto a redundant Hartlepool carrier.

Private actual game only; original source replay and existing native guards apply.
This does not publish or close any frozen duplicate case.
"""
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import prepare_paired_whole_club_dispositions_v1 as paired
from scripts import prepare_paired_whole_club_native_v1 as native
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/Barnet2018-native-delivery-v1'
SOURCE = registry.ROOT / ('.local/consolidated-audit-20261009/'
    'whole-club-matchday-career-scan-20261017-r2/2018-19/3317-barnet.json')


def main():
    pair_path = ROOT / 'complete-singleton-source.json'
    if (ROOT / 'native').exists():
        raise ValueError('inspect retained native attempt; never overwrite or repeat')
    proposal = pipeline.read_json_file(SOURCE)
    if (proposal['outside_collisions'] or proposal['allocation_gap']
            or len(proposal['desired_people']) != 17
            or proposal['before_club']['carrier_id'] != 3317
            or [c['carrier_id'] for c in proposal['retained_duplicate_clubs']] != [3300]):
        raise ValueError('complete Barnet source and retained Hartlepool pair required')
    baseline = registry.load_preferred_release('2018-19')
    if baseline.release_id != proposal['release_id']:
        raise ValueError('baseline advanced; preserve proposal and inspect changes')
    manager_path = ROOT / 'source-cache/manager/344.html'
    manager, person = native.dated_manager_identity(manager_path.read_bytes(), '2018-08-04')
    if (manager, person) != ('John Still', 844):
        raise ValueError('original numeric manager/dated tenure differs')
    pair = dict(schema_version=paired.SINGLETON_SCHEMA, season='2018-19',
        release_id=baseline.release_id, proposals=[dict(
            path=registry.relative_workspace_path(SOURCE), sha256=registry.sha256_file(SOURCE))],
        native_writes=0, registered=False, publication_authorised=False)
    pair['source_guard'] = paired.source_guard(pair, [proposal])
    ROOT.mkdir(parents=True, exist_ok=True)
    # A pre-native interpreter/dependency failure may already have saved the
    # source group. retained() requires byte-equivalent content; never replace it.
    retained(pair_path, pair)
    print(dict(source_guard=pair['source_guard'], dated_manager=manager), flush=True)
    result = native.prepare(pair_path, {3317: manager_path}, ROOT / 'native')
    retained(ROOT / 'native-build-summary.json', dict(utc=datetime.now(UTC).isoformat(),
        machine='joe-Vostro-3350', source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        corrected_slots=result['corrected_slots'], preferred_changed=False,
        remaining=['source-bound ground and kit', 'independent native readback',
            'whole SOURCE reconstruction', 'targeted original runner', 'bounded publication']))
    print(dict(private_native_game_built=True, corrected_slots=result['corrected_slots'],
        preferred_changed=False), flush=True)


if __name__ == '__main__':
    main()
