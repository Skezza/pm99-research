"""Prove bounded Arsenal25/four-reserve allocation before native writes.

Keep represented Arsenal players in their own slots. Move the four positively
identified outside actors, and reject unexplained same-birthday identities.
This is preparation, never a completed game correction or duplicate closure.
"""
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import arsenal_2021_opening_transaction_source_v1 as source
from scripts import season_historical_transfer_review_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import season_published_display_names_v1 as displays
from scripts import season_published_family_component_v1 as families
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts import season_stevenage_opening_repair_v1 as prior
from scripts import season_opening_order_repair_v1 as ownership


def represented(players,people,desired,paired):
    """Do not equate birthdays or silently introduce another represented actor."""
    wanted={r['source_person']['source_player_id']:r for r in desired}
    known={};by_carrier={p['carrier_id']:p for p in players}
    # These are original-source corrections, not relaxed date matching.
    corrected={335721:('benwhite','1997-11-08'),253341:('robholding','1994-11-09')}
    for p in players:
        person=identities.unique_person(p,people)
        if person is not None:
            known[p['carrier_id']]=person['source_player_id']
        else:
            for pid,(name,birthday) in corrected.items():
                if (p.get('club_id')=='english-club-309'
                    and roster.normalise(p.get('source_name') or p['name'])==name
                    and p.get('facts',{}).get('birth_date')==birthday):
                    known[p['carrier_id']]=pid
    matches={pid:[c for c,id in known.items() if id==pid] for pid in wanted}
    if any(len(rows)>1 for rows in matches.values()):
        raise ValueError('desired opening person already occupies multiple game carriers')
    paired_map={r['moved_source_player_id']:r['carrier_id'] for r in paired}
    retained={};moved={}
    for pid,rows in matches.items():
        if not rows:continue
        carrier=rows[0];p=by_carrier[carrier]
        if p['club_id']=='english-club-309':retained[pid]=carrier
        elif paired_map.get(pid)==carrier:moved[pid]=carrier
        else:raise ValueError('opening actor has an unpaired outside game owner')
    if set(moved)!=set(paired_map):raise ValueError('all four coupled actors must reproduce')
    represented_ids=set(known.values())
    for row in desired+[r['replacement'] for r in paired]:
        person=row['source_person'];pid=person['source_player_id']
        names={roster.normalise(row['source_player']['name']),roster.normalise(person['name'])}
        for p in players:
            known_id=known.get(p['carrier_id'])
            if known_id==pid:continue
            if roster.normalise(p.get('source_name') or p['name']) in names:
                raise ValueError('unresolved current full-name alias blocks new person')
            # An existing identified actor is retained or moved exactly once;
            # an unrelated birthday neighbour is not a newly introduced copy.
            # For genuinely new actors require positive exclusion of every
            # birthday neighbour (the De Maio spelling trap).
            if (pid not in represented_ids and known_id is None
                and p.get('facts',{}).get('birth_date')==person['birth_date']):
                raise ValueError('unidentified same-birthday carrier blocks new person: '+str(p['carrier_id']))
    return retained,moved


def prepare(base):
    admitted=source.admission(base)
    package=pipeline.read_json_file(base.package_path)
    people,_,_=source.published_index()
    extra=source.arsenal.ROOT/'kata-original-person-identity.json'
    people,_=source.people_source.merge(people,pipeline.read_json_file(extra))
    kept,moved=represented(package['players'],people,admitted['desired_people'],admitted['paired'])
    if len(kept)!=12 or len(moved)!=4:raise ValueError('bounded twelve retained/four moved actors changed')
    players={p['carrier_id']:p for p in package['players']}
    target=[p for p in package['players'] if p['club_id']=='english-club-309']
    if len(target)!=25:raise ValueError('native Arsenal capacity must remain25')
    free=[p for p in target if p['carrier_id'] not in kept.values()]
    incoming=[r for r in admitted['desired_people'] if r['source_person']['source_player_id'] not in kept]
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    owners=ownership.native_owners(eq)
    for carrier,cid in [(p['carrier_id'],309) for p in target]+[
            (r['carrier_id'],r['club_carrier_id']) for r in admitted['paired']]:
        if owners.get(carrier)!={cid}:raise ValueError('selected native carrier is not exclusively owned')
    bundle=pipeline.read_json_file(prior.CAPACITY_PROOF)['bindings']['same_carrier_name_capacity']
    capacity.verify_bundle(bundle)
    aliases=displays.claims(source.arsenal.PUBLIC)
    family=families.claims(source.arsenal.PUBLIC,{r['source_person']['source_player_id'] for r in incoming})
    rows=allocation.allocate(jug,free,incoming,aliases,published_families=family,capacity_bundle=bundle)
    mapping=dict(kept)
    mapping.update({r['replacement']['source_person']['source_player_id']:r['carrier_id'] for r in rows})
    for paired in admitted['paired']:
        rows.extend(allocation.allocate(jug,[players[paired['carrier_id']]],[paired['replacement']],aliases,
            published_families=families.claims(source.arsenal.PUBLIC,
                {paired['replacement']['source_person']['source_player_id']}),capacity_bundle=bundle))
    if len(rows)!=17 or len(set(r['carrier_id'] for r in rows))!=17 or len(set(mapping.values()))!=25:
        raise ValueError('bounded17 replacements/25 unique Arsenal slots did not reproduce')
    return dict(season=base.season,release_id=base.release_id,
        manifest_sha256=base.manifest_sha256,source_admission=admitted,
        additional_identity_exclusion=[source.bound(extra),
            source.bound(source.arsenal.ROOT/'kata-identity-exclusion-proof.json')],
        retained_Arsenal=sorted([list(item) for item in kept.items()]),
        moved_into_Arsenal=sorted([list(item) for item in moved.items()]),
        preserved_rating_source_carriers=sorted([*kept.values(),*moved.values()]),
        ordered_Arsenal_carriers=[mapping[r['source_person']['source_player_id']] for r in admitted['desired_people']],
        replacements=rows,same_carrier_capacity=bundle,native_writes=0)


if __name__=='__main__':
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    base=registry.load_registered_release('2021-22','sourced-year-bound-managers-20261016-r110a')
    result=prepare(base)
    retained(source.arsenal.ROOT/'native-assignment-preparation.json',result)
    print(dict(replacements=len(result['replacements']),Arsenal_capacity=25,
        retained_rating_profiles=len(result['preserved_rating_source_carriers']),native_writes=0),flush=True)
