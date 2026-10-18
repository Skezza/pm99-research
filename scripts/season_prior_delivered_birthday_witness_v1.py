"""Carry an already proved actor birthday forward through a stale annual.

Require the exact same original numerical biography URL, not a name-only join
or a convenient date. Reverify the original bounded correction and its actual
delivered recipe. This does not infer new birthdays or new club membership.
"""
import copy
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_source_bound_birthday_disagreements_v1 as birthdays
from scripts import season_historical_roster_audit_v1 as roster

POLICY='same-original-numeric-profile-prior-delivered-birthday-witness-v1'


def resolve(review,bio,annual):
    witness=review.get('prior_delivered_birthday_witness',{})
    if witness.get('policy')!=POLICY or review['published_birth_date']!=bio['birth_date']:
        raise ValueError('prior birthday witness cannot change the original profile identity')
    delivered=registry.load_registered_release(witness['season'],witness['release_id'])
    path=registry.ROOT/witness['plan_path']
    if (registry.sha256_file(path)!=witness['plan_sha256']
            or path.resolve()!=(registry.ROOT/delivered.locator['sourced_profile_assignment_plan_path']).resolve()):
        raise ValueError('prior delivered birthday source plan changed')
    plan=pipeline.read_json_file(path)
    if plan.get('schema')!=birthdays.SCHEMA:raise ValueError('prior witness is not a source-verified birthday-only correction')
    base=registry.load_registered_release(plan['season'],plan['release_id']);birthdays.verify(base,plan)
    rows=[r for r in plan['updates'] if r['original_numeric_profile']['url']==bio['source_profile_url']]
    if len(rows)!=1:raise ValueError('prior birthday lacks the same exact original numerical profile')
    row=rows[0]
    if (row['original_full_name']!=bio['name'] or review['name']!=bio['name']
            or review['source_provider_person_id']!=bio['source_player_id']
            or review['canonical_source_player_id']!=bio['source_player_id']
            or review['canonical_birth_date']!=row['birth_date']
            or bio['birth_date'] not in (row['birth_date'],row['before_birth_date'])):
        raise ValueError('prior birthday does not identify the same original actor/date disagreement')
    package=pipeline.read_json_file(delivered.package_path)
    actor=next(p for p in package['players'] if p['carrier_id']==row['carrier_id'])
    if actor['source_name']!=bio['name'] or actor['facts']['birth_date']!=row['birth_date']:
        raise ValueError('prior delivered game recipe does not contain its declared correction')
    artifact=next(a for a in package['artifacts'] if a['id']==birthdays.PREFIX+plan['season'])
    if artifact['sha256']!=registry.sha256_file(path):raise ValueError('prior delivered recipe does not bind the original proof')
    named=[p for p in annual['players'] if roster.normalise(p['name'])==roster.normalise(bio['name'])]
    dates={p.get('birth_date') for p in named}
    if len(named)!=1 or not dates <= {row['before_birth_date'],row['birth_date']}:
        raise ValueError('period annual is neither the proved nor explicitly rejected prior birthday')
    person=copy.deepcopy(bio)
    person.update(birth_date=row['birth_date'],source_provider='soccerbase',identity_policy=POLICY,
        prior_delivered_birthday_witness=copy.deepcopy(witness))
    return person
