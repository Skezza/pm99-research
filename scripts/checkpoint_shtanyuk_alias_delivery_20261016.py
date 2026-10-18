"""Publish two fully proved alias corrections without changing frozen counters."""
import copy
from datetime import UTC,datetime
from pathlib import Path
from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_duplicate_layered_packages_v1 as layered
from scripts import season_stoke_original_alias_reserve_v1 as first_alias
from scripts import season_shtanyuk_2002_coupled_alias_v1 as second_alias
from scripts import season_stoke_commons_number_v1 as shirts
from scripts import season_original_alias_countries_v1 as countries
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts import build_original_alias_countries_20261016 as batch
from scripts import checkpoint_remaining_manager_tenures_20261016 as managers
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.verify_paired_profile_runtime_v1 import profile_name_method
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

SEASONS=('2001-02','2002-03')
PROFILES={'2001-02':(('commons',27013,'Stoke City',18,'Scotland'),),
    '2002-03':(('vandeurzen',10580,'Stoke City',28,'Belgium'),('khomukha',7972,'Shinnik Yaroslavl',33,'Turkmenistan'))}


def profile(release,root,label,carrier,club,age,nationality,player,native):
    visual_path=root/(label+'-profile-visual-review.json')
    visual=pipeline.read_json_file(visual_path);check_visual(visual)
    proof_path=root/(label+'-profile-runtime-proof.json');proof=pipeline.read_json_file(proof_path)
    transport=pipeline.read_json_file(root/(label+'-profile-transport.json'))
    evidence=registry.ROOT/proof['evidence']
    if not evidence.resolve().is_relative_to((root/'runtime'/label).resolve()):
        raise ValueError('profile evidence is outside its owned actor root')
    summary_path=evidence/'summary.json';summary=pipeline.read_json_file(summary_path)
    actual=summary.get('player_profile',{})
    screenshot=evidence/'screens'/Path(actual.get('screenshot','')).name
    if (visual.get('observed_native_name','').casefold()!=player['name'].casefold()
            or visual.get('observed_club')!=club or visual.get('observed_age')!=age
            or visual.get('expected_age')!=age or visual.get('observed_nationality')!=nationality
            or not visual.get('all_ten_visible_skills_inspected') or not visual.get('observed_no_photo')
            or visual.get('observed_ten_skills')!=native['native_ten_skills']
            or visual.get('observed_handling')!=native['native_ten_skills']['handling']
            or proof['carrier_id']!=carrier or proof['release_id']!=release.release_id
            or proof['package_sha256']!=registry.sha256_file(release.package_path)
            or proof['compiler_receipt_sha256']!=registry.sha256_file(release.compiler_receipt_path)
            or proof['visual_review_sha256']!=registry.sha256_file(visual_path)
            or proof['summary_sha256']!=registry.sha256_file(summary_path)
            or proof['screenshot_sha256']!=registry.sha256_file(screenshot)
            or proof['screenshot_sha256']!=visual['screenshot_sha256']
            or not proof['native_inputs_hash_verified'] or not summary.get('success')
            or summary.get('wine_debugger_detected') or summary.get('process_exit_code') not in (None,0)
            or actual.get('expected_name_token_satisfied') is not True
            or transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(root/'runtime'/label)):
        raise ValueError('source-plan actor facts/ten visible skills/original profile proof incomplete')
    if profile_name_method(player['name'],actual['player_name_ocr_normalized'],visual)!=proof['name_verification_method']:
        raise ValueError('profile exact-name proof changed')
    if registry.sha256_file(evidence/'input-provenance.json')!=registry.sha256_file(release.compiler_receipt_path):
        raise ValueError('profile launched another compiler provenance')
    launched={line.split()[1]:line.split()[0] for line in (evidence/'dbdat_override.sha256').read_text().splitlines()
        if line and not line.startswith('#')}
    for name in ('JUG98030.FDI','EQ98030.FDI','ENT98030.FDI','MINIFOTO.PKF','RIDIESC.PKF','MINIESC.PKF','NANOESC.PKF'):
        if launched.get('DBDAT/'+name)!=registry.sha256_file(release.game_path/'DBDAT'/name):
            raise ValueError('profile actual native/archive inputs changed')
    return [binding(p) for p in (visual_path,proof_path,root/(label+'-profile-transport.json'))]


def verify(season):
    root=batch.ROOT/season;release=registry.load_registered_release(season,batch.RELEASE)
    parent=registry.load_registered_release(season,managers.batch.RELEASE)
    country=pipeline.read_json_file(root/countries.FILENAME)
    country_parent=registry.load_registered_release(season,country['release_id']);countries.verify(country_parent,country)
    if pipeline.read_json_file(registry.ROOT/release.locator['sourced_profile_assignment_plan_path'])!=country:
        raise ValueError('country release does not bind its exact source plan')
    if countries.bind(pipeline.read_json_file(country_parent.package_path),country)!=pipeline.read_json_file(release.package_path):
        raise ValueError('entire final alias recipe does not reproduce')
    native=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if countries.apply((country_parent.game_path/'DBDAT/JUG98030.FDI').read_bytes(),eq,country)!=(native,eq):
        raise ValueError('final country byte delta differs')
    alias_release=country_parent
    if season=='2001-02':
        shirt=pipeline.read_json_file(registry.ROOT/country_parent.locator['sourced_profile_assignment_plan_path'])
        shirt_parent=registry.load_registered_release(season,shirt['release_id']);shirts.verify(shirt_parent,shirt)
        if shirts.bind(pipeline.read_json_file(shirt_parent.package_path),shirt)!=pipeline.read_json_file(country_parent.package_path):
            raise ValueError('Commons entire shirt-layer recipe differs')
        if shirts.apply((shirt_parent.game_path/'DBDAT/JUG98030.FDI').read_bytes(),eq,shirt)!=((country_parent.game_path/'DBDAT/JUG98030.FDI').read_bytes(),eq):
            raise ValueError('Commons source-number-only native layer differs')
        alias_release=shirt_parent
    alias=pipeline.read_json_file(registry.ROOT/alias_release.locator['ownership_plan_path'])
    alias_parent=registry.load_registered_release(season,alias['release_id'])
    if (alias_parent.release_id,alias_parent.manifest_sha256)!=(parent.release_id,parent.manifest_sha256):
        raise ValueError('composed alias chain does not descend from the published manager parent')
    (first_alias if season=='2001-02' else second_alias).verify_plan(alias_parent,alias)
    expected,english,_,_=layered.prepare(alias_parent,alias,(alias_parent.game_path/'DBDAT/JUG98030.FDI').read_bytes())
    if english is not None or expected!=pipeline.read_json_file(alias_release.package_path):
        raise ValueError('entire underlying source alias recipe differs')
    selected={r['carrier_id'] for r in alias['updates']}
    if selected!=({27013} if season=='2001-02' else {10580,7972}):raise ValueError('selected alias scope differs')
    original=(parent.game_path/'DBDAT/JUG98030.FDI').read_bytes();preserve_other_records(original,native,selected)
    for name in ('EQ98030.FDI','ENT98030.FDI'):
        if (parent.game_path/'DBDAT'/name).read_bytes()!=(release.game_path/'DBDAT'/name).read_bytes():
            raise ValueError('alias correction changed source manager/club/order/tactics files')
    archive,_=delta.no_photo_archive((parent.game_path/'DBDAT/MINIFOTO.PKF').read_bytes(),selected)
    if archive!=(release.game_path/'DBDAT/MINIFOTO.PKF').read_bytes():raise ValueError('displaced portrait removal differs')
    if any((release.game_path/f'DBDAT/MINIFOTO/J96{c:05d}.BMP').exists() for c in selected):
        raise ValueError('displaced actor retains a loose portrait override')
    old={r['path']:r['sha256'] for r in pipeline.read_json_file(parent.inventory_path)['files']}
    new={r['path']:r['sha256'] for r in pipeline.read_json_file(release.inventory_path)['files']}
    allowed={'DBDAT/JUG98030.FDI','DBDAT/MINIFOTO.PKF'}|{f'DBDAT/MINIFOTO/J96{c:05d}.BMP' for c in selected}
    if any(old.get(k)!=new.get(k) for k in set(old)|set(new) if k not in allowed):raise ValueError('alias changed another actual game file')
    package=pipeline.read_json_file(release.package_path);players={p['carrier_id']:p for p in package['players']}
    keep=27002 if season=='2001-02' else 10542
    before=next(p for p in pipeline.read_json_file(parent.package_path)['players'] if p['carrier_id']==keep)
    if players[keep]!=before:raise ValueError('correct retained Stoke defender changed')
    names={roster.normalise(n) for n in ('Sergey Shtanyuk','Sergei Shtanyuk','Siarhei Shtaniuk','Syarhey Shtanyuk','Sergei Shtaniuk')}
    if [p['carrier_id'] for p in package['players'] if any(roster.normalise(p.get(k)) in names for k in ('name','source_name'))]!=[keep]:
        raise ValueError('final represented alias owners not uniquely resolved')
    replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    rebuilt=registry.load_registered_release(season,batch.REPLAY)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical'] or replay['manifest_sha256']!=release.manifest_sha256:
        raise ValueError('final entire SOURCE proof is missing or stale')
    for game in (release,rebuilt):pipeline.assert_tree_matches_inventory(game.game_path,pipeline.read_json_file(release.inventory_path))
    pipeline.assert_tree_matches_inventory(parent.game_path,pipeline.read_json_file(parent.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:raise ValueError('actual complete SOURCE recipe differs')
    review=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(review)
    tag='original_alias_countries_'+season.replace('-','_')+'_r120a_20261016'
    directory=registry.ROOT/'.local/runlogs/pm99_runner'/tag
    transport=pipeline.read_json_file(root/'startup-transport.json');summary=pipeline.read_json_file(directory/'summary.json')
    if (review['observed_team']!='Stoke City' or review['observed_date']!=season[:4]+'-08-01'
            or review['release_manifest_sha256']!=release.manifest_sha256 or review['screenshot_sha256']!=registry.sha256_file(lineup_frame(directory))
            or transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(directory)
            or not summary.get('success') or summary.get('wine_debugger_detected') or summary.get('crash_detected')
            or summary.get('process_exit_code') not in (None,0) or summary['release_manifest_sha256']!=release.manifest_sha256
            or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']
            or not summary['route_summaries']['line_up']['team_identity']['matched']):raise ValueError('final alias startup not hash-bound and reviewed')
    readback=pipeline.read_json_file(root/'actual-actor-readbacks.json')
    if readback['manifest_sha256']!=release.manifest_sha256 or readback['recipe_sha256']!=registry.sha256_file(release.package_path):
        raise ValueError('literal final actor readback binds another game')
    rows={p['carrier_id']:p for p in readback['rows']}
    evidence=[binding(root/n) for n in (countries.FILENAME,'native-byte-proof.json','complete-SOURCE-replay.json',
        'actual-actor-readbacks.json','startup-transport.json','startup-visual-review.json')]
    for label,carrier,club,age,nationality in PROFILES[season]:
        evidence+=profile(release,root,label,carrier,club,age,nationality,players[carrier],rows[carrier])
    ancestry=[parent.release_id,alias_release.release_id]
    if country_parent.release_id!=alias_release.release_id:ancestry.append(country_parent.release_id)
    ancestry.append(release.release_id)
    return dict(season=season,release_id=release.release_id,manifest_sha256=release.manifest_sha256,
        ancestry_release_ids=ancestry,
        selected_replacement_carriers=sorted(selected),retained_Stoke_defender=keep,evidence=evidence,
        original_sources_native_full_SOURCE_and_reviewed_profiles_verified=True,unrelated_game_data_preserved=True)


def check_bindings(originals,selected):
    for season in registry.supported_seasons():
        actual=registry.load_preferred_release(season);old=originals[season]
        if (actual.release_id,actual.manifest_sha256)==(old['release_id'],old['manifest_sha256']):continue
        if season not in selected or (actual.release_id,actual.manifest_sha256)!=(batch.RELEASE,selected[season]['manifest_sha256']):
            raise ValueError('preferred drift: preserve intervening fixes and unselected seasons')


def run():
    previous=batch.ROOT.parent/'release-delivery-checklist-v55.json';output=batch.ROOT.parent/'release-delivery-checklist-v56.json'
    if output.exists():raise ValueError('completed alias publication must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(previous));old={r['season']:r for r in result['current_release_bindings']}
    # Both complete source/native/runtime gates run before the first mutation.
    rows=[verify(s) for s in SEASONS];selected={r['season']:r for r in rows}
    if sum(len(r['selected_replacement_carriers']) for r in rows)!=3:raise ValueError('additional alias actor count drift')
    check_bindings(old,selected);backup=managers.verify_original2015();evidence=[backup]
    for row in rows:
        season=row['season'];root=batch.ROOT/season;retained(root/'prepublication-proof-v2.json',row)
        publisher.register_completed_delta(season,batch.RELEASE,verified_ancestor_chain=row['ancestry_release_ids'])
        if not (root/'final-attestation.json').exists():
            retained(root/'final-attestation.json',runtime.attest(season=season,evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/
                ('original_alias_countries_'+season.replace('-','_')+'_r120a_20261016')))
        valid=registry.validate_preferred_release(season,level='playable')
        if not valid['valid']:raise ValueError('final alias preferred game failed playable validation')
        retained(root/'preferred-playable-validation.json',valid)
        evidence+=row['evidence']+[binding(root/n) for n in ('prepublication-proof-v2.json','final-attestation.json','preferred-playable-validation.json')]
    current=bindings()
    if any(r!=old[r['season']] for r in current if r['season'] not in selected):raise ValueError('unselected24 bindings changed')
    finding=dict(id='additional-Shtanyuk-transliteration-and-wrong2002-owner-v1',state='delivered-native-SOURCE-and-runner-verified',
        seasons=list(SEASONS),additional_alias_groups_closed=2,displaced_actor_slots_corrected=3,
        source_shirt_number_bytes_corrected=1,literal_source_nationality_bytes_completed=2,
        original82_and_frozen2797_denominators_and_dispositions_unchanged=True,
        one_Shinnik_starter_explicitly_source_authorised=True,full_historical_starting_XI_approval=False,
        no_photo_fallback_declared=True,all_unrelated_games_players_managers_tactics_and_artwork_preserved=True)
    result['additional_confirmed_findings'].append(finding);result['delivered_evidence']+=evidence
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(previous),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=list(SEASONS),all_required_work_complete=False,
        next_batch='Continue frozen2797 cross-club/opening-squad cases, broader position/entity/manager source queues, known-wrong facts and global kit/photo QA. Additional Shtanyuk groups delivered; no denominator reset/global historical RC.')
    pipeline.write_canonical_json(output,result)
    retained(batch.ROOT/'final-delivery-summary.json',dict(finding,checklist=binding(output),original2015_backup_verified=True,global_historical_RC=False))
    print(dict(delivered=True,**finding,checklist=binding(output)),flush=True)


if __name__=='__main__':run()
