"""Bind actual bitmap-digit readbacks to the reviewed native player values."""
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts import read_profile_skill_digits_v1 as digits
from scripts import read_profile_age_digits_v1 as age_digits
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def expected_profile_age(release, player, *, allow_preserved_native_birthdate=False):
    """Use a sourced DOB, or an explicitly permitted native-preserve preimage.

    The latter checks runtime rendering only, not historical birthday accuracy.
    Never treat an arbitrary malformed/missing recipe value as that permission.
    """
    from datetime import date
    birthday = player['facts'].get('birth_date')
    if isinstance(birthday, str):
        parsed = date.fromisoformat(birthday)
        return dict(expected_age=int(release.season[:4])-parsed.year,
                    basis='recipe-birthday')
    if (allow_preserved_native_birthdate is not True
            or birthday != {'policy': 'preserve-existing-mode1'}):
        raise ValueError('profile needs a recipe DOB or explicit native-preserve age validation')
    from scripts.season_within_club_reserve_repair_v1 import native_facts
    raw = (release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    observed = native_facts(raw, player['carrier_id'])['birth_date']
    return dict(expected_age=int(release.season[:4])-date.fromisoformat(observed).year,
                basis='declared-preserved-native-birthday-not-independent-historical-proof',
                native_birth_date=observed, historical_birthday_certified=False)


def verify_profiles(root,season,release_id,profiles,*,allow_preserved_native_birthdate=False):
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
        age_basis=expected_profile_age(release,players[carrier],
            allow_preserved_native_birthdate=allow_preserved_native_birthdate)
        if (age['observed_age']!=visual['observed_age']
                or age['observed_age']!=age_basis['expected_age']):
            raise ValueError('actual bitmap-font age differs from visual review or native year: '+label)
        if age_basis['basis'] != 'recipe-birthday':
            age['age_comparison_basis']=age_basis
        retained(root/(label+'-original-age-proof.json'),age)
    print(dict(original_digit_profiles_verified=len(profiles),season=season,recipe_used_to_decode=False),flush=True)
