"""Finish the otherwise omitted legacy English layer after the foreign v3 build."""
import os
import time
from collections import Counter
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_2015_english_rating_calibration_v3 as english
from scripts import season_quality_only_delta_v1 as quality
from scripts.build_all_rating_calibrations_20261011 import ROOT as BATCH,release_id
from scripts.build_quality_only_delivery_v1 import build
from scripts.audit_delivered_rating_calibrations_v1 import audit
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts import capture_registered_season_runtime_v1 as capture

SEASON='2015-16'
ROOT=BATCH/'2015-16-english'
RELEASE='sourced-rating-calibration-2015-english-20261011-r102a'
REPLAY='replayed-rating-calibration-2015-english-20261011-r102b'
TAG='rating_calibration_2015_16_english_r102a_20261011'
PROFILES=((9260,'afellay','Afellay'),(9277,'arnautovic','Arnautovic'),(1790,'messi','Messi'))

def main():
    deadline=time.monotonic()+7200
    while not (BATCH/SEASON/'complete-SOURCE-replay.json').exists():
        if time.monotonic()>deadline:raise ValueError('bounded English rating baseline wait expired')
        time.sleep(10)
    base=registry.load_registered_release(SEASON,release_id(SEASON));ROOT.mkdir(parents=True,exist_ok=True)
    plan_path=ROOT/'quality-plan.json'
    if not plan_path.exists():retained(plan_path,quality.prepare(base,english.KIND))
    plan=pipeline.read_json_file(plan_path)
    players={p['carrier_id']:p for p in english.overlay(base)[0]['players']}
    updates={p['carrier_id']:p for p in plan['updates']}
    if not all(updates[carrier]['ratings']['values']['handling']<=20 for carrier in (9260,9277)):
        raise ValueError('reported English outfield handling regression')
    from app.fdi_indexed import IndexedFDIFile
    from scripts import season_historical_roster_audit_v1 as roster
    raw=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(raw).entries}
    for carrier,p in players.items():
        if roster.native_player(entries[carrier].decode_payload(raw),carrier)['position']!=p['facts']['primary_position']:
            raise ValueError('English source keeper/outfield class disagrees with actual game')
    retained(ROOT/'pre-build-English-position-and-handling-gates.json',dict(source_players_checked=len(players),
        primary_position_mismatches=[],reported_carriers=[9260,9277],planned_updates=len(plan['updates']),
        handling_after={str(c):updates[c]['ratings']['values']['handling'] for c in (9260,9277)}))
    build(base,english.KIND,ROOT,RELEASE,REPLAY)
    if not (ROOT/'all-updated-players-native-readback.json').exists():print(audit(SEASON,root=ROOT,release_name=RELEASE),flush=True)
    retained(ROOT/'calibration-summary.json',dict(season=SEASON,baseline=base.release_id,release_id=RELEASE,
        updated_players=len(plan['updates']),methods=dict(Counter(x['ratings']['provenance']['method'] for x in plan['updates'])),
        ratings_only=True,English_overlay_recipe_and_native_fixed=True,foreign_players_unchanged=True))
    release=registry.load_registered_release(SEASON,RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=TAG,compact_evidence=True,release_id=RELEASE)
    captured(command,evidence,ROOT/'startup-transport.json',release,env)
    from scripts.season_duplicate_ownership_plan_v1 import package_layers
    all_players={p['carrier_id']:p for _,pkg,_ in package_layers(release) for p in pkg['players']}
    for carrier,label,token in PROFILES:
        target=ROOT/'runtime'/(label+'-retry1' if label=='messi' else label)
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label+('_retry1' if label=='messi' else ''),'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',all_players[carrier]['name'],
            '--player-label',label,'--profile-name-token',token,'--profile-only',
            '--provenance-file',str(release.compiler_receipt_path)]
        captured(command,target,ROOT/(label+'-profile-transport.json'),release,env)
        print(dict(actual_English_rating_profile=label,carrier=carrier,original_image_review_pending=True),flush=True)

if __name__=='__main__':main()
