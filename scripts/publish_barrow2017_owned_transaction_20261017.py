"""Private atomic delivery and complete SOURCE proof; never promotes by itself."""
from scripts import season_verified_owned_roster_transaction_v1 as transaction
from scripts.prepare_barrow2017_opening_source_20261017 import FOLDER,retained
from scripts import publish_historical_role_delta_v1 as publisher

RELEASE='sourced-owned-opening-20261017-r146a'
REPLAY='replayed-owned-opening-20261017-r146b'


def main():
    path=FOLDER/'source-owned-roster-0af29910882af17f04e700c0.json'
    plan=transaction.pipeline.read_json_file(path)
    base=transaction.registry.load_registered_release(plan['season'],plan['release_id'])
    transaction.verify(base,plan)
    descriptor=FOLDER/'role-delta-input.json'
    retained(descriptor,dict(season=base.season,release_id=base.release_id,
        package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if not transaction.registry.locator_path(base.season,RELEASE).exists():
        publisher.publish(base.season,descriptor,release_id=RELEASE,
            source_release_id=base.release_id,profile_assignment_plan_path=path)
    actual=transaction.registry.load_registered_release(base.season,RELEASE)
    if (FOLDER/'complete-SOURCE-replay.json').exists():raise ValueError('completed SOURCE proof must not repeat')
    result=transaction.reconstruction(actual,REPLAY)
    retained(FOLDER/'complete-SOURCE-replay.json',result)
    print(dict(private_release=RELEASE,**result,preferred_changed=False),flush=True)


if __name__=='__main__':main()
