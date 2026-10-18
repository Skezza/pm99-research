"""Audit only new null-country actors against their already-bound originals."""
import argparse
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_soccerbase_secondary_facts_v2 as source
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def run(season,release_id,proposal_path,output):
    if output.exists():raise ValueError('completed bounded source audit must not repeat')
    release=registry.load_registered_release(season,release_id)
    proposal=pipeline.read_json_file(proposal_path)
    package=pipeline.read_json_file(release.package_path);actors={p['carrier_id']:p for p in package['players']}
    rows=[]
    for row in proposal['allocation']:
        person=row['replacement'];desired=person['source_player']
        if desired.get('nationality') is not None:continue
        evidence=person['raw_evidence'];path=registry.ROOT/evidence['local_path']
        if registry.sha256_file(path)!=evidence['source_sha256']:raise ValueError('bound original body changed')
        found=source.country(path.read_bytes(),person_id=int(path.stem),name=desired['name'],birth_date=desired['birth_date'],
            url='https://www.soccerbase.com/players/player.sd?player_id='+path.stem)
        actor=actors[row['carrier_id']]
        if (actor['source_name'],actor['facts']['birth_date'],actor['facts']['nationality'])!=(desired['name'],desired['birth_date'],'XXX'):
            raise ValueError('expected current source-composition country omission differs')
        rows.append(dict(carrier_id=row['carrier_id'],name=desired['name'],current_recipe_country='XXX',
            classification='confirmed-source-composition-country-omission',proposed_nationality=found['nationality'],
            original_profile=found,evidence=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
            delivered=False))
    retained(output,dict(season=season,release_id=release_id,manifest_sha256=release.manifest_sha256,
        proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
        cases=rows,new_confirmed_country_omissions=len(rows),native_writes=0,
        original_cross_club_baseline_unchanged=True,scope='Five new source country omissions, not unavailable/unsupported facts; no whole-season fact approval.'))
    print(dict(confirmed_country_omissions=len(rows),native_writes=0),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--season',required=True);p.add_argument('--release',required=True)
    p.add_argument('--proposal',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    run(a.season,a.release,a.proposal,a.output)
