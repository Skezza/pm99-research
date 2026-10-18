"""Admit an opening reserve omitted from an end-of-season annual roster.

An annual omission cannot disprove an original August appearance. Conversely,
the appearance does not certify every profile detail. Replay both originals,
use the biography's positive interior-year senior spell, and leave nationality
unknown rather than deriving it from birthplace or carrying another man's ENG.
This is source admission only; actual alias replacement is a separate delta.
"""
import copy
from datetime import UTC, datetime
import re
from bs4 import BeautifulSoup

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_wikipedia_career_identity_v1 as wiki
from scripts import season_august_manager_tenures_20261016 as managers
from scripts.prepare_stoke_alias_identity_evidence_20261016 import original
from scripts.audit_shtanyuk_runtime_aliases_20261016 import ROOT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

URL = 'https://en.wikipedia.org/wiki/Jurgen_Vandeurzen'


def substitution(raw):
    """One literal incoming player event, exact club ID and outgoing XI man."""
    page = BeautifulSoup(raw, 'html.parser')
    events = []
    for event in page.select('#sb-wechsel li'):
        clubs = {int(m[1]) for a in event.select('.sb-aktion-wappen a[href]')
            if (m := re.search(r'/startseite/verein/(\d+)(?:/|$)', a['href']))}
        incoming = event.select('.sb-aktion-wechsel-ein a[title][href]')
        outgoing = event.select('.sb-aktion-wechsel-aus a[title][href]')
        if clubs != {512} or len(incoming) != 1 or len(outgoing) != 1:
            continue
        link = incoming[0]
        if (link['title'] == 'Jurgen Vandeurzen'
                and re.search(r'/spieler/20366(?:/|$)', link['href'])
                and outgoing[0]['title'] == 'Kris Commons'
                and re.search(r'/spieler/13561(?:/|$)', outgoing[0]['href'])):
            events.append(dict(source_player_id=20366, name=link['title'], club_id=512,
                replaced_player_id=13561, replaced_player_name=outgoing[0]['title']))
    if len(events) != 1:
        raise ValueError('one exact original Stoke Vandeurzen incoming substitution required')
    return events[0]


def reconcile(person, owner, fixture, historical, current):
    """No fuzzy identity, invented transfer day, or annual-omission veto."""
    if (roster.normalise(person['name']) != 'jurgenvandeurzen'
            or person['birth_date'] != '1974-01-26'
            or roster.normalise(historical['name']) != roster.normalise(person['name'])
            or historical['birth_date'] != person['birth_date']):
        raise ValueError('independent biography and historical full-name/DOB disagree')
    tenure = owner['owner']
    if (owner['anchor'] != '2002-08-01' or tenure['club'] != 'Stoke City'
            or not tenure['entry_year'] < 2002 < tenure['departure_year'] or tenure['loan']):
        raise ValueError('reserve lacks positive target-August senior ownership')
    if (fixture['date'] != '2002-08-10' or fixture['source_club_id'] != 512
            or fixture.get('positive_substitution') != dict(source_player_id=20366,
                name='Jurgen Vandeurzen', club_id=512, replaced_player_id=13561,
                replaced_player_name='Kris Commons')):
        raise ValueError('reserve lacks the independently reparsed original opening substitution')
    if any(roster.normalise(p['name']) == 'jurgenvandeurzen' for p in current):
        raise ValueError('current annual omission changed; inspect instead of silently changing policy')
    source = copy.deepcopy(historical)
    source.update(name=person['name'], nationality=None, shirt_number=None)
    source['unresolved_fields'] = sorted(set(source.get('unresolved_fields', [])) | {'nationality', 'shirt_number'})
    return dict(source_player=source, source_person=person, owner_evidence=owner,
        positive_opening_substitution=fixture,
        current_annual_omission_explicit=True,
        historical_height_weight_not_target_season_measurements=True,
        target_shirt_number_claimed=False, nationality_inferred_from_birthplace=False,
        exact_transfer_day_claimed=False)


def annual(season):
    rows, bindings = roster.load_sources(season)
    matches = [r for r in rows if roster.source_group(r['country_catalog']) == 'england'
        and r['club_name'] == 'Stoke City' and r['source_path'].endswith('.txt')]
    if len(matches) != 1:
        raise ValueError('one original annual Stoke source required')
    proof = roster.SourceVerifier(season).verify(matches[0])
    if proof['status'] != 'raw-source-reparsed':
        raise ValueError('original annual roster did not independently replay')
    return matches[0], dict(original=proof, captures=[dict(path=b['path'], sha256=b['sha256']) for b in bindings])


def prepare():
    folder = ROOT / 'reserve-originals'
    _, binding = original(folder, 'vandeurzen-biography', URL)
    raw = (registry.ROOT / binding['path']).read_bytes()
    person, owner = wiki.read(raw, 'Jurgen_Vandeurzen', URL, '2002-08-01', 'Stoke City', 'england',
        expected_name='Jurgen Vandeurzen')
    old, old_proof = annual('2001-02')
    current, current_proof = annual('2002-03')
    people = [p for p in old['players'] if roster.normalise(p['name']) == 'jurgenvandeurzen']
    if len(people) != 1:
        raise ValueError('one independently reparsed historical profile required')
    path = managers.old.REVIEWS / '2002-03/opening-review.json'
    review = pipeline.read_json_file(path)
    capture_path = registry.ROOT / review['bindings']['opening_capture_path']
    capture = managers.checked_json(capture_path, review['bindings']['opening_capture_sha256'])
    rows = [r for r in capture['clubs'] if r['source_selector'].get('transfermarkt_club_id') == 512]
    if len(rows) != 1:
        raise ValueError('one original numerical Stoke opening capture required')
    fixture = managers.old.opening.verify_opening(rows[0], capture, capture_path.parent / 'cache')
    report_raw, _ = managers.old.opening.verified_page(capture_path.parent / 'cache',
        capture['source']['cache_files'], rows[0]['lineup_source_url'])
    fixture['positive_substitution'] = substitution(report_raw)
    return dict(schema='pm99-Stoke2002-original-bench-positive-reserve-v1',
        machine='joe-Vostro-3350', source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        biography_original=binding, historical_annual=old_proof, current_annual=current_proof,
        opening_capture=dict(path=registry.relative_workspace_path(capture_path), sha256=registry.sha256_file(capture_path)),
        admitted=reconcile(person, owner, fixture, people[0], current['players']),
        native_writes=0, recipe_writes=0, duplicate_cases_closed=0)


def main():
    path = ROOT / 'vandeurzen-positive-opening-reserve-admission.json'
    if path.exists():
        raise ValueError('completed reserve admission must not repeat')
    result = prepare()
    retained(path, dict(utc=datetime.now(UTC).isoformat(), **result))
    print(dict(positive_original_August_substitution=True, positive_senior_tenure=True,
        current_annual_omission_logged=True, native_writes=0, duplicate_cases_closed=0), flush=True)


if __name__ == '__main__':
    main()
