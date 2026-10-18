"""Build one original annual-cohort label repair without changing its people."""
import json
import shutil
from scripts import season_period_squad_carrier_label_v2 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import build_registered_quality_release_v1 as reconstruction
from scripts.build_original_carrier_label_20261017 import external
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=source.registry.ROOT/'.local/consolidated-audit-20261009/hertha2000-cohort-label-20261017'
SEASON='2000-01'
BASE='sourced-takano-period-country-20261017-r136a'
RELEASE='sourced-hertha-cohort-label-20261017-r137a'
REPLAY='replayed-hertha-cohort-label-20261017-r137b'


def inputs():
    return dict(preallocation=source.prior.bind(source.registry.ROOT/'.local/transfermarkt-opening-plans-current-v1/2000-01/opening-squad-preallocation.json'),
        fixed_registry=source.prior.bind(source.registry.ROOT/'seasons/2000-01/fixed-carrier-registry.json'),
        clubs=[dict(carrier_id=421,coach=dict(published_full_name='Jürgen Röber',published_club_name='Hertha BSC',
            original=external('hertha2000-roeber-original-career'),club_alias_original=dict(kind='UEFA-Hertha-Roeber-2002-departure-v1',
                original=external('hertha2000-original-uefa-2002-departure'))),
            ground=dict(kind='official-Hertha-Olympiastadion-continuity-v1',original=external('hertha2000-official-stadium-history')))])


def verify_native(base,actual,plan):
    source.verify(base,plan)
    before=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes();after=(actual.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    expected,changes=source.prior.labels.rewrite_club_labels(before,plan['updates'])
    if expected!=after or len(changes)!=1:raise ValueError('actual Hertha labels differ from exact typed plan')
    old={e.record_id:e for e in source.prior.IndexedFDIFile.from_bytes(before).entries}
    new={e.record_id:e for e in source.prior.IndexedFDIFile.from_bytes(after).entries}
    if old.keys()!=new.keys():raise ValueError('club label edit changes fixed indexed directory IDs')
    for carrier,entry in new.items():
        a=old[carrier].decode_payload(before);b=entry.decode_payload(after)
        if carrier==421:
            if source.prior.labels.prefix_parts(a)[2]!=source.prior.labels.prefix_parts(b)[2]:
                raise ValueError('Hertha label edit changes ground/coach/roster/unknown bytes')
        elif a!=b:raise ValueError('Hertha label edit changes another native club')
    left={r['path']:r['sha256'] for r in source.pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in source.pipeline.read_json_file(actual.inventory_path)['files']}
    if left.keys()!=right.keys() or any(left[k]!=right[k] for k in left if k!='DBDAT/EQ98030.FDI'):
        raise ValueError('Hertha labels changed a player/coach/executable/image/other file')
    descriptor=source.pipeline.read_json_file(ROOT/'inert.json');manager=source.pipeline.read_json_file(ROOT/'manager-plan.json')
    if publisher.updated_package(source.pipeline.read_json_file(base.package_path),descriptor,manager_plan=manager,club_plan=plan)!=source.pipeline.read_json_file(actual.package_path):
        raise ValueError('Hertha recipe changed outside exact club identity/labels/provenance')
    return dict(season=SEASON,release_id=actual.release_id,manifest_sha256=actual.manifest_sha256,
        native_club_labels_corrected=json.loads(source.pipeline.canonical_json_bytes(changes)),
        all_players_coaches_ground_rosters_tactics_capacities_EXE_and_assets_preserved=True,
        prior_Morecambe_and_Japan_corrections_preserved=True,
        full_opening_XI_or_historical_kit_design_approved=False,global_historical_RC=False)


def main():
    ROOT.mkdir(exist_ok=True)
    if (ROOT/'club-plan.json').exists() or source.registry.locator_path(SEASON,RELEASE).exists():
        raise ValueError('existing Hertha transaction must be inspected, not regenerated')
    base=source.registry.load_preferred_release(SEASON)
    if base.release_id!=BASE:raise ValueError('Hertha parent advanced; preserve intervening changes')
    plan=source.prepare(base,inputs());retained(ROOT/'club-plan.json',plan)
    descriptor=ROOT/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    manager=ROOT/'manager-plan.json'
    retained(manager,dict(schema_version='pm99-historical-manager-plan-v1',season=SEASON,release_id=base.release_id,
        package_sha256=plan['package_sha256'],eq_sha256=plan['eq_sha256'],ent_sha256=plan['ent_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(source.registry.ROOT).free<8.15*1024**3:raise ValueError('Hertha build needs normal free-space reserve')
    publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=base.release_id,
        club_plan_path=ROOT/'club-plan.json',manager_plan_path=manager)
    actual=source.registry.load_registered_release(SEASON,RELEASE)
    retained(ROOT/'native-byte-proof.json',verify_native(base,actual,plan))
    replay=reconstruction._build_manager_reconstruction(actual,release_id=REPLAY)
    if replay is None or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('Hertha complete SOURCE proof incomplete')
    share_verified(actual,source.registry.load_registered_release(SEASON,REPLAY),ROOT)
    retained(ROOT/'complete-SOURCE-replay.json',replay)
    print(dict(Hertha_club_label_and_SOURCE_built=True,no_player_or_asset_changes=True,preferred_changed=False,runtime_pending=True),flush=True)


if __name__=='__main__':main()
