"""Bind replacement-specific role review and the already-delivered v3 model.

Never recalibrate the rest of a club or season. A contemporary first-City-spell
account supports a right-wing editorial classification, not an assertion of
the player's exact August2000 tactical deployment or numerical FIFA abilities.
"""
import copy
from datetime import date
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_rating_calibration_v3 as calibration
from scripts.capture_tachira_2014_original_people_v1 import source_rows

POLICY = 'source-bound-period-reserve-v3-abilities-and-first-spell-winger-review-v1'
SOURCE_KEY = 'cross-club-2000-wright-phillips-contemporary-winger-original-20261016'
SOURCE_URL = 'https://www.theguardian.com/football/2005/jul/18/newsstory.sport1'


def parse_role(raw):
    page = BeautifulSoup(raw, 'lxml')
    titles = [t.get_text(' ', strip=True) for t in page.select('title')]
    dates = [m.get('content') for m in page.select('meta[property="article:published_time"]')]
    paragraphs = [p.get_text(' ', strip=True) for p in page.select('p')]
    if (titles != ['From licence to thrill City to riches on Blues bench | Football | The Guardian']
            or dates != ['2005-07-18T11:22:43+01:00']
            or not any('Shaun Wright-Phillips, the very right-winger' in p for p in paragraphs)
            or not any("Wright-Phillips terrorising left-backs while marauding down Manchester City's right" in p
                for p in paragraphs)):
        raise ValueError('right-wing review lacks the explicit contemporary first-spell person and side')
    return dict(fine_roles=[11], grade='reviewed-editorial',
        basis='Contemporary2005 account of the same first City spell explicitly identifies right-wing/right-side play; reviewed historical role classification, not exact August2000 match deployment.',
        exact_target_match_role_claimed=False, future_FIFA_used=False)


def review(season, club, replacement, person, policy):
    if (policy != POLICY or season != '2000-01' or club['name'] != 'Manchester City'
            or replacement['name'] != 'Shaun Wright-Phillips'
            or replacement['birth_date'] != '1981-10-25' or replacement['position'] != 'F'
            or person['source_player_id'] != 'wikipedia:Shaun_Wright-Phillips'):
        raise ValueError('replacement output policy is outside its positively reviewed identity/season')
    path, raw, binding = source_rows(SOURCE_KEY)
    receipt = path.with_suffix('.source.json')
    if pipeline.read_json_file(receipt)['url'] != SOURCE_URL:
        raise ValueError('replacement role publication URL differs')
    role = parse_role(raw)
    layer = registry.ROOT / '.local/season-english-preseason-rating-policy-v4' / season / 'english-rating-audit.json'
    source = pipeline.read_json_file(layer)
    key = calibration.old._club_key(club['name'])
    strengths = calibration.old.english_strengths(layer)
    divisions = [r['current_division'] for r in source['club_strengths']
        if calibration.old._club_key(r['club']) == key]
    if len(divisions) != 1 or divisions[0] not in calibration.DIVISION_BOUNDS:
        raise ValueError('replacement lacks one dated English club/division rating prior')
    low, high = calibration.DIVISION_BOUNDS[divisions[0]]
    strength = max(low, min(high, round(60 + (strengths[key] - 60) * 0.8)))
    from scripts.season_soccerbase_duplicate_source_policy_v1 import person_id
    player = dict(name=replacement['name'], source_name=replacement['name'],
        person_id=person_id(person), club_id=club['id'],
        facts=dict(birth_date=replacement['birth_date'], primary_position=replacement['position'],
            height_cm=replacement.get('height_cm'), fine_roles=role['fine_roles']))
    values = calibration.editorial(player, strength, 'opening_squad', date(2000, 8, 1))
    if set(values) != set(calibration.old.MAPPING) or not 1 <= values['handling'] <= 20:
        raise ValueError('replacement v3 model violates the ten-skill/outfield-handling contract')
    implementation_paths = [__file__, calibration.__file__, calibration.old.__file__,
        calibration.model.__file__, layer]
    inputs = [dict(path=registry.relative_workspace_path(Path(p)), sha256=registry.sha256_file(Path(p)))
        for p in implementation_paths]
    return dict(policy=POLICY, role_review=role, ratings=dict(profile='pm99-visible-skills-v1',
        values=values, provenance=dict(method='identity-club-role-age-optional-editorial-calibration-v3',
            proof_grade='reviewed-editorial', source_ids=[calibration.SOURCE_ID])),
        rating_basis=dict(club_strength=strength, division=divisions[0], opening_status='opening_squad',
            native_nonstarter_independently_proved=True, FIFA_values_claimed=False),
        original_publication=dict(binding, url=SOURCE_URL,
            receipt_path=registry.relative_workspace_path(receipt), receipt_sha256=registry.sha256_file(receipt)),
        implementation_inputs=inputs, unchanged='All other people and all their ten skills; identities/ownership/tactics/assets outside the selected replacement.')


def apply_output(player, row):
    output = row.get('source_bound_replacement_output')
    if output is None:
        return player
    if (output.get('policy') != POLICY or player['source_name'] != 'Shaun Wright-Phillips'
            or player['facts']['birth_date'] != '1981-10-25' or player['facts']['primary_position'] != 'F'
            or output['role_review']['fine_roles'] != [11]):
        raise ValueError('replacement output changes an unreviewed identity or role')
    for binding in output['implementation_inputs']:
        if registry.sha256_file(registry.ROOT / binding['path']) != binding['sha256']:
            raise ValueError('replacement model or source prior changed')
    result = copy.deepcopy(player)
    result['facts']['fine_roles'] = list(output['role_review']['fine_roles'])
    result['ratings'] = copy.deepcopy(output['ratings'])
    return result
