"""Repair current Eastleigh inputs without repeating old native builds.

Source-only complete-club proposal. Existing original sources and previously
delivered birthday proofs are replayed; no current season is regenerated.
"""
import copy
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import derive_provider_identity_resolutions_v1 as derivation
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import season_prior_delivered_birthday_witness_v1 as prior
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/Eastleigh2014-current-source-v1'


def prepare():
    old=pipeline.read_json_file(registry.ROOT/'.local/duplicate-ownership-v3/whole-club-fit-scan-r1/2014-15/3322-eastleigh.json')
    bindings=old['bindings'];pin=bindings['snapshot']
    people,events,actual_pin=context.load_snapshot(registry.ROOT/pin['path'],registry.ROOT/pin['pinned_receipt_path'])
    if actual_pin!=pin:raise ValueError('existing original snapshot pin differs')
    people,events,receipt=public.merge_bound(people,events,bindings)
    print('Original identity and transfer sources replayed',flush=True)
    captures,_=roster.load_sources('2014-15')
    opening=next(c for c in captures if c['source_path']=='soccerbase/team/4252/august')
    annual=next(c for c in captures if c['source_path']=='eng/2014-2015/confprem/eastleigh.txt')
    if roster.SourceVerifier('2014-15').verify(annual)['status']!='raw-source-reparsed':
        raise ValueError('original annual did not replay')
    actual=replay.replay_club('2014-15',opening,people,True,allow_missing_birth_date=True)
    review,gaps=derivation.derive('2014-15','Eastleigh',actual,annual,people)
    # Do not allow an agreeing pair of stale provider birthdays to undo a
    # correction already independently proved and delivered in other seasons.
    reviews={r['source_provider_person_id']:r for r in review['resolutions']}
    for year,person_id in (('2006-07','soccerbase:39723'),('2010-11','soccerbase:29353')):
        delivered=registry.load_registered_release(year,'sourced-original-birthday-disagreements-20261016-r114a')
        path=registry.ROOT/delivered.locator['sourced_profile_assignment_plan_path']
        plan=pipeline.read_json_file(path)
        bio=next(r['soccerbase_person'] for rows in actual['identity_bridges'].values() for r in rows
            if r['soccerbase_person']['source_player_id']==person_id)
        source=next(r for r in plan['updates'] if r['original_numeric_profile']['url']==bio['source_profile_url'])
        row=dict(source_provider_person_id=person_id,name=bio['name'],published_birth_date=bio['birth_date'],
            canonical_birth_date=source['birth_date'],canonical_source_player_id=person_id,
            corroboration_url=source['original_numeric_profile']['url'],
            reason='Reuse the exact original numerical actor and independently replayed prior delivered birthday proof; retain the current dated opening membership and reject stale conflicting annual/provider dates.',
            prior_delivered_birthday_witness=dict(policy=prior.POLICY,season=year,release_id=delivered.release_id,
                plan_path=registry.relative_workspace_path(path),plan_sha256=registry.sha256_file(path)))
        prior.resolve(row,bio,annual);reviews[person_id]=row
    noice=registry.ROOT/'.local/consolidated-audit-20261009/Eastleigh2014-secondary-birthday-v1/Noice-original-secondary-birthday-admission.json'
    secondary=pipeline.read_json_file(noice)
    for row in secondary['resolutions']:reviews[row['source_provider_person_id']]=copy.deepcopy(row)
    gaps=[g for g in gaps if g['provider_person_id'] not in reviews]
    if gaps:raise ValueError('unresolved original identity gaps: '+str(gaps))
    review.update(resolutions=sorted(reviews.values(),key=lambda r:r['source_provider_person_id']),
        allow_explicitly_reviewed_missing_provider_birth_date=True,
        derivation_policy='original-provider-and-explicit-replayed-prior-delivery-or-secondary-source-v1',
        secondary_admission=dict(path=registry.relative_workspace_path(noice),sha256=registry.sha256_file(noice)))
    path=ROOT/'explicit-original-identities.json'
    retained(path,review)
    verified=whole.matchday_people(actual,annual,identity_resolutions=reviews,people=people)
    print('Original matchday identities:',[(r['source_player']['name'],r['source_player']['birth_date']) for r in verified],flush=True)
    base=registry.load_preferred_release('2014-15')
    output=ROOT/'3322-eastleigh-current-proposal.json'
    whole.prepare('2014-15',3322,'Eastleigh',registry.ROOT/bindings['published_person_supplement']['path'],
        registry.ROOT/bindings['published_transfer_supplement']['path'],registry.ROOT/old['entity_binding']['path'],output,
        capacity_bundle=old['capacity_policy_bundle'],baseline_release_id=base.release_id,inspect_collisions=True,
        snapshot_binding=pin,snapshot_loader=lambda *args:(people,events,actual_pin),
        public_loader=lambda *args:(people,events,receipt),identity_review_path=path,
        allow_keeper_order_exchange=True,allow_original_matchday_only_club_identity=True,
        allow_original_provider_career_reserves=True,fit_verified_reserve_pool=True)
    proposal=pipeline.read_json_file(output)
    print(dict(proposal=registry.relative_workspace_path(output),schema=proposal['schema_version'],
        people=len(proposal['desired_people']),collisions=len(proposal['outside_collisions']),
        allocation_gap=proposal.get('allocation_gap'),native_writes=0),flush=True)


if __name__=='__main__':
    if ROOT.exists():raise ValueError('retained current source attempt exists; inspect instead of overwriting')
    ROOT.mkdir(parents=True)
    prepare()
