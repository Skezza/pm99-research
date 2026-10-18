"""Register a private candidate and prove a full source reconstruction.

Does not update preferred games. Fresh runner review must follow.
"""
from datetime import UTC,datetime
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import publish_paired_whole_club_delta_v1 as publisher
from scripts import season_paired_whole_club_reconstruction_v1 as source
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009'
RELEASE='sourced-eastleigh-original-opening-20261017-r121a'
REPLAY='replayed-eastleigh-original-opening-20261017-r121b'
SEASON='2014-15'


def main():
    complete=ROOT/'Eastleigh2014-complete-v1'
    proof=ROOT/'Eastleigh2014-native-readback.json'
    identities=ROOT/'Eastleigh2014-identity-readback.json'
    result=publisher.publish(complete,proof,identities,RELEASE)
    retained(ROOT/'Eastleigh2014-native-delivery-v1/private-registration.json',dict(utc=datetime.now(UTC).isoformat(),**result))
    print(dict(actual_private_release=RELEASE,preferred_changed=False),flush=True)
    original=registry.load_registered_release(SEASON,RELEASE)
    result=source.reconstruction(original,REPLAY)
    if result is None or not result['complete_game_inventory_identical'] or not result['complete_recipe_identical']:
        raise ValueError('whole SOURCE reconstruction failed')
    rebuilt=registry.load_registered_release(SEASON,REPLAY)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(original.inventory_path))
    if rebuilt.package_path.read_bytes()!=original.package_path.read_bytes():raise ValueError('whole SOURCE recipe bytes differ')
    retained(ROOT/'Eastleigh2014-native-delivery-v1/complete-SOURCE-replay.json',dict(utc=datetime.now(UTC).isoformat(),**result))
    print(dict(SOURCE_complete=True,preferred_changed=False,runner_pending=True),flush=True)


if __name__=='__main__':main()
