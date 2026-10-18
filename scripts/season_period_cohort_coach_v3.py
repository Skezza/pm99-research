"""Couple positively proved annual club identity and dated coach corrections.

Never pretend a wrong inherited coach corroborates a label-only edit. The
manager plan is inseparable from this label plan and uses a published surname
for the native UI while retaining the full sourced identity in the recipe.
"""
from pathlib import Path
from scripts import admit_hertha_dated_cohort_coach_20261017 as admission

prior=admission.prior
registry,pipeline=prior.registry,prior.pipeline
SCHEMA='pm99-unanimous-period-cohort-and-closed-coach-tenure-v3'
METHOD='dated-closed-manager-tenure-v1'


def prepare(base):
    proof=admission.admit(base)
    package=pipeline.read_json_file(base.package_path)
    club=next(c for c in package['clubs'] if c['id']==proof['club_id'])
    manager=proof['manager'];year=base.season[:4]
    manager_plan=dict(schema_version='pm99-historical-manager-plan-v1',source_method=METHOD,
        season=base.season,release_id=base.release_id,package_sha256=proof['package']['sha256'],
        eq_sha256=proof['eq']['sha256'],ent_sha256=proof['ent']['sha256'],unresolved=[],
        updates=[dict(club_id=club['id'],club_carrier_id=421,club='Hertha Berlin',
            manager_id=manager['id'],carrier_id=manager['carrier_id'],before=manager['name'],
            before_policy=manager.get('policy'),native_before=proof['native_before_manager'],
            after=proof['published_full_coach'],native_after=proof['native_after_manager'],
            effective_opening_date=year+'-08-01',native_manager_owner_count=1,
            evidence=dict(raw_sources=proof['dated_coach']['originals'],
                dated_closed_tenure=proof['dated_coach']['decision'],
                source_cohort_not_first_fixture=True))])
    return dict(schema_version=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=proof['package']['sha256'],jug_sha256=proof['jug']['sha256'],
        eq_sha256=proof['eq']['sha256'],ent_sha256=proof['ent']['sha256'],
        updates=[dict(club_id=club['id'],carrier_id=421,before=club['name'],before_full=club.get('full_name'),
            after='Hertha Berlin',identity_after=prior.old.builder._source_club_identity_id(
                prior.old.roster.club_group(club),'Hertha Berlin'),native_before=proof['before_short'],
            native_full_before=proof['before_full'],native_after='Hertha Berlin')],
        manager_plan=manager_plan,admission=proof,
        implementation_inputs=[prior.bind(Path(m.__file__)) for m in (admission,admission.annual,prior)]+[prior.bind(Path(__file__))],
        scope='Only source-proved original-carrier short/full club labels and dated coach name, with exact recipe identities/provenance. Every player byte, squad order, formation, skill, fact, ground, capacity, kit, portrait and EXE preserved. Not opening-XI or historical kit certification.')


def verify(base,plan):
    if plan.get('schema_version')!=SCHEMA or prepare(base)!=plan:
        raise ValueError('coupled original cohort/dated coach source-native plan changed')


def verify_manager_pair(plan,manager_plan):
    if plan.get('schema_version')!=SCHEMA or manager_plan!=plan['manager_plan']:
        raise ValueError('coupled club identity requires its exact dated manager plan')
