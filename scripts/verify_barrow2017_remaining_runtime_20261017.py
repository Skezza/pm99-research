"""Record direct original-frame reviews, then verify native inputs and digits."""
from scripts import season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.verify_profile_skill_digits_v1 import verify_profiles as verify_digits

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/Barrow2017-owned-roster-delivery-v1'
RELEASE = 'sourced-owned-opening-20261017-r146a'


def main():
    rows = [
        (10989, 'dunne', '50_profile_only_dunne_done.png',
         'd15261530e59654387f3056641621e94dcd5ddb4d9eea19cad78c9909d01607e',
         'Jimmy DUNNE', 'Barrow', 'IRELAND', 20,
         [52, 61, 65, 59, 9, 57, 47, 65, 64, 42]),
        (9592, 'hornby', '58_profile_only_hornby_done.png',
         '14a1e961662083dce9ea73a9bc9b1eb38a6df0092ec8537001f92c123c1b8fe1',
         'Tyler HORNBY-FORBES', 'Accrington Stanley', 'ENGLAND', 21,
         [53, 60, 63, 60, 8, 56, 50, 66, 67, 39]),
    ]
    profiles = []
    for carrier, label, filename, digest, name, club, nation, age, skills in rows:
        frame = ROOT / 'runtime' / label / (
            'owned_opening_2017_18_r146a_20261017_' + label) / 'screens' / filename
        if registry.sha256_file(frame) != digest:
            raise ValueError('original visually reviewed frame changed')
        retained(ROOT / (label + '-profile-visual-review.json'), dict(
            method='assistant-original-image-visual-review',
            original_frame_visually_inspected=True,
            screenshot=registry.relative_workspace_path(frame), screenshot_sha256=digest,
            observed_native_name=name, observed_club=club, observed_nationality=nation,
            observed_age=age, expected_age=age, observed_role='DEFENDER',
            observed_position='INS. CENT. LEFT',
            observed_skills=dict(zip(('speed', 'stamina', 'aggression', 'quality',
                'handling', 'passing', 'dribbling', 'heading', 'tackling', 'shooting'), skills)),
            all_ten_visible_skills_inspected=True, visible_skills_match_native_baseline=True,
            portrait='no image; permitted missing portrait',
            scope='Directly reviewed actor, club, nationality, broad role, year-based age and ten skills. Fine role is editorial, not independently historically verified. Barrow inherited red/white kit is NOT historically approved.'))
        profiles.append((carrier, label, '', name))
    verify_profiles(ROOT, '2017-18', RELEASE, profiles)
    verify_digits(ROOT, '2017-18', RELEASE, profiles)


if __name__ == '__main__':
    main()
