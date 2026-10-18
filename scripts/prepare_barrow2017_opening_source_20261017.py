"""Turn the reviewed research batch into data for the reusable source reader."""
from scripts import season_verified_opening_roster_sources_v1 as reader
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

ROOT=registry.ROOT/'.local/consolidated-audit-20261009'
FOLDER=ROOT/'Barrow2017-owned-roster-delivery-v1'


def retained(path,value):
    if path.exists():
        if pipeline.read_json_file(path)!=value:raise ValueError('retained source evidence differs')
    else:pipeline.write_canonical_json(path,value)


def source(path):
    receipt=pipeline.read_json_file(path.with_suffix('.html.source.json'))
    if receipt['sha256']!=registry.sha256_file(path):
        raise ValueError('original source receipt hash differs')
    return dict(path=registry.relative_workspace_path(path),**receipt)


def main():
    report=pipeline.read_json_file(ROOT/'luna-closeout-20261017/barrow-full18-allocation-review.json')
    cache=registry.ROOT/'.local/season-2017-18/soccerbase-august-cache-v1'
    group=dict(club_name='Barrow',provider_team_id=392,competition='National League',
        expected_opening_game_id=753821,schedule=source(cache/'team/392.html'),
        match=source(cache/'match/753821.html'),profiles={},reserves=[106585,58116],
        display_witnesses={'58116':dict(game_id=753880,match=source(cache/'match/753880.html'))})
    for row in report['desired_people']:
        binding=source(registry.ROOT/row['profile'])
        if binding['sha256']!=row['sha256']:raise ValueError('reviewed profile source differs')
        group['profiles'][str(row['provider_id'])]=binding
    verified=reader.read('2017-18',group)
    if len(verified['desired'])!=18:raise ValueError('reviewed full roster count differs')
    expected={(r['provider_id'],r['name'],r['dob'],r['role']) for r in report['desired_people']}
    observed={(r['source_person']['provider_player_id'],r['source_player']['name'],
               r['source_player']['birth_date'],r['source_player']['position']) for r in verified['desired']}
    if expected!=observed:raise ValueError('reviewed source identities differ from originals')
    FOLDER.mkdir(exist_ok=True)
    retained(FOLDER/'opening-source-input.json',group)
    retained(FOLDER/'opening-source-readback-v2.json',verified)
    print(dict(original_XI=11,original_bench=5,positive_opening_reserves=2,
               secondary_fact_gaps=len(verified['secondary_fact_gaps']),native_writes=0),flush=True)


if __name__=='__main__':main()
