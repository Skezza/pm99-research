"""First league XI from the club's original published historical season record.

The annual appearance catalogue disambiguates printed initials only. It does
not establish opening ownership for reserves or supply DOB/roles/formation.
"""
import re

from bs4 import BeautifulSoup

URL='https://fkradnickinis.rs/2002-03-agonija-okoncana-ispadanjem/'
TITLE='2002/03: AGONIJA OKONČANA ISPADANJEM!'
XI=['Soldatović','Tucaković','D. Đorđević','Marković','B. Milenković',
    'Jovičić','B. Stamenković','S. Stojanović','V. Milenković','Mišeljić','Mihajlović']
LINE='RADNIČKI: Soldatović, Tucaković, D. Đorđević, Marković, B. Milenković, Jovičić, B. Stamenković, S. Stojanović (82′ Stanković), V. Milenković (70′ Ilić), Mišeljić, Mihajlović (58′ Jovanović).'
CATALOGUE='Alivodić Enver 4/0, Cenić Boban 25/1, Dimitrijević Dejan 15/0, Đokić Dušan 13/0, Đorđević Bojan 16/0, Đorđević Dragan 9/0, Đorđević Vladimir 17/0, Ilić Milinko 3/1, Jovanović Saša 21/1, Jovičić Lazar 17/1, Kovač Aleksandar 1/0, Kuzmanović Vojkan 27/4, Marković Milan 29/0, Mihajlović Goran 8/1, Milenković Bojan 11/0, Milenković Ivan 21/1, Milenković Vladimir 26/6, Milisavljević Nemanja 12/0, Miljković Dejan 17/2, Mišeljić Jovo 15/0, Petrović Nenad 7/0, Popović Novak 5/0, Ranđelović Marko 16/0, Soldatović Srđan 21/0, Stamenković Bojan 28/1, Stamenković Srđan 8/0, Stanković Aleksandar 19/0, Stefanović Stefan 9/0, Stojanović Jovica 20/0, Stojanović Saša 16/4, Terzić Pavle 9/0, Tucaković Kristijan 4/0, Vasić Ivan 3/0.'
COACH='Manojlović Tomislav (od 1-5. kola), Krstić Boban (od 6-17. kola), Milenković Zoran (od 18-34. kola).'
DATE='10.08.2002. Niš, Stadion Čair, 10.000 gledalaca. Sudija: G. Mihaljević (Podgorica).'


def expand_label(label,catalogue):
    initial=re.fullmatch(r'([A-ZŠĐČĆŽ])\. (.+)',label)
    matches=[p for p in catalogue if p['family_name']==(initial[2] if initial else label)
        and (initial is None or p['given_name'].startswith(initial[1]))]
    if len(matches)!=1:
        raise ValueError('original printed match label has no unique club-published full name')
    return dict(published_match_name=label,**matches[0])


def parse(raw,url=URL):
    if url!=URL or not 1000<=len(raw)<=2*1024**2:
        raise ValueError('unexpected official season URL or size')
    page=BeautifulSoup(raw,'html.parser')
    headings=[h.get_text(' ',strip=True) for h in page.select('h1')]
    if headings!=[TITLE]:
        raise ValueError('official season heading changed')
    text=re.sub(r'\s+',' ',page.get_text(' ',strip=True))
    first='1.KOLO: RADNIČKI (N) – C. ZVEZDA 0:0'
    following='2.KOLO: RADNIČKI (N) – ZEMUN 0:2 (0:1)'
    if any(text.count(v)!=1 for v in (first,following,DATE,LINE,CATALOGUE,COACH,'IGRALI U PRVENSTVU (33 igrača)')):
        raise ValueError('official first round/date/XI/catalogue/coach missing or ambiguous')
    if not text.index(first)<text.index(DATE)<text.index(LINE)<text.index(following):
        raise ValueError('official lineup is not bound to the first league round')
    catalogue=[]
    for entry in CATALOGUE.rstrip('.').split(', '):
        match=re.fullmatch(r'(\S+) (\S+) (\d+)/(\d+)',entry)
        if match is None:
            raise ValueError('invalid original surname-first annual catalogue')
        family,given,appearances,goals=match.groups()
        catalogue.append(dict(name=given+' '+family,given_name=given,family_name=family,
            season_appearances=int(appearances),season_goals=int(goals)))
    if len(catalogue)!=33 or len({p['name'] for p in catalogue})!=33:
        raise ValueError('official annual identity catalogue changed')
    starters=[expand_label(n,catalogue) for n in XI]
    substitutes=[dict(**expand_label(n,catalogue),minute=m)
        for n,m in [('Stanković',82),('Ilić',70),('Jovanović',58)]]
    if len({r['name'] for r in starters+substitutes})!=14:
        raise ValueError('first eleven and actual used substitutes repeat a person')
    return dict(season='2002-03',fixture_date='2002-08-10',club='Radnički Niš',
        opponent='Crvena Zvezda',result='0-0',ground='Stadion Čair',manager='Tomislav Manojlović',
        starting_xi=starters,used_substitutes=substitutes,annual_identity_catalogue=catalogue,
        unused_substitutes=None,formation=None,source_url=url,native_writes=0,publication_authorised=False,
        source_credit='FK Radnički Niš / club-published historical season record',
        limitations=['Club annual appearance catalogue supplies full names only, not opening reserve membership.',
            'Four additional positive opening reserves and independent biographies/roles remain required.',
            'Website labels the historical season-end date; contemporaneous publication date not independently proved.'])
