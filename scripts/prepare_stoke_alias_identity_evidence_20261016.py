"""Replay original identity/tenure evidence; do not write any season recipe.

The same person can have different transliterations and false recipe dates.
Conversely, a published match bench is not allowed to override contradictory
dated career evidence. Native replacement plans follow the manager rollout.
"""
from datetime import datetime, date, UTC
import re
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts.audit_shtanyuk_runtime_aliases_20261016 import ROOT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts import season_remaining_manager_tenures_20261016 as manager


def original(folder,key,url):
    receipt=folder/(key+'.json')
    row=pipeline.read_json_file(receipt)
    raw=registry.ROOT/row['raw_path']
    if (row['status']!='public-original-captured' or row['url']!=url
            or raw!=folder/(key+'.html') or registry.sha256_file(raw)!=row['raw_sha256']):
        raise ValueError('original identity source URL/body/receipt changed')
    return BeautifulSoup(raw.read_bytes(),'html.parser'),dict(path=registry.relative_workspace_path(raw),
        sha256=row['raw_sha256'],url=url,receipt_path=registry.relative_workspace_path(receipt),
        receipt_sha256=registry.sha256_file(receipt))


def unique_field(page,label):
    found=[]
    for tr in page.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
        if len(cells)==2 and cells[0]==label:
            found.append(cells[1])
    if len(found)!=1:
        raise ValueError('one explicit original identity field required: '+label)
    return found[0]


def soccerbase(page,name):
    if [h.get_text(' ',strip=True) for h in page.find_all('h1')]!=[name]:
        raise ValueError('original numerical Soccerbase person heading differs')
    matches=re.findall(r'\bBorn\s+(\d{2} [A-Za-z]{3}, \d{4})\b',page.get_text(' ',strip=True))
    if len(matches)!=1:
        raise ValueError('one explicit Soccerbase birthday required')
    birthday=datetime.strptime(matches[0],'%d %b, %Y').date().isoformat()
    rows=[]
    for tr in page.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all('td')]
        if len(cells)>=4 and cells[0]=='Stoke':
            rows.append(dict(club='Stoke City',joined=datetime.strptime(cells[1],'%d %b, %y').date().isoformat(),
                left=datetime.strptime(cells[2],'%d %b, %y').date().isoformat(),contract_kind=cells[3]))
    if len(rows)!=1:
        raise ValueError('one explicitly dated Stoke tenure required')
    return dict(name=name,birth_date=birthday,Stoke=rows[0])


def annual_commons():
    captured,bindings=roster.load_sources('2001-02')
    rows=[r for r in captured if roster.source_group(r['country_catalog'])=='england'
        and r['club_name']=='Stoke City' and r['source_path'].endswith('.txt')]
    if len(rows)!=1:
        raise ValueError('one original2001 Stoke annual source required')
    annual=rows[0]; proof=roster.SourceVerifier('2001-02').verify(annual)
    if proof['status']!='raw-source-reparsed':
        raise ValueError('original2001 annual source did not independently replay')
    people=[p for p in annual['players'] if p['name']=='Kris Commons']
    if len(people)!=1:
        raise ValueError('one independently parsed Commons annual row required')
    return dict(person=people[0],original=proof,captures=[dict(path=b['path'],sha256=b['sha256']) for b in bindings],
        annual_is_not_opening_tenure_proof=True)


def prepare():
    """Reparse every original without fetching again or rewriting evidence."""
    root=ROOT/'originals'; reserve=ROOT/'reserve-originals'
    page,primary=original(root,'identity-career-11v11','https://www.11v11.com/players/sergei-shtaniuk-12011/')
    if [h.get_text(' ',strip=True) for h in page.find_all('h1')]!=['Sergei Shtaniuk']:
        raise ValueError('original11v11 numerical identity differs')
    birthday=datetime.strptime(unique_field(page,'Date of birth'),'%d %B %Y').date().isoformat()
    nationality=unique_field(page,'Nationality')
    if nationality!='Belarussian':
        raise ValueError('original explicit nationality differs')
    tables=[t for t in page.find_all('table') if [c.get_text(' ',strip=True) for c in t.find('tr').find_all(['td','th'])]
        ==['Team','Joined','Left','Loan / Trialist']]
    if len(tables)!=1:
        raise ValueError('one original career table required')
    tenures=[]
    for tr in tables[0].find_all('tr')[1:]:
        cells=[c.get_text(' ',strip=True) for c in tr.find_all('td')]
        if cells[0]=='Stoke City' and cells[3]=='':
            tenures.append(dict(joined=datetime.strptime(cells[1],'%d %b %Y').date().isoformat(),
                left=datetime.strptime(cells[2],'%d %b %Y').date().isoformat()))
    if len(tenures)!=1:
        raise ValueError('one non-trial Stoke playing tenure required')
    rfs,rfs_binding=original(root,'official-rfs','https://www.rfs.ru/cup/players/shtaniuk-siarhei')
    match=re.search(r'Дата рождения\s+(\d{2}\.\d{2}\.\d{4})',rfs.get_text(' ',strip=True))
    if match is None or 'Сергей Штанюк' not in rfs.get_text(' ',strip=True):
        raise ValueError('original federation person/date identity missing')
    rfs_date=datetime.strptime(match[1],'%d.%m.%Y').date().isoformat()
    nft,nft_binding=original(root,'national-football-teams','https://www.national-football-teams.com/player/665/Syarhey_Shtanyuk.html')
    heading=' '.join(h.get_text(' ',strip=True) for h in nft.find_all('h1'))
    match=re.search(r'Day of Birth\s+(\d{4}-\d{2}-\d{2})',nft.get_text(' ',strip=True))
    if 'Syarhey Shtanyuk' not in heading or 'Сергей Петрович Штанюк' not in heading or match is None:
        raise ValueError('original Latin/Cyrillic alias bridge or birthday absent')
    if len({birthday,rfs_date,date.fromisoformat(match[1]).isoformat()})!=1:
        raise ValueError('independent original birthday sources disagree')
    if not all(tenures[0]['joined']<=f'{year}-08-01'<tenures[0]['left'] for year in (2001,2002)):
        raise ValueError('retained actor lacks the actual target opening tenure')
    page,commons_binding=original(reserve,'commons-soccerbase','https://www.soccerbase.com/players/player.sd?player_id=28633')
    commons=soccerbase(page,'Kris Commons'); annual=annual_commons()
    if (commons['birth_date']!=annual['person']['birth_date']
            or not commons['Stoke']['joined']<='2001-08-01'<commons['Stoke']['left']):
        raise ValueError('Commons annual identity or positive opening reserve tenure disagrees')
    page,wilson_binding=original(reserve,'wilson-conflicting-opening-soccerbase','https://www.soccerbase.com/players/player.sd?player_id=13854')
    wilson=soccerbase(page,'Mark Wilson')
    report=pipeline.read_json_file(manager.prior.old.REVIEWS/'2002-03/opening-review.json')
    evidence=next(c['evidence'] for c in report['clubs'] if c['club']=='Stoke City')
    if not (evidence['date']=='2002-08-10' and evidence['substitutes'].get('3327')=='Mark Wilson'
            and wilson['Stoke']['joined']>evidence['date']):
        raise ValueError('explicit dated bench/career conflict changed; do not silently reclassify')
    return dict(machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',native_writes=0,recipe_writes=0,cases_closed=0,
        retained_person=dict(published_names=['Sergei Shtaniuk','Syarhey Shtanyuk','Сергей Петрович Штанюк'],
            birth_date=birthday,nationality='BLR',positive_Stoke_tenure=tenures[0],
            originals=[primary,rfs_binding,nft_binding]),
        positive_2001_reserve=dict(**commons,annual=annual,original=commons_binding),
        rejected_2002_reserve=dict(**wilson,original=wilson_binding,original_bench_claim=evidence,
            reason='March2003 loan cannot establish August2002 opening ownership; contradictory bench label is not authority'),
        remaining='Admit Vandeurzen opening/career facts, check all6 native actors and paired owners, produce actual bounded replacements only after current manager rollout. No duplicate cases closed by source admission alone.')


def main():
    output=ROOT/'identity-and-reserve-source-admission.json'
    if output.exists():
        raise ValueError('completed original identity admission must not repeat')
    result=prepare()
    retained(output,dict(utc=datetime.now(UTC).isoformat(),**result))
    print(dict(original_identity_sources_agree=True,birth_date=result['retained_person']['birth_date'],positive_2001_reserve='Kris Commons',
        rejected_2002_reserve='Mark Wilson',native_writes=0,cases_closed=0),flush=True)


if __name__=='__main__':
    main()
