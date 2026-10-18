"""Source-bound August fallback, dated coach and explicitly declared facts."""
import copy
import json
import re
import tempfile
from pathlib import Path
from datetime import date
from bs4 import BeautifulSoup
from scripts import prepare_italchacao_2001_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_tachira_2014_original_people_v1 import source_rows

SCHEMA = 'pm99-private-original-italchacao2001-verified-inputs-v1'
SECONDARY_POLICY = 'original-period-facts-with-explicit-unknowns-and-physical-defaults-v1'


def secondary_facts(raw, desired, official_raw):
    page = BeautifulSoup(raw, 'html.parser')
    if page.title is None or page.title.get_text(' ', strip=True) != 'Deportivo Italchacao - Detailed squad 01/02 (Detailed view) | Transfermarkt':
        raise ValueError('secondary catalogue club/season changed')
    official = source.opening.flat(official_raw)
    if 'PLANTILLA APERTURA 2001/ APERTURA 2001 SQUAD' not in official:
        raise ValueError('dated original club squad is not Apertura2001')
    # Exact original names/countries, not a modern primary passport heuristic.
    period = {350368:('JOS� FASCIANA 1','VEN'), 140127:('DANIEL DIEZ 3','VEN'),
        147691:('GREGORY LUZARDO 13','VEN'), 140144:('LEOPOLDO JIM�NEZ 14','VEN'),
        824124:('ARSENIO SANTEUGINI 16','VEN'), 347836:('H�CTOR BIDOGLIO -','VEN'),
        123498:('GIOVANNY P�REZ 23','VEN'), 72532:('RAFAEL CASTELL�N 9','VEN'),
        77943:('JOS� LUIS VALLENILLA PACHECO -','VEN'), 351335:('WILLIAM GONZ�LEZ -','VEN'),
        954596:('MODESTO GONZ�LEZ -','VEN'), 172115:('CLAUDIO SILVA, CARIOCA -','BRA')}
    for label, country in period.values():
        if official.count(label+' '+{'VEN':'Venezuela','BRA':'Brasil'}[country]) != 1:
            raise ValueError('original period nationality changed or ambiguous')
    selected = {r['source_person']['source_player_id']:r for r in desired}
    facts = {}
    for tr in page.select('table.items > tbody > tr'):
        ids = {int(m[1]) for a in tr.select('a[href*="/profil/spieler/"]')
            if (m := re.search(r'/profil/spieler/(\d+)', a.get('href','')))}
        if len(ids) != 1 or next(iter(ids)) not in selected:
            continue
        id = next(iter(ids)); cells = tr.find_all('td', recursive=False)
        if id in facts or len(cells) != 10:
            raise ValueError('ambiguous original secondary identity row')
        match = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4}) \(\d+\)', cells[2].get_text(' ',strip=True))
        if match is None or date(int(match[3]),int(match[2]),int(match[1])).isoformat() != selected[id]['source_person']['birth_date']:
            raise ValueError('secondary original identity birthday conflicts')
        flags = cells[3].select('img.flaggenrahmen')
        nation = {'Venezuela':'VEN','Brazil':'BRA','Argentina':'ARG','Italy':'ITA','Spain':'ESP'}.get(flags[0].get('title') if flags else None)
        if nation is None:
            raise ValueError('unmapped original country')
        source_country = nation
        if id in period: nation = period[id][1]
        height_text = cells[5].get_text(' ',strip=True)
        height_match = re.fullmatch(r'(\d),(\d{2})m',height_text)
        if height_match: height = int(height_match[1])*100+int(height_match[2])
        elif height_text in ('-', '', 'N/A'): height = None
        else: raise ValueError('unknown original secondary height unit')
        if height is not None and not 140 <= height <= 220:
            raise ValueError('implausible original height')
        facts[id] = dict(nationality=nation, height_cm=height, weight_kg=None,
            nationality_basis='original-Apertura2001-club-squad' if id in period else 'declared-target-season-catalogue-flag',
            country_disagreement=dict(period_selected=nation, catalogue_primary=source_country) if nation != source_country else None,
            height_basis='original-target-season-catalogue-centimetres' if height else 'unpublished',
            weight_basis='unpublished')
    for id in selected.keys()-facts.keys():
        facts[id] = dict(nationality=period[id][1] if id in period else 'XXX', height_cm=None, weight_kg=None,
            nationality_basis='original-Apertura2001-club-squad' if id in period else 'unpublished-explicit-XXX',
            country_disagreement=None, height_basis='unpublished', weight_basis='unpublished')
    return facts


def prepare(output, baseline_release_id=None):
    if output.exists(): raise ValueError('verified source inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-italchacao-original-') as temporary:
        proposal = source.prepare(Path(temporary)/'allocation.json', baseline_release_id)
    _, annual, annual_binding = source_rows('italchacao-2001-original-linked-identity-catalogue')
    _, official, official_binding = source_rows('italchacao-2001-original-official-opening-squad')
    _, club, club_binding = source_rows('italchacao-2001-original-official-club-facts')
    text = BeautifulSoup(club,'html.parser').get_text(' ',strip=True)
    if ('Entrenador: Raúl Cavallieri' not in text or 'Olímpico de la UCV - Caracas' not in text
            or '2000/2001 - Site powered and designed by Manuel De Oliveira' not in text):
        raise ValueError('original club coach/ground/period missing')
    facts = secondary_facts(annual, proposal['desired_people'], official)
    for row in proposal['desired_people']:
        id = row['source_person']['source_player_id']; fact = facts[id]
        source_values = {key:fact[key] for key in ('nationality','height_cm','weight_kg')}
        # Loader randomises unknown physical sentinels; deterministic declared
        # defaults are estimates, never an alleged source fact.
        if source_values['height_cm'] is None:
            source_values['height_cm'] = {'G':185,'D':180,'M':178,'F':180}[row['source_player']['position']]
            fact['height_fallback'] = dict(value=source_values['height_cm'], historically_sourced=False)
        source_values['weight_kg'] = {'G':80,'D':76,'M':74,'F':76}[row['source_player']['position']]
        fact['weight_fallback'] = dict(value=source_values['weight_kg'], historically_sourced=False)
        row['source_player'].update(source_values)
        row['secondary_facts_status'] = copy.deepcopy(fact)
    desired = {r['source_person']['source_player_id']:r for r in proposal['desired_people']}
    for row in proposal['allocation']:
        row['replacement'] = desired[row['replacement']['source_person']['source_player_id']]
    proposal.update(schema_version=SCHEMA,
        source_title='OriginalAugust2001 Italchacao cup XI and friendly additions; league XI unavailable',
        secondary_fact_review=dict(policy=SECONDARY_POLICY, facts=facts,
            original_bindings=[annual_binding,official_binding],
            native_fallbacks=['Unpublished height/weight explicitly estimated, not historically certified.',
                'Unknown nationality remains XXX; no current passport copied.', 'No inherited portraits or sourced August shirt-number claim.']),
        dated_manager_ground=dict(date='2001-08-08',source_club_id=proposal['transfermarkt_club_id'],
            manager='Raúl Cavallieri',ground='Olimpico de la UCV',
            ground_source=dict(binding=club_binding, published='Olímpico de la UCV - Caracas',
                limitation='Original2000/2001 technical page, not a first home fixture certificate.')))
    proposal['original_bindings'].extend([official_binding,club_binding])
    proposal = json.loads(pipeline.canonical_json_bytes(proposal))
    pipeline.write_canonical_json(output, proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'], report_binding=proposal['original_bindings'][0],
        manager_native_names=dict(surname='Cavallieri',display_name='Cavallieri'),
        manager_person_id='manager-original-club-august2001-raul-cavallieri',
        artifact_id='italchacao-original-manager-ground-2001', relative_path='italchacao-original-opening-2001.html')


if __name__ == '__main__':
    result = prepare(source.ROOT/'italchacao-2001-verified-source-inputs-v1.json')
    print(dict(people=len(result['desired_people']),native_writes=0),flush=True)
