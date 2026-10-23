"""Bind independently inspected six-person profiles to the exact actual game."""
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as kits
from scripts.verify_paired_profile_runtime_v1 import profile_name_method,compare
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.build_city_opening_exchange_20261011 import ROOT,SEASON,RELEASE
from scripts.capture_city_opening_exchange_20261011 import PROFILES


def same_native_display_name(observed,expected):
    """PM99 capitalises surnames; retain accents, punctuation and full identity."""
    return isinstance(observed,str) and isinstance(expected,str) and observed.casefold()==expected.casefold()


def verify_profiles(root=ROOT,season=SEASON,release_id=RELEASE,profiles=PROFILES,*,allow_preserved_native_birthdate=False):
    release=registry.load_registered_release(season,release_id)
    from scripts.season_duplicate_ownership_plan_v1 import package_layers
    players={};player_clubs={}
    for _,package,_ in package_layers(release):
        clubs={c['id']:c for c in package['clubs']}
        for player in package['players']:
            if player['carrier_id'] in players:raise ValueError('ambiguous shared native profile carrier')
            players[player['carrier_id']]=player;player_clubs[player['carrier_id']]=clubs[player['club_id']]
    dbdat=release.game_path/'DBDAT';palette,palette_source=kits._palette(dbdat)
    kit_records=kits._record_index(dbdat/'RIDIESC.PKF')
    for carrier,label,_,_ in profiles:
        output=root/(label+'-native-runtime-proof.json')
        if output.exists():
            cached=pipeline.read_json_file(output)
            visual_path=root/(label+'-profile-visual-review.json')
            if (cached.get('season')!=season or cached.get('release_id')!=release_id
                    or cached.get('visual_review_sha256')!=registry.sha256_file(visual_path)
                    or cached.get('compiler_receipt_sha256')!=registry.sha256_file(release.compiler_receipt_path)):
                raise ValueError('saved native runtime proof binds another release/review; preserve it before re-verifying')
        transport=pipeline.read_json_file(root/(label+'-profile-transport.json'))
        target=registry.ROOT/transport['evidence']
        summaries=list(target.rglob('summary.json'))
        if len(summaries)!=1:raise ValueError('one exact actual profile summary required')
        evidence=summaries[0].parent;summary=pipeline.read_json_file(summaries[0])
        profile=summary['player_profile'];player=players[carrier];club=player_clubs[carrier]
        visual_path=root/(label+'-profile-visual-review.json');visual=pipeline.read_json_file(visual_path)
        check_visual(visual)
        from scripts.verify_profile_skill_digits_v1 import expected_profile_age
        age_basis=expected_profile_age(release,player,
            allow_preserved_native_birthdate=allow_preserved_native_birthdate)
        screenshot=evidence/'screens'/Path(profile['screenshot']).name
        if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
                or summary.get('success') is not True or summary.get('wine_debugger_detected')
                or summary.get('process_exit_code') not in (None,0)
                or profile.get('expected_name_token_satisfied') is not True
                or visual['screenshot_sha256']!=registry.sha256_file(screenshot)
                or not same_native_display_name(visual['observed_native_name'],player['name']) or visual['observed_club']!=club['name']
                or visual['observed_skills']!=player['ratings']['values']
                or not visual.get('all_ten_visible_skills_inspected')
                or visual['observed_age']!=visual['expected_age']
                or visual['expected_age']!=age_basis['expected_age']):
            raise ValueError('actual player/club/ten skills/year-based native age visual proof differs')
        if transport.get('recovered_remote_native_child'):
            from scripts.recover_completed_profile_transport_v1 import verify_mirrored_native_child
            proof_binding = transport['recovered_remote_native_child']
            proof_path = registry.ROOT / proof_binding['path']
            if (registry.sha256_file(proof_path) != proof_binding['sha256']
                    or pipeline.read_json_file(proof_path) != verify_mirrored_native_child(release, evidence)):
                raise ValueError('recovered original remote child proof differs')
        elif registry.sha256_file(evidence/'input-provenance.json')!=registry.sha256_file(release.compiler_receipt_path):
            raise ValueError('actual profile compiler provenance differs')
        hashes={line.split()[1]:line.split()[0] for line in (evidence/'dbdat_override.sha256').read_text().splitlines()
            if line and not line.startswith('#')}
        for name in ('JUG98030.FDI','EQ98030.FDI','ENT98030.FDI','MINIFOTO.PKF','RIDIESC.PKF','MINIESC.PKF','NANOESC.PKF'):
            if hashes.get('DBDAT/'+name)!=registry.sha256_file(dbdat/name):raise ValueError('actual native/asset input differs')
        pixels=compare(kit_records[club['carrier_id']],palette,screenshot)
        if not pixels['passed']:raise ValueError('actual unchanged displayed kit differs')
        result=dict(season=season,release_id=release_id,carrier_id=carrier,
            native_name=player['name'],club=club['name'],screenshot=registry.relative_workspace_path(screenshot),
            screenshot_sha256=registry.sha256_file(screenshot),visual_review_sha256=registry.sha256_file(visual_path),
            compiler_receipt_sha256=registry.sha256_file(release.compiler_receipt_path),
            summary_sha256=registry.sha256_file(summaries[0]),native_inputs_hash_verified=True,
            ten_visible_skills_verified=True,kit_pixels=pixels,palette_source=palette_source,
            name_method=profile_name_method(player['name'],profile['player_name_ocr_normalized'],visual))
        if age_basis['basis'] != 'recipe-birthday':
            result['age_comparison_basis']=age_basis
        if output.exists():
            if pipeline.read_json_file(output)!=result:
                raise ValueError('cached runtime proof differs from freshly verified original inputs/pixels')
        else:
            pipeline.write_canonical_json(output,result)
    print(dict(actual_profiles_verified=len(profiles),season=season),flush=True)


def main():verify_profiles()


if __name__=='__main__':main()
