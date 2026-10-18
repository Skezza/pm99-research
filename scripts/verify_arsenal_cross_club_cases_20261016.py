"""Close only the eleven frozen opponent-XI copies with positive owner proof.

Disappearance is insufficient: Brentford's original numeric XI must contain
all11 publisher identities, and each unchanged native copy must remain there.
"""
from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_historical_transfer_review_v1 as identities
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_arsenal_2021_owned_opening_v1 as source
from scripts import season_historical_opening_review_v1 as opening
from scripts.backfill_exact_opening_club_aliases_v1 import unique_capture
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_arsenal_owned_opening_20261016 import ROOT,SEASON,BASE,RELEASE


def verify():
    base=registry.load_registered_release(SEASON,BASE)
    actual=registry.load_registered_release(SEASON,RELEASE)
    before=pipeline.read_json_file(base.package_path);after=pipeline.read_json_file(actual.package_path)
    plan=pipeline.read_json_file(ROOT/'opening-ownership-plan.json')
    frozen_path=ROOT.parent/'cross-club-identities-enriched.json'
    frozen=pipeline.read_json_file(frozen_path)
    rows=next(s for s in frozen['seasons'] if s['season']==SEASON)['candidates']
    replaced={r['carrier_id'] for r in plan['assignment']['replacements']
        if r['before_recipe']['club_id']=='english-club-309'}
    cases=[c for c in rows if any(p['carrier_id'] in replaced for p in c['players'])]
    if len(cases)!=11 or any(c['identity'][0]!='published-person' or len(c['players'])!=2 for c in cases):
        raise ValueError('exact eleven frozen published-person pairs required')
    capture_path=registry.ROOT/'.local/transfermarkt-opening-plans-current-v1/2021-22/opening-lineups.json'
    capture=pipeline.read_json_file(capture_path)
    club=next(c for c in before['clubs'] if c['carrier_id']==301)
    if club['name']!='Brentford':raise ValueError('retained native club identity changed')
    captured=unique_capture(club,capture['clubs'])
    if captured is None:raise ValueError('retained Brentford lacks one original numeric opening')
    positive=opening.verify_opening(captured,capture,capture_path.parent/'cache')
    expected={c['identity'][1] for c in cases}
    if (positive['date']!='2021-08-13' or positive['source_club_id']!=1148
        or {int(id) for id in positive['starting_xi']}!=expected):
        raise ValueError('positive original Brentford XI does not establish these eleven owners')
    people,_,_=source.assignment.source.published_index()
    old={p['carrier_id']:p for p in before['players']};new={p['carrier_id']:p for p in after['players']}
    represented={}
    for p in after['players']:
        person=identities.unique_person(p,people)
        if person is not None and person['source_player_id'] in expected:
            represented.setdefault(person['source_player_id'],[]).append(p['carrier_id'])
    jug=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(actual.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    owners=ownership.native_owners(eq)
    old_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(original).entries}
    new_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    dispositions=[]
    for case in cases:
        pid=case['identity'][1]
        retired=next(p['carrier_id'] for p in case['players'] if p['carrier_id'] in replaced)
        keep=next(p['carrier_id'] for p in case['players'] if p['carrier_id']!=retired)
        if (old[keep]['club_id']!=club['id'] or new[keep]!=old[keep] or owners.get(keep)!={301}
            or represented.get(pid)!=[keep]
            or any(identities.unique_person(old[c],people)['source_player_id']!=pid for c in (keep,retired))
            or old_entries[keep].decode_payload(original)!=new_entries[keep].decode_payload(jug)):
            raise ValueError('frozen duplicate retained owner/native/global identity not proved')
        native=facts.native_facts(jug,keep)
        if native['birth_date']!=new[keep]['facts']['birth_date']:
            raise ValueError('retained Brentford native original-person birthday differs')
        if owners.get(retired)!={309} or new[retired]['club_id']!='english-club-309':
            raise ValueError('replacement did not stay in the same exclusive Arsenal carrier')
        case_id=pipeline.canonical_json_sha256(dict(season=SEASON,case=case))
        dispositions.append(dict(case_id=case_id,season=SEASON,
            state='confirmed-fault-repaired-current-game',source_person_id=pid,
            retained_native_carrier=keep,retained_owner='Brentford',
            replaced_native_carrier=retired,replacement=new[retired]['source_name'],
            exact_retained_native_record_preserved=True,positive_original_first_XI=positive))
    result=dict(season=SEASON,release_id=RELEASE,manifest_sha256=actual.manifest_sha256,
        plan_sha256=registry.sha256_file(ROOT/'opening-ownership-plan.json'),
        frozen_cases_binding=source.assignment.source.bound(frozen_path),
        exact_original_owner_capture=source.assignment.source.bound(capture_path),
        confirmed_frozen_cases_repaired=len(dispositions),dispositions=dispositions,
        retained_Brentford_XI_records_identical=True,new_Arsenal_actors_not_extra_copies=True,
        other_frozen_cases_not_approved=True)
    retained(ROOT/'independent-eleven-cross-club-case-proof.json',result)
    print(dict(exact_frozen_cross_club_cases_repaired=11,preferred_publication_pending=True),flush=True)
    return result


if __name__=='__main__':verify()
