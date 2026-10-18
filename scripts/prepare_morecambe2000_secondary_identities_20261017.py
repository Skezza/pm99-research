"""Admit the four missing original DOBs and one unpublished bench role."""
from scripts import season_external_soccerbase_birthday_v2 as birthdays
from scripts import season_original_secondary_bench_role_v1 as bench_roles
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import capture_stock_replacement_sources_20261010 as cache
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = birthdays.registry.ROOT / '.local/consolidated-audit-20261009/morecambe2000-source-closure-20261017'


def main():
    output = ROOT / 'provider-identity-and-bench-role-review-v2.json'
    if output.exists():
        raise ValueError('completed Morecambe identity admission must not repeat')
    actual = birthdays.pipeline.read_json_file(ROOT / 'original-opening-equivalence.json')['actual']
    prior = birthdays.pipeline.read_json_file(ROOT / 'secondary-birthdays-source-admission.json')
    reviews = prior['reviews']
    if len(reviews) != 4:
        raise ValueError('all four original missing DOBs must have positive secondary witnesses')
    actors = {r['soccerbase_person']['source_player_id']: r['soccerbase_person']
        for group in actual['identity_bridges'].values() for r in group}
    for review in reviews:
        birthdays.resolve(review, actors[review['source_provider_person_id']], actual)
    matches = [b for b in actors.values() if b['name'] == 'Chris Price' and b['birth_date'] == '1975-10-24']
    if len(matches) != 1:
        raise ValueError('original full bench person/DOB differs')
    bio = matches[0]
    path = cache.ROOT / 'morecambe2000-chris-price-official-club-role.html'
    receipt = cache.ROOT / 'morecambe2000-chris-price-official-club-role.source.json'
    external = dict(path=birthdays.registry.relative_workspace_path(path),
        sha256=birthdays.registry.sha256_file(path), url=birthdays.pipeline.read_json_file(receipt)['url'],
        source_receipt_path=birthdays.registry.relative_workspace_path(receipt),
        source_receipt_sha256=birthdays.registry.sha256_file(receipt))
    role_review = dict(policy=bench_roles.POLICY, source_provider_person_id=bio['source_player_id'],
        name=bio['name'], birth_date=bio['birth_date'], primary_position='M',
        original_profile=next(p for p in actual['raw_sources'] if p['url'] == bio['source_profile_url']),
        external_biography=external)
    role_proof = bench_roles.resolve(role_review, bio, actual)
    desired = whole.matchday_people(actual, dict(players=[]),
        identity_resolutions={r['source_provider_person_id']: r for r in reviews},
        role_resolutions={bio['source_player_id']: role_review})
    whole.validate_opening_birth_dates(desired, actual['fixture']['date'])
    if len(desired) != 16 or sum(p['membership'] == 'starting_xi' for p in desired) != 11:
        raise ValueError('positive source admission did not preserve the complete eleven plus five')
    retained(output, dict(schema_version='pm99-explicit-provider-person-identity-resolution-v1',
        season='2000-01', club='Morecambe', resolutions=reviews, bench_role_resolutions=[role_review],
        allow_explicitly_reviewed_missing_provider_birth_date=True,
        evidence_policy='Original numerical fixture/profile/career plus explicit secondary facts; no fake provider IDs, known-date changes or starter-role inference.'))
    retained(ROOT / 'complete-matchday-people-source-proof-v2.json', dict(
        season='2000-01', desired_people=desired, original_XI=11, original_bench=5,
        secondary_missing_birthdays_resolved=4, secondary_biographical_bench_roles=1,
        bench_role_proof=role_proof, native_writes=0, allocation_or_collision_or_manager_or_assets_approved=False))
    print(dict(original_matchday_people_positive=16, missing_birthdays_resolved=4,
               unpublished_bench_role_resolved=1, native_writes=0), flush=True)


if __name__ == '__main__':
    main()
