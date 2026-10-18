"""Independently adjudicate one nominated club label, without game writes."""
from datetime import UTC,datetime
from bs4 import BeautifulSoup
from scripts import season_original_carrier_label_restoration_v1 as source
from scripts.build_original_carrier_label_20261017 import external
from scripts.build_takano_period_country_20261017 import RELEASE
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    root=source.registry.ROOT/'.local/consolidated-audit-20261009/hertha2000-cohort-label-20261017'
    root.mkdir(exist_ok=True)
    output=root/'source-native-identity-review.json'
    if output.exists():raise ValueError('existing Hertha adjudication requires inspection, not repetition')
    base=source.registry.load_registered_release('2000-01',RELEASE)
    package=source.pipeline.read_json_file(base.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==421)
    players=[p for p in package['players'] if p['club_id']==club['id']]
    pre=source.registry.ROOT/'.local/transfermarkt-opening-plans-current-v1/2000-01/opening-squad-preallocation.json'
    aid='opening-squad-preallocation-2000-01'
    descriptor=next(a for a in package['artifacts'] if a['id']==aid)
    if source.registry.sha256_file(pre)!=descriptor['sha256']:raise ValueError('current Hertha original source rows changed')
    index,sources=source.old.indexed_claims(source.pipeline.read_json_file(pre))
    authored=source.cohort_source(club,players,aid,index,sources)
    captures,_=source.old.roster.load_sources('2000-01')
    matches=[c for c in captures if source.old.selector_key(c)==source.old.selector_key(authored['selector'])]
    if len(matches)!=1:raise ValueError('Hertha needs one exact original season-squad capture')
    capture=matches[0];raw_proof=source.old.roster.SourceVerifier('2000-01').verify(capture)
    if raw_proof['status']!='raw-source-reparsed':raise ValueError('original period squad cannot be reparsed')
    raw=source.registry.ROOT/raw_proof['local_path']
    header=' '.join(raw.read_text().splitlines()[0].split())
    if (header!='= Hertha Berlin - German Bundesliga 2000/01'
            or len(players)!=25 or authored['selector']['club_name']!='Hertha Berlin'):
        raise ValueError('literal original season/club/full represented cohort differs')
    fixed_path=source.registry.ROOT/'seasons/2000-01/fixed-carrier-registry.json'
    fixed=source.pipeline.read_json_file(fixed_path)
    baseline=next(c for c in fixed['carriers'] if c['carrier_id']==421)['baseline_club']
    if source.old.builder._normalise_club_name(baseline['name'])!='herthaberlin':
        raise ValueError('source cohort is not original Hertha carrier')
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entry=next(e for e in source.IndexedFDIFile.from_bytes(eq).entries if e.record_id==421)
    payload=entry.decode_payload(eq);short,full,_=source.labels.prefix_parts(payload)
    marker=payload.find(bytes.fromhex('dd6361'));_,_,end=source._read_eq_inline_string(payload,marker+4)
    ground=source._read_eq_inline_string(payload,end)[0]
    holders,names=source.old._manager_graph(eq_path=base.game_path/'DBDAT/EQ98030.FDI',ent_path=base.game_path/'DBDAT/ENT98030.FDI')
    manager=next(m for m in package['managers'] if m['id']==club['manager_id'])
    if (short!=club['name'] or short!='1. FC Koln' or ground!=baseline['ground_name'] or ground!='Olympiastadion'
            or manager['carrier_id']!=baseline['active_manager_carrier_id'] or names[manager['carrier_id']]!='Röber'
            or manager['name']!='Röber' or [c['carrier_id'] for c in holders[manager['carrier_id']]]!=[421]):
        raise ValueError('actual current labels/retained original ground/coach exclusive owner differ')
    owned=source.owners.native_owners(eq)
    entries={e.record_id:e for e in source.IndexedFDIFile.from_bytes(jug).entries}
    for p in players:
        native=source.old.roster.native_player(entries[p['carrier_id']].decode_payload(jug),p['carrier_id'])
        if owned.get(p['carrier_id'])!={421} or source.old.roster.normalise(native['name'])!=source.old.roster.normalise(p['name']):
            raise ValueError('Hertha actual native person/exclusive owner differs')
    coach_input=external('hertha2000-roeber-original-career')
    coach=source.coach(source.originals.publisher_original(coach_input),'Jürgen Röber','Hertha BSC',2000)
    ground_input=external('hertha2000-official-stadium-history')
    page=BeautifulSoup(source.originals.publisher_original(ground_input),'lxml')
    text=' '.join(page.get_text(' ',strip=True).split())
    if ([h.get_text(' ',strip=True) for h in page.select('h1')]!=['Olympiastadion']
            or not all(s in text for s in ('Hertha BSC','seit 1963','1986 und 1988'))):
        raise ValueError('official stadium continuity/exceptions original differs')
    uefa_input=external('hertha2000-original-uefa-2002-departure')
    uefa=source.originals.publisher_original(uefa_input)
    uefa_text=' '.join(BeautifulSoup(uefa,'lxml').get_text(' ',strip=True).split())
    if b'2002-02-06' not in uefa or not all(s in uefa_text for s in ('Jürgen Röber','Hertha BSC Berlin','after six years in charge')):
        raise ValueError('original UEFA dated six-year Hertha coaching departure differs')
    if any(c['id']!=club['id'] and source.old.builder._normalise_club_name(c['name'])=='herthaberlin' for c in package['clubs']):
        raise ValueError('another Hertha label exists; paired duplicate adjudication required')
    retained(output,dict(utc=datetime.now(UTC).isoformat(),machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',season=base.season,release_id=base.release_id,
        manifest_sha256=base.manifest_sha256,carrier_id=421,native_before=short,native_full_before=full,
        confirmed_source_cohort_club='Hertha Berlin',original_registry=source.bind(fixed_path),
        preallocation=source.bind(pre),raw_period_squad=raw_proof,represented_native_people_verified=25,
        original_source_squad_people=len(capture['players']),native_coach='Röber',source_coach_full_name='Jürgen Röber',
        native_surname_alias_explicit_not_an_invented_first_name=True,dated_coach_spell=coach,
        coach_original=coach_input,UEFA_original=uefa_input,ground_original=ground_input,
        retained_ground=ground,ground_continuity='since1963 except1986–1988;2000 covered',
        proposed_fix='Restore source-authored original Hertha club short/full labels; preserve all native people/coach/ground/assets. Separate opening XI and historical kit-design work is not approved here.',
        complete_opening_XI_or_historical_kit_approval=False,native_writes=0,frozen_case_dispositions_changed=0))
    print(dict(confirmed_existing_native_Hertha_cohort_under_Koln_label=True,native_people=25,native_writes=0),flush=True)


if __name__=='__main__':main()
