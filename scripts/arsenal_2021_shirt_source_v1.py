"""Replay20 original matchday numbers plus five target-season reserve rows."""
import re
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_opening_order_repair_v1 as ownership
from scripts import arsenal_2021_opening_transaction_source_v1 as actors
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.capture_arsenal_shirt_source_20261016 import KEY,URL,validate
from scripts.build_arsenal_owned_opening_20261016 import ROOT as ACTORS_ROOT,RELEASE as ACTORS_RELEASE


def matchday(raw,club_id=11):
    page=BeautifulSoup(raw,'html.parser');sides=[]
    for side in page.select('.large-6'):
        ids={int(m[1]) for a in side.select('a[href]')
            if (m:=re.search(r'/startseite/verein/(\d+)(?:/|$)',a['href']))}
        if ids=={club_id}:sides.append(side)
    if len(sides)!=1:raise ValueError('shirt numbers need exactly one numeric original-club side')
    result={};groups=[]
    for selector,count in (('.formation-player-container',11),('table.ersatzbank tr',9)):
        selected={}
        for node in sides[0].select(selector):
            ids={int(m[1]) for a in node.select('a[href]')
                if (m:=re.search(r'/profil/spieler/(\d+)(?:/|$)',a['href']))}
            if not ids:continue  # Coach row is not a squad player.
            nums=[n.get_text(strip=True) for n in node.select('.tm-shirt-number')]
            if len(ids)!=1 or len(nums)!=1 or not re.fullmatch(r'[1-9][0-9]?',nums[0]):
                raise ValueError('one explicit shirt number and numeric person required')
            pid=next(iter(ids))
            if pid in result or pid in selected:raise ValueError('source repeats a shirt-number actor')
            selected[pid]=int(nums[0])
        if len(selected)!=count:raise ValueError('complete original eleven/nine bench shirt numbers required')
        result.update(selected);groups.append(list(selected))
    if len(set(result.values()))!=20:raise ValueError('original matchday repeats a shirt number')
    return result,groups


def reserve_numbers(raw,people,aliases):
    validate(raw,URL);page=BeautifulSoup(raw,'html.parser');tables=[]
    for table in page.select('table.wikitable'):
        first=table.find('tr')
        headers=[c.get_text(' ',strip=True) for c in first.find_all(['td','th'],recursive=False)] if first else []
        if headers[:2]==['No.','Player'] and 'Date of birth (age)' in headers:tables.append((table,headers))
    if len(tables)!=1:raise ValueError('one original target-season squad number/DOB table required')
    table,headers=tables[0];found={}
    for row in table.select('tr'):
        cells=row.find_all(['td','th'],recursive=False)
        if len(cells)<len(headers):continue
        number=cells[0].get_text(' ',strip=True);a=cells[1].find('a')
        if not re.fullmatch(r'[1-9][0-9]?',number) or a is None:continue
        name=roster.normalise(a.get_text(' ',strip=True))
        dates=re.findall(r'\(\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*\)',
            cells[headers.index('Date of birth (age)')].get_text(' ',strip=True))
        for pid,person in people.items():
            if name not in aliases[pid]|{roster.normalise(person['name'])}:continue
            if dates!=[person['birth_date']]:raise ValueError('season-shirt row conflicts with original person birthday')
            if pid in found:raise ValueError('season-shirt source repeats an original identity')
            found[pid]=dict(number=int(number),source_name=a.get_text(' ',strip=True),birth_date=dates[0])
    if set(found)!=set(people):raise ValueError('not all five positively owned August reserves have sourced numbers')
    return found


def prepare(base):
    if base.season!='2021-22' or base.release_id!=ACTORS_RELEASE:
        raise ValueError('shirt pilot must preserve the exact corrected Arsenal actor game')
    plan=pipeline.read_json_file(ACTORS_ROOT/'opening-ownership-plan.json')
    package=pipeline.read_json_file(base.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==309)
    if club['name']!='Arsenal':raise ValueError('shirt target club changed')
    admitted=plan['assignment']['source_admission'];desired=admitted['desired_people']
    capture_path=registry.ROOT/'.local/transfermarkt-opening-plans-current-v1/2021-22/opening-lineups.json'
    capture=pipeline.read_json_file(capture_path)
    raw,proof=opening.verified_page(capture_path.parent/'cache',capture['source']['cache_files'],
        'https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/3583476')
    match,groups=matchday(raw)
    if set(match)!={p['source_person']['source_player_id'] for p in desired[:20]}:
        raise ValueError('source match numbers belong to other starting/bench actors')
    _,wiki_raw,wiki_binding=source_rows(KEY)
    _,_,aliases=actors.published_index()
    reserve_people={p['source_person']['source_player_id']:p['source_person'] for p in desired[20:]}
    reserves=reserve_numbers(wiki_raw,reserve_people,aliases)
    numbers=dict(match);numbers.update({pid:r['number'] for pid,r in reserves.items()})
    if len(numbers)!=25 or len(set(numbers.values()))!=25:raise ValueError('complete Arsenal25 must have unique sourced shirt numbers')
    mapping=dict(plan['assignment']['retained_Arsenal'])
    mapping.update({r['replacement']['source_person']['source_player_id']:r['carrier_id']
        for r in plan['assignment']['replacements'] if r['before_recipe']['club_id']=='english-club-309'})
    if set(mapping)!=set(numbers):raise ValueError('shirt source actors do not reproduce corrected Arsenal25')
    players={p['carrier_id']:p for p in package['players']}
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    owners=ownership.native_owners(eq);entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    records=ownership.tactics.payloads(eq)
    if records[309][0x29]!=0:raise ValueError('shirt writes require the independently proven mode0 club')
    updates=[]
    for pid,carrier in sorted(mapping.items(),key=lambda item:item[1]):
        player=players[carrier];raw=entries[carrier].decode_payload(jug)
        native=read_initial_order(raw)
        if (owners.get(carrier)!={309} or player['club_id']!=club['id']
            or raw[2:5]!=bytes.fromhex('dd6361') or native.name.casefold()!=player['name'].casefold()):
            raise ValueError('shirt target lacks exact native identity/exclusive full-layout mode0 ownership')
        updates.append(dict(carrier_id=carrier,source_person_id=pid,player_id=player['id'],
            before_player=player,native_name=native.name,before_number=raw[7]^0x61,number=numbers[pid],
            source_kind='exact-first-league-numeric-player' if pid in match else 'target-season-number-and-original-DOB'))
    return dict(updates=updates,source_bindings=[actors.bound(ACTORS_ROOT/'opening-ownership-plan.json'),
        actors.bound(capture_path),proof,wiki_binding],reserve_rows={str(pid):row for pid,row in reserves.items()},
        original_match_groups=groups,scope='25 full-layout Arsenal shirt header bytes and explicit shirt facts only; no identities, skills, roles, order, tactics, managers, kits, portraits or other game files.')


if __name__=='__main__':
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    base=registry.load_registered_release('2021-22',ACTORS_RELEASE);doc=prepare(base)
    target=registry.ROOT/'.local/consolidated-audit-20261009/arsenal-shirts-2021-v1'
    target.mkdir(parents=True,exist_ok=True)
    retained(target/'source-number-admission.json',doc)
    print(dict(sourced_Arsenal_numbers=25,actual_native_numbers_to_change=sum(r['before_number']!=r['number'] for r in doc['updates']),native_writes=0),flush=True)
