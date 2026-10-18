"""Deliver the admitted five-country correction privately, then prove SOURCE."""
from scripts import season_source_verified_player_changes_v1 as changes
from scripts import publish_historical_role_delta_v1 as publisher

ROOT=changes.registry.ROOT/'.local/consolidated-audit-20261009'
FOLDER=ROOT/'country-field-delivery-20261017-v1'
RELEASE='sourced-profile-countries-20261017-r145a'
REPLAY='replayed-profile-countries-20261017-r145b'


def main():
    path=ROOT/'Hyde2013-native-delivery-v1/source-backed-player-changes-5c5ef71468f2c09144e9c650.json'
    plan=changes.pipeline.read_json_file(path)
    base=changes.registry.load_registered_release(plan['season'],plan['release_id'])
    changes.verify(base,plan)
    FOLDER.mkdir(exist_ok=True)
    descriptor=FOLDER/'role-delta-input.json'
    inert=dict(season=base.season,release_id=base.release_id,
               package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[])
    if descriptor.exists():assert changes.pipeline.read_json_file(descriptor)==inert
    else:changes.pipeline.write_canonical_json(descriptor,inert)
    if not changes.registry.locator_path(base.season,RELEASE).exists():
        publisher.publish(base.season,descriptor,release_id=RELEASE,
            source_release_id=base.release_id,profile_assignment_plan_path=path)
    actual=changes.registry.load_registered_release(base.season,RELEASE)
    proof=FOLDER/'complete-SOURCE-replay.json'
    if proof.exists():raise ValueError('SOURCE already completed; do not repeat')
    result=changes.reconstruction(actual,REPLAY)
    changes.pipeline.write_canonical_json(proof,result)
    print(result,flush=True)


if __name__=='__main__':main()
