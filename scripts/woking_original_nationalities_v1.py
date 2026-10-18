"""Recover literal nationality rows from sixteen already bound biographies."""
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_compiler_v2 as compiler
from scripts import capture_soccerbase_august_squads_v1 as biographies
from scripts import season_quality_only_delta_v1 as delta

SOURCE=registry.ROOT/'.local/consolidated-audit-20261009/woking-owned-opening-v1/opening-ownership-plan.json'
COUNTRIES={'England':'ENG','New Zealand':'NZL','Jamaica':'JAM','France':'FRA',
    'Scotland':'SCO','Dominica':'DMA','Nigeria':'NGA'}


def nationality(raw):
    page=BeautifulSoup(raw,'lxml');headers=[h for h in page.select('th') if h.get_text(strip=True)=='Nationality']
    if len(headers)!=1:raise ValueError('one literal original nationality row required')
    cells=headers[0].parent.select('td')
    if len(cells)!=1:raise ValueError('ambiguous nationality cell')
    text=cells[0].get_text(' ',strip=True)
    if text not in COUNTRIES:raise ValueError('unmapped/ambiguous original nationality')
    return COUNTRIES[text]


def rows(base):
    if base.season!='2003-04':raise ValueError('Woking nationality source is2003 only')
    source=pipeline.read_json_file(SOURCE);package=pipeline.read_json_file(base.package_path)
    expected=[a for a in package['artifacts'] if a['id']=='sourced-woking-owned-opening-2003-04']
    if len(expected)!=1 or registry.sha256_file(SOURCE)!=expected[0]['sha256']:
        raise ValueError('Woking cohort source is not the immutable recipe artifact')
    people={p['source_name']:p for p in package['players'] if p['club_id']=='club-3321'}
    if len(people)!=16:raise ValueError('Woking source cohort changed')
    countries=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    updates=[];bindings=[dict(path=registry.relative_workspace_path(SOURCE),sha256=registry.sha256_file(SOURCE))]
    for wanted in source['proposal']['desired_people']:
        path=registry.ROOT/wanted['raw_evidence']['local_path']
        if registry.sha256_file(path)!=wanted['raw_evidence']['source_sha256']:raise ValueError('original biography changed')
        raw=path.read_bytes();person=biographies.player_profile(raw,fallback_name='',fallback_position='?')
        old=people[wanted['source_player']['name']]
        same_dob=person['birth_date']==old['facts']['birth_date']
        # Liam's original biography publishes no DOB. His already verified
        # opening-layer numerical identity/annual DOB bridge is immutable;
        # the present operation reads only that same actor's country cell.
        established_liam=(person['name']=='Liam Cockerill' and person['birth_date'] is None
            and wanted['source_person']['source_player_id']==1354651
            and wanted['source_player']['birth_date']==old['facts']['birth_date']=='1984-06-02'
            and path.name=='35807.html')
        if person['name']!=old['source_name'] or not (same_dob or established_liam):
            raise ValueError('nationality biography names another exact person')
        code=nationality(raw);native=compiler._country_code(code,countries)
        if native==countries['XXX']:raise ValueError('original nationality is not representable')
        if old['facts']['nationality']!='XXX':raise ValueError('Woking nationality preimage is not the declared gap')
        binding=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path));bindings.append(binding)
        updates.append(dict(carrier_id=old['carrier_id'],before=old,nationality=code,native_country_code=native,
            source=binding,scope='Literal full-name/DOB-bound biography nationality; not a claim of target-season international caps. Dominica DMA is not Dominican Republic DOM.'))
    if len(updates)!=16:raise ValueError('incomplete Woking nationality repair')
    return sorted(updates,key=lambda r:r['carrier_id']),bindings
