"""Join dated club-press names to original published IDs; acquire18 biographies.

Annual calendar pages supply only explicit identity links here, not opening
membership or permission to copy present-day countries/positions/portraits.
"""
import re
from bs4 import BeautifulSoup
from scripts import tachira_2014_original_opening_v1 as opening
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts.capture_source_bound_people_v1 import capture_ids


def source_rows(key):
    path = ROOT / (key + '.html')
    receipt = pipeline.read_json_file(ROOT / (key + '.source.json'))
    if receipt['status'] != 'original-captured' or registry.sha256_file(path) != receipt['sha256']:
        raise ValueError('original identity-link page missing or changed')
    return path, path.read_bytes(), dict(path=registry.relative_workspace_path(path), sha256=receipt['sha256'])


def join():
    path, raw, binding = source_rows('tachira-2014-original-club-press-opening-validated')
    actual = opening.parse(raw)
    annual_path, annual, annual_binding = source_rows('tachira-2014')
    page = BeautifulSoup(annual, 'html.parser')
    if page.title is None or 'Deportivo Táchira - Detailed squad 2015' not in page.title.get_text():
        raise ValueError('identity-link catalogue identifies another club')
    ids = {}
    for row in page.select('table.items > tbody > tr'):
        links = {a.get('href'): a.get_text(' ', strip=True) for a in row.select('a[href*="/profil/spieler/"]')}
        if not links:
            continue
        if len(links) != 1:
            raise ValueError('annual identity row ambiguous')
        href, name = next(iter(links.items()))
        id = int(re.search(r'/profil/spieler/(\d+)', href)[1])
        key = roster.normalise(name)
        if key in ids:
            raise ValueError('two publisher people share one match-name identity link')
        ids[key] = id
    profile_path, profile_raw, profile_binding = source_rows('tancredi-original-profile')
    profile = BeautifulSoup(profile_raw, 'html.parser')
    full_names = [p.get_text(' ', strip=True) for p in profile.select('.info-table__content--bold')]
    canonical = profile.select_one('link[rel="canonical"]')
    if (canonical is None or not re.search(r'/profil/spieler/76530(?:/|$)', canonical.get('href', ''))
            or 'José Luis Tancredi Malatez' not in full_names
            or not any(v.startswith('14/02/1983 ') for v in full_names)):
        raise ValueError('original full Tancredi biography/ID not confirmed')
    # The actual press label includes the full two given names, not an invented
    # initial expansion. The original profile explicitly publishes that person.
    ids[roster.normalise('José Luis Tancredi')] = 76530
    names = actual['starting_xi'] + [p['name'] for p in actual['used_substitutes']] + actual['unused_substitutes']
    matched = [dict(published_match_name=n, source_player_id=ids[roster.normalise(n)]) for n in names]
    if len(matched) != 18 or len({p['source_player_id'] for p in matched}) != 18:
        raise ValueError('opening18 lacks distinct original publisher identities')
    return actual, matched, [binding, annual_binding, profile_binding]


def capture():
    actual, matched, inputs = join()
    output = ROOT.parent / 'tachira-2014-original-person-identities-v1.json'
    document = capture_ids([p['source_player_id'] for p in matched],
        ROOT.parent / 'tachira-2014-original-people', output, inputs)
    if any(batch['gaps'] for batch in document['batches']):
        raise ValueError('original biography gaps require review; retained acquisition not native approved')
    ledger = ROOT.parent / 'tachira-2014-original18-identity-links-v1.json'
    pipeline.write_canonical_json(ledger, dict(season=actual['season'], original_match=actual,
        original_bindings=inputs, matched_people=matched,
        people_document=dict(path=registry.relative_workspace_path(output), sha256=registry.sha256_file(output)),
        identity_catalogue_period='calendar2015; explicit identity links ONLY, no membership/secondary facts',
        native_writes=0, publication_authorised=False))
    return document


if __name__ == '__main__':
    result = capture()
    print(dict(confirmed_original_people=sum(len(b['people']) for b in result['batches']), native_writes=0), flush=True)
