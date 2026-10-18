"""Reparse the actual 2015 Becej preview and first match, never infer identities.

This is source preparation, not a native repair or historical clearance. The
paper publishes a full preseason roster but its match sheet has an ambiguous
Culum and a misspelled surname. Keep those gaps explicit instead of selecting
the first surname match or treating a later match as the opening XI.
"""
import re
from datetime import date

from bs4 import BeautifulSoup

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_stock_replacement_sources_20261010 import ROOT


def article(payload):
    page = BeautifulSoup(payload, 'html.parser')
    articles = page.select('article')
    if len(articles) != 1:
        raise ValueError('one original newspaper article required')
    node = articles[0]
    content = node.select('.entry-content')
    published = node.select('time[datetime]')
    if len(content) != 1 or not published:
        raise ValueError('article body and original publication date required')
    day = date.fromisoformat(published[0]['datetime'][:10])
    return node, content[0], day


def preseason(payload):
    _, body, published = article(payload)
    text = body.get_text(' ', strip=True)
    if published != date(2015, 8, 14) or '2015/16.' not in text or 'OFK Bečej 1918' not in text:
        raise ValueError('original preview does not identify target season/club/date')
    paragraphs = [p.get_text(' ', strip=True) for p in body.select('p')
        if 'na raspolaganju će imati sledeće igrače:' in p.get_text(' ', strip=True)]
    if len(paragraphs) != 1:
        raise ValueError('one explicit complete preseason roster paragraph required')
    match = re.search(r'šef stručnog štaba (.+?) na raspolaganju će imati sledeće igrače:\s*(.+?)\.\s*$', paragraphs[0])
    if match is None:
        raise ValueError('source does not publish a complete coach/roster statement')
    manager, names = match.group(1), [n.strip() for n in match.group(2).split(',')]
    if (len(names) != 25 or len(set(names)) != 25
            or any(len(n.split()) != 2 for n in names)
            or manager != 'Dalibor Novčić'):
        raise ValueError('published complete roster or coach changed; inspect original')
    # Read only the first-round fixture section, not a later round/current list.
    if '1. kolo:' not in text or 'Subota 15. 08. 17 č Radnički (S) – Bečej 1918' not in text:
        raise ValueError('target first fixture is not published in the preview')
    return dict(club='OFK Bečej 1918', season='2015-16', published=published.isoformat(),
        opening_date='2015-08-15', opening_opponent='Radnički Sombor', manager=manager,
        players=[dict(name=name, position='G' if name in ('Davor Dovedan', 'Tibor Ereg') else None,
            birth_date=None, nationality=None, height_cm=None, weight_kg=None,
            unresolved_fields=['birth_date', 'nationality', 'height_cm', 'weight_kg'] +
                ([] if name in ('Davor Dovedan', 'Tibor Ereg') else ['primary_position'])) for name in names],
        proposed_not_registered_player='Nemanja Perendić',
        scope='Complete explicit opening squad/dated coach only. Full first XI and secondary facts not approved.')


def resolve_label(label, roster):
    """Exact surname plus optional initial; never fuzzy-match or choose namesakes."""
    match = re.fullmatch(r'(?:(\w)\.\s*)?([\w-]+)', label)
    if match is None:
        raise ValueError('unsupported original match-sheet name label')
    initial, family = match.groups()
    matches = [row['name'] for row in roster if row['name'].split()[-1] == family
        and (initial is None or row['name'][0] == initial)]
    return dict(original_label=label, candidate_names=matches,
        full_name=matches[0] if len(matches) == 1 else None,
        state='exact-unique-published-roster-label' if len(matches) == 1 else 'unresolved-original-label')


def first_fixture(payload, roster):
    node, body, published = article(payload)
    title = node.select_one('h1')
    if (published != date(2015, 8, 20) or title is None
            or '1. kolo:' not in title.get_text(' ', strip=True)):
        raise ValueError('not the original first-round dated match report')
    paragraphs = [p.get_text(' ', strip=True) for p in body.select('p')
        if p.get_text(' ', strip=True).startswith('Bečej 1918:')]
    if len(paragraphs) != 1:
        raise ValueError('one named first-fixture squad paragraph required')
    raw = paragraphs[0].removeprefix('Bečej 1918:').strip().removesuffix('.')
    starters, used_substitutes = [], []
    for row in raw.split(','):
        match = re.fullmatch(r'\s*([^()]+?)(?:\s*\(([^()]+)\))?\s*', row)
        if match is None:
            raise ValueError('ambiguous first-fixture player/substitution structure')
        starters.append(resolve_label(match.group(1).strip(), roster))
        if match.group(2):
            used_substitutes.append(resolve_label(match.group(2).strip(), roster))
    if len(starters) != 11 or len(used_substitutes) != 3:
        raise ValueError('published first-fixture XI/substitutions changed')
    return dict(published=published.isoformat(), first_round=True, starting_xi=starters,
        appeared_substitutes=used_substitutes, full_unused_bench_published=False,
        unresolved_labels=[r for r in starters + used_substitutes if r['full_name'] is None],
        first_xi_identity_approved=all(r['full_name'] is not None for r in starters),
        scope='Used substitutes are not the complete matchday bench. No formation/primary outfield position inferred.')


def main():
    sources = {}
    originals = {}
    for key in ('becej-2015-opening-roster', 'becej-2015-first-fixture'):
        path, receipt = ROOT / (key + '.html'), ROOT / (key + '.source.json')
        binding = pipeline.read_json_file(receipt)
        if binding['status'] != 'original-captured' or registry.sha256_file(path) != binding['sha256']:
            raise ValueError('retained original newspaper evidence changed')
        originals[key] = path.read_bytes()
        sources[key] = dict(path=registry.relative_workspace_path(path), sha256=binding['sha256'], url=binding['url'])
    preview = preseason(originals['becej-2015-opening-roster'])
    opening = first_fixture(originals['becej-2015-first-fixture'], preview['players'])
    result = dict(schema_version='pm99-original-local-newspaper-opening-review-v1',
        season='2015-16', club_carrier_id=706, originals=sources,
        preseason=preview, first_fixture=opening, native_writes=0, closed_duplicate_cases=0,
        source_gap_recovered='Complete25 opening squad and dated Novcic; not yet a native candidate or release.',
        outstanding=['Culum is ambiguous between Bojan/Nikola; no first-match identity guessed.',
            'Dabizjevic match-sheet spelling needs independent person/alias evidence.',
            'Outfield primary positions and biographies require published person evidence.',
            'Full fixed18-carrier native assignment, manager/assets/readback/replay/runtime proof still required.'])
    output = ROOT.parent / 'becej-2015-original-opening-review-v1.json'
    pipeline.write_canonical_json(output, result)
    print(dict(review=registry.relative_workspace_path(output), source_squad=25,
        dated_manager=preview['manager'], unresolved_match_labels=len(opening['unresolved_labels']),
        native_writes=0, duplicates_closed=0), flush=True)


if __name__ == '__main__':
    main()
