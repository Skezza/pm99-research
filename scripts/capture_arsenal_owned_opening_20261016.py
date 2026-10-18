"""Actual Arsenal XI/tactics, paired reserves and corrected Holding age."""
import os
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts.season_tactics_formation_runtime_v1 import selector
from scripts.build_arsenal_owned_opening_20261016 import ROOT,SEASON,RELEASE

TAG='arsenal_owned_opening_2021_22_r111a_20261016'
PROFILES=((9080,'philogene','Philogene'),(21228,'palumbo','Palumbo'),
          (14650,'rovella','Rovella'),(30550,'hartjes','Hartjes'),(9116,'holding','Holding'))


def bound_capture(command,evidence,receipt,release,env):
    if receipt.exists():
        saved=pipeline.read_json_file(receipt)
        if (saved['exit_code']!=0 or saved['release_manifest_sha256']!=release.manifest_sha256
            or saved['evidence']!=registry.relative_workspace_path(evidence)):
            raise ValueError('prior Arsenal transport failed or binds another game; inspect, do not overwrite')
        return
    captured(command,evidence,receipt,release,env)


def main():
    if not (ROOT/'native-byte-proof.json').exists():raise ValueError('actual Arsenal native proof required before runner')
    release=registry.load_registered_release(SEASON,RELEASE)
    package=pipeline.read_json_file(release.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==309)
    if club['name']!='Arsenal' or club['opening']['formation']!='4-2-3-1':raise ValueError('actual Arsenal target differs')
    coords=selector(package,club)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    # Keep the existing Stoke attestation contract unchanged; the Arsenal
    # target proof below is additional, not a waiver of normal startup checks.
    startup,startup_evidence=capture.capture_command(season=SEASON,worker='default',run_tag=TAG+'_stoke',
        compact_evidence=True,release_id=RELEASE)
    bound_capture(startup,startup_evidence,ROOT/'startup-transport.json',release,env)
    command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=TAG,
        compact_evidence=False,release_id=RELEASE)
    for flag,value in (('--team-name','Arsenal'),('--team-select-x',coords['team'][0]),
            ('--team-select-y',coords['team'][1]),('--division-select-x',coords['division'][0]),
            ('--division-select-y',coords['division'][1])):
        command[command.index(flag)+1]=str(value)
    command.extend(['--capture-route','tactics','--tactics-advanced-inspect','--tactics-advanced-matrix',
        '--tactics-native-state-proof','309','--tactics-advanced-view','general'])
    bound_capture(command,evidence,ROOT/'Arsenal-startup-tactics-transport.json',release,env)
    players={p['carrier_id']:p for p in package['players']}
    for carrier,label,token in PROFILES:
        target=ROOT/'runtime'/label;name=players[carrier]['name']
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',name,'--player-label',label,
            '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        bound_capture(command,target,ROOT/(label+'-profile-transport.json'),release,env)
        print(dict(actual_profile_captured=name,carrier=carrier,original_visual_review_pending=True),flush=True)


if __name__=='__main__':main()
