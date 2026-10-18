"""Prove the one fully resolved frozen pair; Aldred's remaining pair stays open."""
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_opening_order_repair_v1 as owners
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_historical_roster_audit_v1 as roster
from scripts.backfill_exact_opening_club_aliases_v1 import unique_capture
from scripts.publish_eastleigh_private_20261017 import ROOT,RELEASE,SEASON
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def verify():
    output=ROOT/'Eastleigh2014-native-delivery-v1/independent-frozen-case-proof.json'
    if output.exists():raise ValueError('completed frozen-case proof must not repeat')
    proposal=pipeline.read_json_file(ROOT/'Eastleigh2014-current-source-v1/3322-eastleigh-current-proposal.json')
    base=registry.load_registered_release(SEASON,proposal['release_id'])
    actual=registry.load_registered_release(SEASON,RELEASE)
    before=pipeline.read_json_file(base.package_path);after=pipeline.read_json_file(actual.package_path)
    frozen_path=ROOT/'cross-club-identities-enriched.json';frozen=pipeline.read_json_file(frozen_path)
    cases=next(r['candidates'] for r in frozen['seasons'] if r['season']==SEASON)
    selected=[c for c in cases if c['identity']==['published-person',223790]]
    if len(selected)!=1 or {r['carrier_id'] for r in selected[0]['players']}!={9574,11157}:
        raise ValueError('exact original Luke Simpson pair changed')
    case=selected[0];club=next(c for c in before['clubs'] if c['carrier_id']==324)
    capture_path=registry.ROOT/'.local/transfermarkt-opening-plans-current-v1/2014-15/opening-lineups.json'
    capture=pipeline.read_json_file(capture_path);captured=unique_capture(club,capture['clubs'])
    if captured is None:raise ValueError('retained Accrington lacks a unique original opening')
    positive=opening.verify_opening(captured,capture,capture_path.parent/'cache')
    if positive['date']!='2014-08-09' or positive['source_club_id']!=3688 or '223790' not in positive['starting_xi']:
        raise ValueError('original first XI does not establish the retained original keeper')
    old={p['carrier_id']:p for p in before['players']};new={p['carrier_id']:p for p in after['players']}
    represented=[p['carrier_id'] for p in after['players'] if roster.person_identity_key(p)==('lukesimpson','1994-09-23')]
    if represented!=[9574] or old[9574]!=new[9574] or new[9574]['club_id']!=club['id']:
        raise ValueError('retained whole recipe identity or exclusive representation differs')
    jug=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes();original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    old_entry=next(e for e in IndexedFDIFile.from_bytes(original).entries if e.record_id==9574)
    new_entry=next(e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id==9574)
    if old_entry.decode_payload(original)!=new_entry.decode_payload(jug):raise ValueError('retained keeper native record changed')
    ownership=owners.native_owners((actual.game_path/'DBDAT/EQ98030.FDI').read_bytes())
    if ownership.get(9574)!={324} or ownership.get(11157)!={3322}:raise ValueError('exact native club owners differ')
    if facts.native_facts(jug,9574)['birth_date']!='1994-09-23' or new[11157]['source_name']!='Ross Flitney':
        raise ValueError('native original keeper identity or sourced replacement differs')
    case_id=pipeline.canonical_json_sha256(dict(season=SEASON,case=case))
    result=dict(season=SEASON,release_id=RELEASE,manifest_sha256=actual.manifest_sha256,
        frozen_cases_binding=dict(path=registry.relative_workspace_path(frozen_path),sha256=registry.sha256_file(frozen_path)),
        exact_original_owner_capture=dict(path=registry.relative_workspace_path(capture_path),sha256=registry.sha256_file(capture_path)),
        confirmed_frozen_cases_repaired=1,dispositions=[dict(case_id=case_id,season=SEASON,
            state='confirmed-fault-repaired-current-game',source_person_id=223790,retained_native_carrier=9574,
            retained_owner='Accrington Stanley',replaced_native_carrier=11157,replacement='Ross Flitney',
            positive_original_first_XI=positive,exact_retained_native_record_preserved=True)],
        Tom_Aldred_other_two_club_copies_still_open=True,preferred_publication_pending=True)
    retained(output,result)
    print(dict(frozen_cases_repaired=1,remaining_Aldred_pair_not_closed=True,preferred_publication_pending=True),flush=True)


if __name__=='__main__':verify()
