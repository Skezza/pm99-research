"""Admit a period FIFA identity using an independently dated official roster.

FIFA supplies identity, abilities and positions, never historical ownership.
The published league PDF establishes membership; it does not establish an XI,
bench appearance or transfer date. Existing native writers remain unchanged.
"""
from __future__ import annotations

import csv
from datetime import date
from functools import lru_cache
import hashlib
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_rating_calibration_v1 as ratings
from scripts import season_historical_roster_audit_v1 as roster
from scripts.season_historical_role_plan_v1 import ROLE_MAP
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES

POLICY = 'exact-target-fifa-and-dated-premier-league-roster-v1'
PERSON_POLICY = 'exact-target-FIFA-identity-with-dated-official-roster-v1'


def _published_alias_matches(published, full_name):
    public = published.casefold().split()
    full = full_name.casefold().split()
    if len(public) < 2 or not full or (public[0], public[-1]) != (full[0], full[-1]):
        return False
    cursor = iter(full)
    return all(any(token == part for token in cursor) for part in public)


def _source(value):
    path = (registry.ROOT / value['path']).resolve(strict=True)
    if (not path.is_relative_to(registry.ROOT.resolve()) or not path.is_file()
            or registry.sha256_file(path) != value['sha256']):
        raise ValueError('dated FIFA admission source path/hash changed')
    return path


@lru_cache(maxsize=4)
def _edition_rows(path_string, source_sha, edition):
    # The caller rehashes the file before every use, including cache hits.
    with Path(path_string).open(newline='') as stream:
        return tuple(dict(row) for row in csv.DictReader(stream)
                     if row['fifa_version'] == str(edition))


def fifa_row(selection, evidence, season):
    value = evidence[selection['fifa_source']]
    path = _source(value)
    edition = int(season[:4]) - 1999
    if not 15 <= edition <= 23:
        raise ValueError('exact target FIFA edition is not available; no future proxy admission')
    rows = _edition_rows(str(path), value['sha256'], edition)
    candidates = [row for row in rows if
                  roster.normalise(row['long_name']) == roster.normalise(selection['name'])
                  and row['dob'] == selection['birth_date']]
    ids = {row['player_id'] for row in candidates}
    if ids != {str(selection['fifa_player_id'])}:
        raise ValueError('FIFA full-name/DOB identity is missing, ambiguous or has another player ID')
    if selection.get('native_display_name'):
        alias_ids = {row['player_id'] for row in rows if row['dob'] == selection['birth_date']
                     and _published_alias_matches(selection['native_display_name'], row['long_name'])}
        if alias_ids != ids:
            raise ValueError('published roster name and DOB have ambiguous FIFA identities')
    fields = ('player_positions', 'short_name', 'nationality_name', 'height_cm', 'weight_kg',
              *ratings.MAPPING.values())
    if len({tuple(row[k] for k in fields) for row in candidates}) != 1:
        raise ValueError('contradictory target-edition FIFA updates require review')
    row = min(candidates, key=lambda r: r['fifa_update_date'])
    stamp = date.fromisoformat(row['fifa_update_date'])
    year = int(season[:4])
    if not date(year, 6, 1) <= stamp <= date(year + 1, 5, 31):
        raise ValueError('FIFA update is outside the target season')
    return row, path, value


def roster_membership(selection, evidence, season, club):
    if selection.get('admission_policy') != POLICY:
        raise ValueError('unsupported dated FIFA admission policy')
    value = evidence[selection['roster_source']]
    path = _source(value)
    stamp = date.fromisoformat(selection['roster_date'])
    if stamp.year != int(season[:4]) or stamp.month != 8:
        raise ValueError('official opening roster must be dated in target August')
    origin = urlsplit(value['url'])
    expected = '/premierleague/document/' + stamp.strftime('%Y/%m/%d') + '/'
    if (origin.scheme != 'https'
            or origin.hostname != 'premierleague-static-files.s3.amazonaws.com'
            or not origin.path.startswith(expected) or not origin.path.lower().endswith('.pdf')
            or origin.query or origin.fragment):
        raise ValueError('official roster URL does not bind the requested publisher and date')
    if not path.read_bytes().lstrip(b' \t\r\n').startswith(b'%PDF-'):
        raise ValueError('official roster body is not a PDF')
    text = subprocess.run(['pdftotext', '-layout', str(path), '-'], check=True,
                          capture_output=True, text=True).stdout
    blocks = re.split(r'NOTIFICATION OF SHIRT NUMBERS\s*:\s*', text)[1:]
    wanted = selection['club_name']
    if club['name'] != wanted:
        raise ValueError('official roster selection belongs to another destination club')
    hits = [block for block in blocks if block.splitlines()[0].strip() == wanted]
    if len(hits) != 1:
        raise ValueError('one exact official club roster block is required')
    # Stop at the next page; another club's row can never provide membership.
    block = hits[0].split('\f', 1)[0]
    entries = []
    for number, family, given in re.findall(r'^\s*(\d+)\s+([^,\n]+),\s*([^\n]+?)\s*$', block, re.M):
        entries.append((int(number), (given.strip() + ' ' + family.strip())))
    name = selection['native_display_name']
    if len(name.split()) < 2 or any(len(x) < 2 for x in name.split()):
        raise ValueError('roster display needs published given name and complete surname')
    matched = [(number, published) for number, published in entries
               if roster.normalise(published) == roster.normalise(name)]
    if len(matched) != 1:
        raise ValueError('new person is not unique in the destination official roster')
    # Explicit middle-name omission, never initials or arbitrary substrings.
    if not _published_alias_matches(name, selection['name']):
        raise ValueError('published roster name does not identify the complete FIFA name')
    return dict(date=stamp.isoformat(), shirt_number=matched[0][0],
                published_name=matched[0][1], source_sha256=value['sha256'],
                membership='dated-official-August-squad-not-matchday-or-opening-XI-claim')


def new_person(selection, evidence, season, club):
    membership = roster_membership(selection, evidence, season, club)
    row, path, source = fifa_row(selection, evidence, season)
    roles = [ROLE_MAP[v.strip()] for v in row['player_positions'].split(',')]
    first = row['player_positions'].split(',')[0].strip()
    position = ('G' if first == 'GK' else 'D' if first in ('CB', 'SW', 'RB', 'LB', 'RWB', 'LWB')
                else 'F' if first in ('ST', 'CF', 'RW', 'LW', 'RF', 'LF') else 'M')
    country = NATIONALITY_CODES.get(row['nationality_name'])
    if (position, roles, country) != (selection['position'], selection['fine_roles'], selection['nationality']):
        raise ValueError('admission position, roles or nationality differ from exact target FIFA row')
    if not country:
        raise ValueError('FIFA nationality has no declared source code')
    values = {key: max(1, min(99, int(row[column]))) for key, column in ratings.MAPPING.items()}
    if position != 'G':
        values['handling'] = min(20, values['handling'])
    row_sha = hashlib.sha256(pipeline.canonical_json_bytes(row)).hexdigest()
    person = dict(name=row['long_name'], birth_date=row['dob'],
                  source_player_id='fifa:' + row['player_id'], source_provider='fifa',
                  identity_policy=PERSON_POLICY, source_profile_url='https://sofifa.com' + row['player_url'],
                  fifa_source=dict(path=registry.relative_workspace_path(path), sha256=source['sha256']),
                  fifa_edition=int(row['fifa_version']), fifa_row_sha256=row_sha)
    return dict(source_person=person,
                source_player=dict(name=row['long_name'], birth_date=row['dob'], position=position,
                                   nationality=country, height_cm=int(row['height_cm']),
                                   weight_kg=int(row['weight_kg']), shirt_number=membership['shirt_number']),
                raw_evidence=dict(status='original-period-FIFA-row-and-official-roster-reparsed',
                                  local_path=str(path), source_sha256=source['sha256'],
                                  fifa_row_sha256=row_sha, fifa_values=values,
                                  published_display_name=membership['published_name'],
                                  fine_roles=roles, membership=membership),
                membership=membership['membership'])


def published_move_display(actor, claim, evidence, season):
    """Use a literal published short name, keeping the full recipe identity."""
    if set(claim) != {'fifa_player_id', 'fifa_source'}:
        raise ValueError('published FIFA display needs an exact source and player ID')
    value = evidence[claim['fifa_source']]
    path = _source(value)
    rows = _edition_rows(str(path), value['sha256'], int(season[:4]) - 1999)
    published = actor.get('source_name') or actor['name']
    candidates = [row for row in rows if row['dob'] == actor['facts']['birth_date']
                  and _published_alias_matches(published, row['long_name'])]
    if {row['player_id'] for row in candidates} != {str(claim['fifa_player_id'])}:
        raise ValueError('moved published name/DOB does not uniquely identify the FIFA player')
    selection = dict(claim, name=candidates[0]['long_name'], native_display_name=published,
                     birth_date=actor['facts']['birth_date'])
    row, _, source = fifa_row(selection, evidence, season)
    from scripts.season_package_compiler_v2 import _pm99_text
    return dict(display_name=_pm99_text(row['short_name'], label='literal published FIFA short name'),
                published_name=row['short_name'], source_sha256=source['sha256'],
                published_full_name=row['long_name'],
                fifa_row_sha256=hashlib.sha256(pipeline.canonical_json_bytes(row)).hexdigest())


def person_id(person):
    if person.get('identity_policy') != PERSON_POLICY or person.get('source_provider') != 'fifa':
        raise ValueError('unsupported FIFA person identity policy')
    source = person['fifa_source']
    path = _source(source)
    rows = _edition_rows(str(path), source['sha256'], person['fifa_edition'])
    matches = [row for row in rows if 'fifa:' + row['player_id'] == person['source_player_id']
               and row['long_name'] == person['name'] and row['dob'] == person['birth_date']
               and 'https://sofifa.com' + row['player_url'] == person['source_profile_url']
               and hashlib.sha256(pipeline.canonical_json_bytes(row)).hexdigest() == person['fifa_row_sha256']]
    if len(matches) != 1:
        raise ValueError('FIFA person identity does not reproduce from the retained original row')
    return 'person-fifa-' + matches[0]['player_id']
