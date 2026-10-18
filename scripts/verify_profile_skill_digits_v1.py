"""Bind actual bitmap-digit readbacks to the reviewed native player values."""
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts import read_profile_skill_digits_v1 as digits
from scripts import read_profile_age_digits_v1 as age_digits
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def verify_profiles(root,season,release_id,profiles):
    release=registry.load_registered_release(season,release_id)
    players={p['carrier_id']:p for _,pkg,_ in layers.package_layers(release) for p in pkg['players']}
    for carrier,label,_,_ in profiles:
        transport=pipeline.read_json_file(root/(label+'-profile-transport.json'))
        if transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256:
            raise ValueError('digit readback launched another native game')
        summaries=list((registry.ROOT/transport['evidence']).rglob('summary.json'))
        if len(summaries)!=1:raise ValueError('one exact completed original profile needed for digits')
        summary=pipeline.read_json_file(summaries[0])
        if not summary.get('success'):raise ValueError('original profile did not succeed')
        screenshot=summaries[0].parent/'screens'/Path(summary['player_profile']['screenshot']).name
        result=digits.read(screenshot)
        visual=pipeline.read_json_file(root/(label+'-profile-visual-review.json'))
        if (result['screenshot_sha256']!=visual['screenshot_sha256']
                or result['observed_skills']!=visual['observed_skills']
                or result['observed_skills']!=players[carrier]['ratings']['values']):
            raise ValueError('actual bitmap-font skill digits differ from visual review or native recipe: '+label)
        retained(root/(label+'-original-digit-proof.json'),result)
        age=age_digits.read(screenshot)
        if (age['observed_age']!=visual['observed_age']
                or age['observed_age']!=int(season[:4])-int(players[carrier]['facts']['birth_date'][:4])):
            raise ValueError('actual bitmap-font age differs from visual review or native year: '+label)
        retained(root/(label+'-original-age-proof.json'),age)
    print(dict(original_digit_profiles_verified=len(profiles),season=season,recipe_used_to_decode=False),flush=True)
