"""Read an original August cup XI and a separately published dated bench.

No yearly-catalogue membership inference: the RSSSF match proves the XI and
used substitutes, while the dated original match page witnesses two unused
substitutes. Its conflicting coach and reserve are explicitly not imported.
"""
import re

from bs4 import BeautifulSoup

RSSSF_URL = 'https://rsssf.org/sacups/sudamcup-venez.html'
MATCH_URL = 'https://www.transfermarkt.es/spielbericht/index/spielbericht/3298494'
RSSSF_LINE = ('Monagas: José Bottini, Enermis Rodríguez, Rubén Chávez, José González, '
    'Alexander Flores, Luis “pájaro” Vera, Juan José Cardinal '
    '(César “maestrico” González, 46), Adrián Álvarez (Alexis Acuña, 78), '
    'Carlos “pomada” Bravo (Pedro Duval, 59), Juan “lagarto” García, '
    'Rafael Castellín. Coach: Eduardo Borrero;')
XI = [('José Bottini', 659637), ('Enermis Rodríguez', 847961),
    ('Rubén Chávez', 823618), ('José González', 99192),
    ('Alexander Flores', 847955), ('Luis Vera', 72568),
    ('Juan José Cardinal', 807018), ('Adrián Álvarez', 847566),
    ('Carlos Bravo', 313103), ('Juan García', 28158),
    ('Rafael Castellín', 72532)]
USED = [('César González', 56426, 46), ('Alexis Acuña', 147681, 78),
    ('Pedro Duval', 308346, 59)]
UNUSED = [('Johny Alejo', 847941), ('Hernán Sivira', 847954)]
BENCH_IDS = {847941, 847954, 308346, 847531, 56426, 147681}


def parse(rsssf_raw, match_raw, *, urls=(RSSSF_URL, MATCH_URL)):
    if urls != (RSSSF_URL, MATCH_URL) or any(
        not isinstance(raw, bytes) or not 500 <= len(raw) <= 2 * 1024**2
        for raw in (rsssf_raw, match_raw)):
        raise ValueError('unexpected original August source URL or size')
    rsssf = BeautifulSoup(rsssf_raw.decode('cp1252'), 'html.parser')
    if rsssf.title is None or rsssf.title.get_text() != 'Venezolan clubs in Copa Sudamericana':
        raise ValueError('original cup compilation title differs')
    pre = rsssf.find('pre')
    text = re.sub(r'\s+', ' ', pre.get_text(' ', strip=True)) if pre else ''
    if text.count('Edition 2002') != 1:
        raise ValueError('original2002 edition missing or ambiguous')
    section = text.split('Edition 2002', 1)[1]
    if section.count('[August 28]') != 1 or '[September 6]' not in section:
        raise ValueError('original August cup date missing or ambiguous')
    august = section.split('[August 28]', 1)[1].split('[September 6]', 1)[0]
    return_leg = section.split('[September 6]', 1)[1].split('First Round:', 1)[0]
    if 'At Estadio Alexander “comanche” Bottini in Maturín' not in return_leg:
        raise ValueError('original adjoining return-leg home ground differs')
    if (august.count(RSSSF_LINE) != 1
            or 'Deportivo Táchira 0-2 Monagas SC' not in august
            or 'At Estadio Pueblo Nuevo in San Cristóbal' not in august):
        raise ValueError('original Monagas target XI, manager, fixture or date differs')
    match = BeautifulSoup(match_raw, 'html.parser')
    expected_title = ('Deportivo Táchira - Monagas SC, 28/08/2002 - '
        'Copa Sudamericana - Informe del partido | Transfermarkt')
    if match.title is None or match.title.get_text() != expected_title:
        raise ValueError('separate bench report club, date or competition differs')
    boxes = [box for box in match.select('div.large-6.columns')
        if box.select_one('table.ersatzbank') is not None
        and box.get_text(' ', strip=True).startswith('Monagas SC Formación inicial:')]
    if len(boxes) != 1:
        raise ValueError('original Monagas lineup/bench is missing or ambiguous')
    box = boxes[0]
    links = {int(re.search(r'/profil/spieler/(\d+)', a['href'])[1])
        for a in box.select('a[href*="/profil/spieler/"]')}
    bench = box.select_one('table.ersatzbank')
    bench_ids = {int(re.search(r'/profil/spieler/(\d+)', a['href'])[1])
        for a in bench.select('a[href*="/profil/spieler/"]')}
    if (links != {id for _, id in XI} | BENCH_IDS or bench_ids != BENCH_IDS
            or 'Entrenador: Eduardo Borrero' not in bench.get_text(' ', strip=True)):
        raise ValueError('original dated bench IDs or Monagas manager differ')
    for name, id in UNUSED:
        names = {a.get_text(' ', strip=True) for a in bench.select(
            f'a[href*="/profil/spieler/{id}"]')}
        if names != {name}:
            raise ValueError('original unused substitute published label differs')
    return dict(season='2002-03', club='Monagas SC', fixture_date='2002-08-28',
        competition='cup', first_league_xi=False, opponent='Deportivo Táchira',
        result='2-0', manager='Eduardo Borrero',
        opening_home_ground=dict(name='Estadio Alexander Comanche Bottini', witnessed_date='2002-09-06'),
        starting_xi=[dict(published_match_name=name, source_player_id=id) for name, id in XI],
        used_substitutes=[dict(published_match_name=name, source_player_id=id, minute=minute)
            for name, id, minute in USED],
        unused_substitutes=[dict(published_match_name=name, source_player_id=id) for name, id in UNUSED],
        formation=None,
        source_disagreements=[
            dict(field='opponent coach', source='Transfermarkt August28 report',
                published='César Farías', other_source='RSSSF', other_published='Walter Cata Roque',
                disposition='Never import opposing coach into Monagas or another recipe.'),
            dict(field='unused substitute', source_player_id=847531,
                published='Hugo González', disposition='Excluded: recorded departure July1,2002 conflicts with dated bench; no continuity inference.')],
        source_gaps=['August cup XI, not first league XI.',
            'Formation and broad roles require an explicit editorial declaration.',
            'Person biographies and secondary facts require separate original-source joins.',
            'The published bench is not approved wholesale; conflicting Hugo González excluded.'],
        credits='Eliézer Sebastián Pérez Pérez/RSSSF; Transfermarkt original historical match report.',
        native_writes=0, publication_authorised=False)


def prepare(output):
    from scripts.capture_tachira_2014_original_people_v1 import source_rows
    from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
    from scripts import season_published_transfer_history_v1 as history
    from scripts import season_historical_transfer_review_v1 as transfer
    if output.exists():
        raise ValueError('original source review is immutable')
    originals = [source_rows(key) for key in (
        'venezuela-2002-2003-original-RSSSF-Sudamericana-lineups',
        'monagas-2002-original-August28-first-cup-full-match')]
    result = parse(*(row[1] for row in originals))
    result['original_bindings'] = [row[2] for row in originals]
    history_path = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1/monagas-2002-original-reserve-histories-v1.json'
    events, _ = history.merge({}, pipeline.read_json_file(history_path))
    interval = transfer.transfer_interval(events.get(847531, []), '2002-08-28')
    if (interval.get('status') != 'recorded-entry-and-exit-bracket-fixture'
            or interval['source_owner_club_id'] != 75
            or interval['entry']['date'] != '2002-07-01'
            or interval['entry']['from_club_id'] != 14596):
        raise ValueError('excluded reserve chronology does not replay the original July departure')
    result['excluded_reserve_original_history'] = dict(source_player_id=847531, interval=interval,
        binding=dict(path=registry.relative_workspace_path(history_path), sha256=registry.sha256_file(history_path)))
    result['original_bindings'].append(result['excluded_reserve_original_history']['binding'])
    pipeline.write_canonical_json(output, result)
    return result
