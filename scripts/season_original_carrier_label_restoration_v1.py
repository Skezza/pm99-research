"""Restore a source-authored club's original carrier label without moving people.

Unlike full-XI certification, this admits missing optional biographies. Every
represented player must still bind one unanimous immutable source selector;
the original carrier registry, dated fixture, current coach and ground must
independently agree. No majority vote or new carrier selection is allowed.
"""
from datetime import date
from pathlib import Path
import re

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.editor_actions import _read_eq_inline_string
from scripts import season_historical_club_label_review_v1 as old
from scripts import season_historical_club_label_plan_v1 as labels
from scripts import season_external_soccerbase_birthday_v2 as originals
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_equivalent_soccerbase_openings_v1 as equivalents
from scripts import season_opening_order_repair_v1 as owners

pipeline, registry = old.pipeline, old.registry
SCHEMA = 'pm99-unanimous-source-original-carrier-label-restoration-v1'


def bind(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def checked(binding):
    path = registry.ROOT / binding['path']
    if registry.sha256_file(path) != binding['sha256']:
        raise ValueError('original carrier label source changed')
    return path


def cohort_source(club, people, artifact_id, index, sources):
    if len(people) < 11 or len({p['person_id'] for p in people}) != len(people):
        raise ValueError('club identity needs a distinct authored cohort, not a name majority')
    common = None
    for person in people:
        if person['proof']['artifact_id'] != artifact_id:
            raise ValueError('every represented player must bind original authored rows')
        matches = set()
        for key, row in index.get(person['person_id'], []):
            facts = row['facts']
            if (old.roster.source_group(key[0]) == old.roster.club_group(club)
                    and old._normalise(facts['name']) in {
                        old._normalise(person['name']), old._normalise(person.get('source_name'))}
                    and (not facts.get('birth_date') or facts['birth_date'] == person['facts'].get('birth_date'))):
                matches.add(key)
        if not matches:
            raise ValueError('an authored person/name/known birthday no longer binds original rows')
        common = matches if common is None else common & matches
    if common is None or len(common) != 1:
        raise ValueError('authored cohort has mixed or ambiguous original clubs')
    return sources[next(iter(common))]


def coach(raw, name, club, year):
    page = BeautifulSoup(raw, 'lxml')
    if [h.get_text(' ', strip=True) for h in page.select('h1#firstHeading')] != [name]:
        raise ValueError('dated coach biography has another full name')
    managing = False; hits = []
    for tr in page.select('table.infobox tr'):
        text = tr.get_text(' ', strip=True)
        if text in ('Managerial career', 'Managerial career[edit]'):
            managing = True; continue
        if not managing:
            continue
        cells = tr.find_all(['th', 'td'], recursive=False)
        if len(cells) < 2 or not any(a.get_text(' ', strip=True) == club for a in cells[1].select('a')):
            continue
        years = re.fullmatch(r'(\d{4})[–-](\d{4})', cells[0].get_text(' ', strip=True))
        if years and int(years[1]) < year < int(years[2]):
            hits.append(dict(from_year=int(years[1]), to_year=int(years[2]), literal=text))
    if len(hits) != 1:
        raise ValueError('one unambiguous manager spell strictly containing the target year required')
    return hits[0]


def ground(raw, name, club, year):
    page = BeautifulSoup(raw, 'lxml')
    title = [h.get_text(' ', strip=True) for h in page.select('h1#firstHeading')]
    if len(title) != 1 or title[0] not in (name, name + ' (' + club + ')'):
        raise ValueError('ground biography title differs from retained native ground')
    hits = []
    for tr in page.select('table.infobox tr'):
        text = tr.get_text(' ', strip=True)
        for match in re.finditer(re.escape(club) + r' \((\d{4})[–-](\d{4})\)', text):
            if int(match[1]) < year < int(match[2]):
                hits.append(dict(from_year=int(match[1]), to_year=int(match[2]), literal=text))
    if len(hits) != 1:
        raise ValueError('one published original ground tenancy containing target year required')
    return hits[0]


def prepare(base, targets, source_inputs):
    if not targets or len(set(targets)) != len(targets):
        raise ValueError('explicit distinct club carriers required')
    paths = {key: checked(value) for key, value in source_inputs.items()
             if key in ('preallocation', 'fixed_registry', 'opening_equivalence')}
    package = pipeline.read_json_file(base.package_path)
    preallocation = pipeline.read_json_file(paths['preallocation'])
    fixed = pipeline.read_json_file(paths['fixed_registry'])
    if (paths['fixed_registry'].resolve() != (registry.ROOT/'seasons'/base.season/'fixed-carrier-registry.json').resolve()
            or fixed.get('schema_version') != 'pm99-world-fixed-carrier-registry-v2'):
        raise ValueError('requires this season original fixed-carrier registry, not an arbitrary replacement')
    previous_opening = pipeline.read_json_file(paths['opening_equivalence'])
    artifact_id = 'opening-squad-preallocation-' + base.season
    descriptor = next(a for a in package['artifacts'] if a['id'] == artifact_id)
    if descriptor['sha256'] != registry.sha256_file(paths['preallocation']):
        raise ValueError('current recipe does not bind original source preallocation')
    captures, _ = old.roster.load_sources(base.season)
    index, sources = old.indexed_claims(preallocation)
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(eq).entries}
    player_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    actual_owners = owners.native_owners(eq)
    holders, native_coaches = old._manager_graph(eq_path=base.game_path/'DBDAT/EQ98030.FDI',
        ent_path=base.game_path/'DBDAT/ENT98030.FDI')
    managers = {m['id']: m for m in package['managers']}
    updates = []; witnesses = []
    for carrier in sorted(targets):
        club = next(c for c in package['clubs'] if c['carrier_id'] == carrier)
        represented = [p for p in package['players'] if p['club_id'] == club['id']]
        if {p['id'] for p in represented} != set(club['roster_player_ids']):
            raise ValueError('declared roster differs from its authored people')
        source = cohort_source(club, represented, artifact_id, index, sources)
        target = source['selector']['club_name']
        baseline = [c for c in fixed['carriers'] if c['carrier_id'] == carrier]
        if (len(baseline) != 1 or baseline[0]['record_mode'] != 1
                or old.builder._normalise_club_name(baseline[0]['baseline_club']['name']) != old.builder._normalise_club_name(target)):
            raise ValueError('source target is not this original fixed carrier identity')
        if any(c['id'] != club['id'] and old.roster.club_group(c) == old.roster.club_group(club)
               and old.builder._normalise_club_name(c['name']) == old.builder._normalise_club_name(target)
               for c in package['clubs']):
            raise ValueError('restoring label would create another represented club')
        relevant = [c for c in captures if old.selector_key(c) == old.selector_key(source['selector'])]
        selected, actual, equivalent = equivalents.select(relevant,
            lambda c: replay.replay_club(base.season, c, {}, True, allow_missing_birth_date=True))
        if (actual['fixture'] != previous_opening['actual']['fixture']
                or actual['raw_sources'] != previous_opening['actual']['raw_sources']):
            raise ValueError('original fixture/biography evidence differs from reviewed opening')
        for person in represented:
            native = old.roster.native_player(player_entries[person['carrier_id']].decode_payload(jug), person['carrier_id'])
            if (actual_owners.get(person['carrier_id']) != {carrier}
                    or old.roster.normalise(native['name']) != old.roster.normalise(person['name'])):
                raise ValueError('actual native person or exclusive ownership differs')
        payload = entries[carrier].decode_payload(eq)
        short, full, _ = labels.prefix_parts(payload)
        marker = payload.find(bytes.fromhex('dd6361'))
        _, _, end = _read_eq_inline_string(payload, marker+4)
        native_ground, _, _ = _read_eq_inline_string(payload, end)
        manager = managers[club['manager_id']]
        if (old.builder._normalise_club_name(short) != old.builder._normalise_club_name(club['name'])
                or native_ground != baseline[0]['baseline_club']['ground_name']
                or manager['carrier_id'] != baseline[0]['baseline_club']['active_manager_carrier_id']
                or native_coaches.get(manager['carrier_id']) != manager['name']
                or [c['carrier_id'] for c in holders.get(manager['carrier_id'], [])] != [carrier]):
            raise ValueError('retained original ground/coach/name or exclusive owner differs')
        year = int(base.season[:4])
        coach_proof = coach(originals.publisher_original(source_inputs['coach']), manager['name'], target, year)
        ground_proof = ground(originals.publisher_original(source_inputs['ground']), native_ground, target, year)
        updates.append(dict(club_id=club['id'], carrier_id=carrier, before=club['name'],
            before_full=club.get('full_name'), after=target,
            identity_after=old.builder._source_club_identity_id(old.roster.club_group(club), target),
            native_before=short, native_full_before=full,
            native_after=labels.compiler._pm99_text(target, label='source-authored original carrier club')))
        witnesses.append(dict(carrier_id=carrier, source_selector=source['selector'],
            all_represented_players_source_bound=len(represented), original_fixture=actual['fixture'],
            raw_sources=actual['raw_sources'], opening_equivalence=equivalent,
            retained_native_coach=manager['name'], coach_spell=coach_proof,
            retained_native_ground=native_ground, ground_tenancy=ground_proof,
            complete_native_opening_XI_approved=False))
    result = dict(schema_version=SCHEMA, season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'),
        ent_sha256=registry.sha256_file(base.game_path/'DBDAT/ENT98030.FDI'), targets=sorted(targets),
        source_inputs=source_inputs, updates=updates, witnesses=witnesses,
        implementation_inputs=[bind(Path(m.__file__)) for m in (old, labels, originals, replay, equivalents)] + [bind(Path(__file__))],
        scope='Original carrier source-authored short/full club labels and matching recipe identity/proof only. Every player byte/fact/owner/order/tactic, coach, ground, capacity, executable and asset preserved. Missing GK and secondary facts remain separate open corrections.')
    result['transaction_id'] = pipeline.canonical_json_sha256(result)[:24]
    return result


def verify(base, plan):
    if plan.get('schema_version') != SCHEMA or prepare(base, plan['targets'], plan['source_inputs']) != plan:
        raise ValueError('original source-authored carrier label restoration does not reproduce')
