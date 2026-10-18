"""Retain an explicit missing-date resolution; not a consensus/date closure."""
from datetime import UTC,datetime
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_external_soccerbase_birthday_v1 as secondary
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/Eastleigh2014-secondary-birthday-v1'


def prepare():
    capture_path=registry.ROOT/'.local/season-2014-15/soccerbase-august-english-nonleague-v1.json'
    captures=pipeline.read_json_file(capture_path)
    rows=[c for c in captures['clubs'] if c['source_path']=='soccerbase/team/4252/august']
    if len(rows)!=1:raise ValueError('one original numerical Eastleigh capture required')
    actual=replay.replay_club('2014-15',rows[0],{},True,allow_missing_birth_date=True)
    if (actual['fixture']['date'],actual['fixture']['game_id'],actual['club'])!=('2014-08-09',696467,'Eastleigh'):
        raise ValueError('original Eastleigh opening identity/date differs')
    people=[r['soccerbase_person'] for r in actual['identity_bridges']['published_bench']
        if r['soccerbase_person']['source_player_id']=='soccerbase:77024']
    if len(people)!=1 or people[0]['birth_date'] is not None:raise ValueError('original Noice missing-date state changed')
    bio=people[0];profile=next(p for p in actual['raw_sources'] if p['url']==bio['source_profile_url'])
    raw=registry.ROOT/'.local/duplicate-ownership-v3/eastleigh-source-consensus-review-r1/2014-15/additional-biography-sources/statscrew-noice.html'
    receipt=raw.with_name(raw.name+'.source.json');meta=pipeline.read_json_file(receipt)
    external=dict(path=registry.relative_workspace_path(raw),sha256=meta['sha256'],url=meta['url'],
        source_receipt_path=registry.relative_workspace_path(receipt),source_receipt_sha256=registry.sha256_file(receipt))
    gap=raw.parent.parent/'source-gap.json'
    review=dict(source_provider_person_id=bio['source_player_id'],name=bio['name'],published_birth_date=None,
        canonical_birth_date='1995-09-27',canonical_source_player_id=bio['source_player_id'],
        secondary_birthday_policy=secondary.POLICY,original_profile=profile,external_biography=external,
        corroboration_url=external['url'],
        reason='Original dated bench/person/profile and playing spell identify the actor. Use the literal StatsCrew secondary birthday; do not invent a date or claim independent consensus. Preserve the unadmitted conflicting date lead.',
        competing_date_lead=dict(published_date_reported='1996-01-01',provider='Sofascore',
            independently_captured_or_admitted=False,retained_gap_path=registry.relative_workspace_path(gap),retained_gap_sha256=registry.sha256_file(gap)))
    person=secondary.resolve(review,bio,actual)
    return dict(schema_version='pm99-explicit-provider-person-identity-resolution-v1',season='2014-15',club='Eastleigh',
        resolutions=[review],allow_explicitly_reviewed_missing_provider_birth_date=True,
        derivation_policy=secondary.POLICY,
        source_capture=dict(path=registry.relative_workspace_path(capture_path),sha256=registry.sha256_file(capture_path)),
        resolved_person=person,independent_birthday_consensus_claimed=False,native_writes=0,recipe_writes=0,
        cases_closed=0,fixture_membership_reparsed_from_originals=True)


if __name__=='__main__':
    path=ROOT/'Noice-original-secondary-birthday-admission.json'
    if path.exists():raise ValueError('completed original secondary admission must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    retained(path,dict(utc=datetime.now(UTC).isoformat(),**prepare()))
    print(dict(original_numeric_August_bench_replayed=True,literal_secondary_birthday='1995-09-27',
        competing_lead_retained=True,consensus_claimed=False,native_writes=0,cases_closed=0),flush=True)
