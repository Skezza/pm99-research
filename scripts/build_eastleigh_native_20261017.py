"""Create one private actual-game correction after complete source fitting."""
from datetime import UTC,datetime
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import prepare_paired_whole_club_dispositions_v1 as paired
from scripts import prepare_paired_whole_club_native_v1 as native
from scripts.supplement_soccerbase_opening_lineups_v1 import Cache
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/Eastleigh2014-native-delivery-v1'
SOURCE=registry.ROOT/'.local/consolidated-audit-20261009/Eastleigh2014-current-source-v1/3322-eastleigh-current-proposal.json'


def main():
    pair_path=ROOT/'complete-singleton-source.json'
    if pair_path.exists():raise ValueError('retained native attempt exists; inspect before continuing')
    proposal=pipeline.read_json_file(SOURCE)
    if proposal['outside_collisions'] or proposal['allocation_gap'] or len(proposal['desired_people'])!=17:
        raise ValueError('complete source allocation not ready')
    base=registry.load_preferred_release('2014-15')
    if base.release_id!=proposal['release_id']:raise ValueError('current game advanced; do not overwrite')
    ROOT.mkdir(parents=True,exist_ok=True)
    manager=ROOT/'source-cache/manager/4252.html'
    url='https://www.soccerbase.com/teams/team.sd?team_id=4252&teamTabs=managers'
    raw=Cache(ROOT/'source-cache',offline=False,delay=1).get(url,'manager/4252.html')
    name,person=native.dated_manager_identity(raw,proposal['original_opening']['fixture']['date'])
    if name!='Richard Hill':raise ValueError('dated original manager does not agree with intended actor')
    retained(manager.with_name(manager.name+'.source.json'),dict(url=url,sha256=registry.sha256_file(manager)))
    pair=dict(schema_version=paired.SINGLETON_SCHEMA,season='2014-15',release_id=base.release_id,
        proposals=[dict(path=registry.relative_workspace_path(SOURCE),sha256=registry.sha256_file(SOURCE))],
        native_writes=0,registered=False,publication_authorised=False)
    pair['source_guard']=paired.source_guard(pair,[proposal])
    retained(pair_path,pair)
    print(dict(complete_source_guard=pair['source_guard'],manager=name,manager_id=person),flush=True)
    result=native.prepare(pair_path,{3322:manager},ROOT/'native')
    retained(ROOT/'native-build-summary.json',dict(utc=datetime.now(UTC).isoformat(),
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',machine='joe-Vostro-3350',
        candidate=registry.relative_workspace_path(ROOT/'native'),corrected_slots=result['corrected_slots'],
        public=False,remaining=['source-bound assets','independent native identity proof','full SOURCE','runner','bounded publication']))
    print(dict(actual_private_game_created=True,players=result['corrected_slots'],public=False),flush=True)


if __name__=='__main__':main()
