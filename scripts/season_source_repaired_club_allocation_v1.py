"""Capacity-fit an exact sourced matchday roster without replacing real locals.

This prepares a whole-club transaction. It does not publish games or waive
other-club copies. All existing genuine local people survive, including a
player whose explicit DOB error has independently corroborated correction.
"""
import copy
from functools import lru_cache
import json
import re
from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import capture_named_birth_date_corroboration_v1 as biography
from scripts import season_contextual_tactics_rollout_v1 as rollout


def corroborated_dates(plan, evidence):
    if evidence.get('schema_version') != 'pm99-bounded-named-DOB-corroboration-v1':
        raise ValueError('unsupported explicit DOB corroboration')
    wanted = {r['source_player_id']: r for r in plan['local_DOB_conflicts']}
    rows = evidence['rows']
    if len(rows) != len(wanted) or {r['source_player_id'] for r in rows} != set(wanted):
        raise ValueError('DOB corroboration must cover the exact named local conflicts')
    result = {}
    for row in rows:
        claim = wanted[row['source_player_id']]
        if any(row[k] != claim[k] for k in ('source_name', 'player_id', 'carrier_id', 'before', 'after')):
            raise ValueError('DOB corroboration identifies a different existing slot or date')
        source = row['corroboration']
        biography.validate_url(source['provider'], source['url'])
        path = registry.ROOT / source['path']
        if registry.sha256_file(path) != source['sha256']:
            raise ValueError('DOB original biography changed')
        if json.loads((registry.ROOT / source['receipt_path']).read_text()) != {
                'url': source['url'], 'sha256': source['sha256']}:
            raise ValueError('DOB original biography URL/SHA differs')
        observed = biography.parse(path.read_bytes(), claim['source_name'], source['provider'])
        if observed != claim['after'] or source['observed_birth_date'] != observed:
            raise ValueError('DOB corroboration does not reproduce from original biography')
        result[row['source_player_id']] = claim['player_id']
    return result


def existing_and_new(plan, corrected):
    existing, new = {}, []
    ids = [r['source_player_id'] for r in plan['desired_matchday_people']]
    if len(ids) != len(set(ids)):
        raise ValueError('source matchday people must have unique published IDs')
    for row in plan['desired_matchday_people']:
        id = row['source_player_id']
        slots = list(row['existing_club_player_ids'])
        if id in corrected:
            if slots:
                raise ValueError('corrected local DOB cannot introduce a second same-person slot')
            slots = [corrected[id]]
        if len(slots) > 1:
            raise ValueError('multiple existing local slots for one sourced matchday person')
        if slots:
            existing[id] = slots[0]
        else:
            if not row['source_person'] or not row['historical_fact_sources'] or not row['source_broad_position_unambiguous']:
                raise ValueError('new matchday person lacks independently sourced identity or player facts')
            facts = row['historical_fact_sources'][0]
            if facts['source_player']['birth_date'] != row['source_person']['birth_date']:
                raise ValueError('new matchday person and source facts disagree on DOB')
            new.append({'source_player': copy.deepcopy(facts['source_player']),
                'source_person': copy.deepcopy(row['source_person']), 'raw_evidence': copy.deepcopy(facts['raw_evidence'])})
    if len(set(existing.values())) != len(existing):
        raise ValueError('two actual matchday people claim one existing carrier')
    return existing, sorted(new, key=lambda r: r['source_person']['source_player_id'])


def fit_slots(original, displaced, replacements, published_aliases):
    if len(displaced) != len(replacements) or not displaced:
        raise ValueError('whole-club replacement must use the exact fixed capacity')
    people = [r['source_person']['source_player_id'] for r in replacements]
    if len(people) != len(set(people)) or len({p['carrier_id'] for p in displaced}) != len(displaced):
        raise ValueError('whole-club allocation needs unique people and carriers')
    replacements = sorted(replacements, key=lambda r: r['source_person']['source_player_id'])
    options = {}
    for i, player in enumerate(sorted(displaced, key=lambda p: p['carrier_id'])):
        for j, replacement in enumerate(replacements):
            old, new = player['facts']['primary_position'], replacement['source_player']['position']
            if ('G' in (old, new)) and old != new:
                continue
            person = replacement['source_person']
            view = {'players': [{'id': player['id'], 'name': delta.compiler._pm99_text(
                replacement['source_player']['name'], label='actual opening matchday name'),
                'source_name': replacement['source_player']['name']}]}
            trial = {'player_id': player['id'], 'carrier_id': player['carrier_id'], 'replacement': replacement}
            claim = published_aliases.get(person['source_player_id'])
            if claim is not None and claim['birth_date'] == person['birth_date']:
                trial['published_display_names'] = claim
            try:
                fitted = delta.fit_display_names(original, view, {'updates': [trial]})[0]
            except (ValueError, RuntimeError):
                continue
            options[i, j] = {'player_id': player['id'], 'carrier_id': player['carrier_id'],
                'before': copy.deepcopy(player), 'replacement': copy.deepcopy(replacement),
                'display': fitted, 'broad_role_change': {'before': old, 'after': new},
                **({'published_display_names': claim} if 'published_display_names' in trial else {})}
    count = len(displaced)
    @lru_cache(None)
    def best(i, used):
        if i == count:
            return 0, ()
        choices = []
        for j in range(count):
            if used & (1 << j) or (i, j) not in options:
                continue
            tail = best(i + 1, used | (1 << j))
            if tail is None:
                continue
            option = options[i, j]
            # Actual goalkeeper identity and name fit are hard constraints;
            # minimise genuine outfield broad-role changes, then stable IDs.
            cost = int(option['broad_role_change']['before'] != option['broad_role_change']['after']) * 1000
            choices.append((cost + tail[0], (j,) + tail[1]))
        return min(choices) if choices else None
    selected = best(0, 0)
    if selected is None:
        raise ValueError('actual matchday roster cannot fit the exact displaced native slots')
    return [options[i, j] for i, j in enumerate(selected[1])]


def source_grid(raw, club_id, expected_ids, formation):
    page = BeautifulSoup(raw, 'lxml')
    boxes = []
    for box in page.find_all('div'):
        if not set(box.get('class', [])) & {'large-6', 'aufstellung-box'}:
            continue
        ids = {int(m.group(1)) for link in box.find_all('a', href=True)
               if (m := re.search(r'/startseite/verein/(\d+)(?:/|$)', link['href']))}
        if ids == {club_id} and box.select('.formation-player-container'):
            boxes.append(box)
    if len(boxes) != 1:
        raise ValueError('original deployment lacks one exact club pitch box')
    rows = {}
    for player in boxes[0].select('.formation-player-container'):
        ids = {int(m.group(1)) for link in player.find_all('a', href=True)
               if (m := re.search(r'/profil/spieler/(\d+)(?:/|$)', link['href']))}
        styles = {k: float(v) for k, v in re.findall(r'(top|left)\s*:\s*(\d+(?:\.\d+)?)\s*%', player.get('style', ''))}
        if len(ids) != 1 or set(styles) != {'top', 'left'} or any(not 0 <= v <= 100 for v in styles.values()):
            raise ValueError('original player deployment is ambiguous or out of range')
        id = next(iter(ids))
        if id in rows:
            raise ValueError('original player appears twice in source pitch')
        rows[id] = styles
    if set(rows) != set(expected_ids) or len(rows) != 11:
        raise ValueError('original source deployment does not contain the exact actual XI')
    ordered = sorted(rows, key=lambda id: (-rows[id]['top'], -rows[id]['left']))
    if rows[ordered[0]]['top'] == rows[ordered[1]]['top']:
        raise ValueError('source goalkeeper depth is not unique')
    result = {ordered[0]: rollout.formation_template(formation)[0]}
    cursor = 1
    for count in map(int, formation.split('-')):
        line = ordered[cursor:cursor + count]
        if cursor + count < 11 and rows[line[-1]]['top'] == rows[ordered[cursor + count]]['top']:
            raise ValueError('original source deployment has an ambiguous line boundary')
        line.sort(key=lambda id: -rows[id]['left'])
        if len({rows[id]['left'] for id in line}) != len(line):
            raise ValueError('original source has tied lateral positions within a line')
        template = rollout.formation_template(formation)
        for id, slot in zip(line, template[cursor:cursor + count]):
            result[id] = slot
        cursor += count
    if len(result) != 11:
        raise ValueError('source formation does not contain the full XI')
    return result
