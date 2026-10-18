"""Acquire original histories for IDs actually present in two OFK squad pages.

Two annual appearances alone do not prove opening membership. Histories are
captured separately so an independently dated entry/exit can bracket the first
2004 league fixture. No native/recipe edits or duplicate closures here.
"""
import re

from bs4 import BeautifulSoup

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_transfer_history_v1 as histories
from scripts.capture_stock_replacement_sources_20261010 import ROOT


def original_ids(year):
    path = ROOT / f'ofk-beograd-{year}.html'
    receipt = pipeline.read_json_file(ROOT / f'ofk-beograd-{year}.source.json')
    if (receipt['status'] != 'original-captured' or registry.sha256_file(path) != receipt['sha256']
            or receipt['url'] != f'https://www.transfermarkt.co.uk/ofk-belgrad/kader/verein/53/saison_id/{year}/plus/1'):
        raise ValueError('original OFK annual roster changed')
    page = BeautifulSoup(path.read_bytes(), 'html.parser')
    rows = {}
    for tr in page.select('table.items > tbody > tr'):
        links = tr.select('a[href*="/profil/spieler/"]')
        ids = {int(match.group(1)) for a in links
            if (match := re.search(r'/profil/spieler/(\d+)(?:/|$)', a.get('href', '')))}
        if not ids:
            continue
        if len(ids) != 1:
            raise ValueError('annual row identifies multiple published people')
        id = next(iter(ids))
        names = {a.get_text(' ', strip=True) for a in links if a.get_text(' ', strip=True)}
        if len(names) != 1 or id in rows:
            raise ValueError('annual player ID/name duplicated or ambiguous')
        rows[id] = next(iter(names))
    return rows, dict(path=registry.relative_workspace_path(path), sha256=receipt['sha256'], url=receipt['url'])


def main():
    previous, old_binding = original_ids(2003)
    target, target_binding = original_ids(2004)
    ids = set(previous) & set(target)
    if len(ids) != 20 or any(previous[id] != target[id] for id in ids):
        raise ValueError('published adjacent OFK roster intersection changed')
    cache = ROOT.parent / 'ofk-2004-history-originals'
    output = ROOT.parent / 'ofk-2004-intersection-history-v1.json'
    histories.capture_ids(ids, cache, output, [old_binding, target_binding],
        'Exact stable IDs appearing in original2003/04 and2004/05 OFK53 squad pages. Acquisition only; not opening ownership/first XI/native repair approval.')


if __name__ == '__main__':
    main()
