"""Capture actual final-game startup and all six corrected ownership profiles."""
import os
import subprocess
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.build_city_opening_exchange_20261011 import ROOT,SEASON,RELEASE

PROFILES=((9244,'walker','Kyle Walker','Walker'),
    (9245,'oreilly',"Nico O'Reilly",'Reilly'),
    (9250,'wilson','Josh Wilson-Esbrand','Wilson'),
    (16,'gundogan','Ilkay Gundogan','Gundogan'),
    (8564,'reis','Vitor Reis','Reis'),
    (19441,'khusanov','Abdukodir Khusanov','Khusanov'))
TAG='city_opening_2024_r97a_20261011'


def captured(command,evidence,path,release,env):
    if path.exists():
        if pipeline.read_json_file(path)['exit_code']!=0:raise ValueError('failed prior transport: '+str(path))
        return
    if evidence.exists():raise ValueError('unreceipted capture exists; inspect, never overwrite')
    completed=subprocess.run(command,env=env,check=False)
    pipeline.write_canonical_json(path,dict(exit_code=completed.returncode,
        evidence=registry.relative_workspace_path(evidence),
        release_manifest_sha256=release.manifest_sha256,visually_approved=False))
    if completed.returncode:raise ValueError('actual profile transport failed: '+str(path))


def main():
    if not all((ROOT/n).exists() for n in ('native-byte-proof.json','complete-SOURCE-replay.json')):
        raise ValueError('actual City native and complete SOURCE proofs missing')
    release=registry.load_registered_release(SEASON,RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=TAG,
        compact_evidence=True,release_id=RELEASE)
    captured(command,evidence,ROOT/'startup-transport.json',release,env)
    players={p['carrier_id']:p for p in pipeline.read_json_file(release.package_path)['players']}
    for carrier,label,search,token in PROFILES:
        # Native name is authoritative for search; source/full identity stays
        # separately recorded. No ASCII substitution of an accented identity.
        search=players[carrier]['name']
        target=ROOT/'runtime'/label
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',search,'--player-label',label,
            '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        captured(command,target,ROOT/(label+'-profile-transport.json'),release,env)
        print(dict(captured_player=search,carrier=carrier,visually_approved=False),flush=True)


if __name__=='__main__':main()
