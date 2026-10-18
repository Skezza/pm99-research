"""Bind the five already-evidenced omissions to the shared field-change lane.

Produces a proposal only. Never installs, publishes, or writes native games.
"""
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as changes


def main():
    root=registry.ROOT/'.local/consolidated-audit-20261009/Hyde2013-native-delivery-v1'
    proof=pipeline.read_json_file(root/'profile-country-gap-proof.json')
    request=dict(schema=changes.INPUT_SCHEMA,season=proof['season'],
                 release_id=proof['release_id'],kind=changes.KIND,changes=[])
    for case in proof['cases']:
        identity=case['original_profile']['identity']
        request['changes'].append(dict(carrier_id=case['carrier_id'],field_mask=['nationality'],
            source=dict(**case['evidence'],url=identity['source_profile_url'],
                        provider_player_id=identity['provider_player_id'])))
    destination=root/'country-only-source-input.json'
    if destination.exists():
        assert pipeline.read_json_file(destination)==request
    else:
        pipeline.write_canonical_json(destination,request)
    base=registry.load_registered_release(proof['season'],proof['release_id'])
    plan=changes.prepare(base,destination)
    changes.verify(base,plan)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after,after_eq=changes.apply(before,eq,plan)
    assert changes.apply(after,after_eq,plan)==(after,after_eq)
    assert sum(a!=b for a,b in zip(before,after))==5 and after_eq==eq
    changes.bind(pipeline.read_json_file(base.package_path),plan)
    pipeline.write_canonical_json(root/changes.filename(plan),plan)
    print(dict(transaction_id=plan['transaction_id'],validated_country_bytes=5,
               idempotent=True,native_files_written=0,published=False))


if __name__=='__main__':main()
