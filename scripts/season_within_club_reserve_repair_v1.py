"""Bench-only equal-DOB duplicate repair with original dated career evidence.

This is not the cross-club first-fixture policy. It requires two actual native
copies inside one squad, an independently reparsed annual roster and a complete
original Soccerbase career bracket for the unused replacement. Starters and
all club/manager/kit/tactics bytes remain untouched by the existing delta writer.
"""
import copy
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_release_registry_v1 as registry
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
from app.fdi_indexed import IndexedFDIFile

SCHEMA = 'pm99-within-club-native-equal-DOB-reserve-repair-v1'
POLICY = 'original-dated-career-interior-bracket-and-target-annual-reserve-v1'


def name_components(full_name, published_label):
    full, short = full_name.split(), published_label.split()
    if (len(full) == len(short) == 2 and len(short[0]) == 1 and
            short[0].casefold() == full[0][0].casefold() and short[1] == full[1]):
        return {'given_name': full[0], 'family_name': full[1]}
    return {}


def career_owner(raw, anchor, expected_name):
    """No approximate dates, missing exits, overlapping loans or current club."""
    tables = BeautifulSoup(raw, 'lxml').select('table.career')
    if len(tables) != 1:
        raise ValueError('replacement needs one original career table')
    rows = []
    for tr in tables[0].select('tbody tr'):
        cells = tr.find_all('td', recursive=False)
        links = cells[0].select('a[href]') if cells else []
        if not links:
            continue  # provider total/statistics rows are not club claims
        if len(cells) < 4 or len(links) != 1:
            raise ValueError('ambiguous original career row')
        url = urlparse(links[0]['href'])
        ids = parse_qs(url.query)
        if (url.netloc not in ('', 'www.soccerbase.com') or
                url.path != '/teams/team.sd' or set(ids) != {'team_id'} or
                len(ids['team_id']) != 1 or not ids['team_id'][0].isdigit()):
            raise ValueError('original career team identity is not exact')
        dates = []
        for cell in cells[1:3]:
            text = cell.get_text(' ', strip=True)
            try:
                value = datetime.strptime(text, '%d %b, %y').date()
            except ValueError as exc:
                raise ValueError('incomplete or unsupported dated career bracket') from exc
            # The two-digit provider year is never guessed across centuries.
            # This policy is explicitly limited to the existing 1999+ releases.
            if value.year < 1969 or value.year > 2068:
                raise ValueError('career year outside unambiguous provider window')
            dates.append(value.isoformat())
        if dates[0] >= dates[1]:
            raise ValueError('invalid dated career bracket')
        rows.append({'provider_club_id': 'soccerbase:' + ids['team_id'][0],
            'club': links[0].get_text(' ', strip=True), 'entry': dates[0],
            'departure': dates[1], 'loan': 'loan' in cells[3].get_text(' ', strip=True).casefold()})
    active = [r for r in rows if r['entry'] <= anchor <= r['departure']]
    if (len(active) != 1 or active[0]['loan'] or
            not active[0]['entry'] < anchor < active[0]['departure'] or
            roster.normalise(active[0]['club']) != roster.normalise(expected_name)):
        raise ValueError('replacement lacks one interior non-loan dated club owner')
    return {'policy': POLICY, 'anchor': anchor, 'owner': active[0], 'career_rows': rows,
        'exact_matchday_appearance_claimed': False}


def native_facts(data, carrier):
    entries = [e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id == carrier]
    if len(entries) != 1:
        raise ValueError('ambiguous native duplicate carrier')
    payload = entries[0].decode_payload(data)
    parsed = roster.native_player(payload, carrier)
    end = parsed['name_end']
    born = date(int.from_bytes(bytes(b ^ 0x61 for b in payload[end+14:end+16]), 'little'),
                payload[end+13] ^ 0x61, payload[end+12] ^ 0x61)
    return {'name': parsed['name'], 'birth_date': born.isoformat(),
        'position': parsed['position'], 'startup_order': payload[end] ^ 0x61}


def annual_capture(season, club):
    captures, _ = roster.load_sources(season)
    names = roster.club_names(roster.club_group(club), club['name'], club.get('full_name', ''))
    matching = [c for c in captures if roster.source_group(c['country_catalog']) == roster.club_group(club)
                and roster.normalise(c['club_name']) in names]
    verifier = roster.SourceVerifier(season)
    checked = [(c, verifier.verify(c)) for c in matching]
    good = [(c, p) for c, p in checked if p['status'] == 'raw-source-reparsed']
    if len(good) != 1:
        raise ValueError('replacement needs one independently reparsed target-season club roster')
    return good[0]


def make_plan(release, displaced, retained, replacement_name, provider_id, cache, *, duplicate_provider_id,
              display_game_id=None, biography_provider='soccerbase', allow_wikipedia_entry_month=False,
              reviewed_profile_position=None):
    package = next(pkg for label, pkg, _ in planner.package_layers(release) if label == 'main')
    by_carrier = {p['carrier_id']: p for p in package['players']}
    before, keep = by_carrier[displaced], by_carrier[retained]
    if before['club_id'] != keep['club_id'] or displaced == retained:
        raise ValueError('duplicate copies are not distinct members of one club')
    club = next(c for c in package['clubs'] if c['id'] == before['club_id'])
    if not {before['id'], keep['id']} <= set(club['roster_player_ids']):
        raise ValueError('duplicate copies are not in the declared native squad')
    data = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    eq_entries = [e for e in IndexedFDIFile.from_bytes(eq).entries if e.record_id == club['carrier_id']]
    if len(eq_entries) != 1:
        raise ValueError('duplicate club native carrier is ambiguous')
    e = eq_entries[0]
    actual_roster = roster.parse_eq_external_team_roster_payload(
        eq[e.payload_offset:e.payload_offset+e.payload_length], {})
    actual_members = [r.player_record_id for r in actual_roster.rows] if actual_roster else []
    if actual_members.count(displaced) != 1 or actual_members.count(retained) != 1:
        raise ValueError('duplicate copies are not each once in the actual native squad')
    first, second = native_facts(data, displaced), native_facts(data, retained)
    names = [p.get('source_name') or p['name'] for p in (before, keep)]
    primary_alias = biography_provider == 'original-savio-bobb-2024'
    if primary_alias:
        from scripts import savio_bobb_2024_original_alias_v1 as alias
        alias.validate_pair(release,displaced,retained,names,[first['birth_date'],second['birth_date']],
            club,provider_id,duplicate_provider_id)
    elif (roster.normalise(names[0]) != roster.normalise(names[1]) or
            first['birth_date'] != second['birth_date']):
        raise ValueError('within-club copies do not have the same full source name and native DOB')
    starters, _ = soccerbase.native_starters(release, club)
    if len(starters) != 11:
        raise ValueError('native starting XI could not be independently established')
    if displaced in starters or first['startup_order'] <= 11:
        raise ValueError('within-club replacement cannot change a native starter')
    capture, annual_proof = annual_capture(release.season, club)
    replacements = [r for r in capture['players'] if roster.normalise(r['name']) == roster.normalise(replacement_name)]
    if len(replacements) != 1:
        raise ValueError('reserve needs a unique annual full-name identity')
    source = copy.deepcopy(replacements[0])
    if source['position'] not in ('D', 'M', 'F') or first['position'] == 'G':
        raise ValueError('bench policy cannot replace a keeper or invent a broad role')
    for _, layer, _ in planner.package_layers(release):
        if any(roster.normalise(p.get('source_name') or p['name']) == roster.normalise(source['name'])
               for p in layer['players']):
            raise ValueError('replacement already exists in a represented squad')
    proofs = []
    anchor = release.season[:4] + '-08-01'
    if primary_alias:
        duplicate_person,duplicate_owner,person,owner,proofs=alias.evidence()
        raw,_ = alias.source_rows('oscar-bobb-original-wikipedia')[1:]
        url=alias.SOURCES['oscar-bobb-original-wikipedia']
    elif biography_provider == 'soccerbase':
        duplicate_raw, duplicate_url = replay.read_original(cache, 'player', duplicate_provider_id, proofs)
        duplicate_person = original.profile(duplicate_raw, {'provider_player_id': duplicate_provider_id,
            'source_player_id': 'soccerbase:' + str(duplicate_provider_id)}, duplicate_url)
        duplicate_owner = career_owner(duplicate_raw, anchor, club['name'])
        raw, url = replay.read_original(cache, 'player', provider_id, proofs)
        person = original.profile(raw, {'provider_player_id': provider_id,
            'source_player_id': 'soccerbase:' + str(provider_id)}, url)
        owner = career_owner(raw, anchor, club['name'])
        person.update(source_provider='soccerbase')
    elif biography_provider == 'wikipedia':
        from scripts import season_wikipedia_career_identity_v1 as wiki
        duplicate_raw, duplicate_url = replay.read_original(cache, 'wiki', duplicate_provider_id, proofs)
        duplicate_person, duplicate_owner = wiki.read(duplicate_raw, duplicate_provider_id, duplicate_url,
            anchor, club['name'], roster.club_group(club), expected_name=names[0])
        raw, url = replay.read_original(cache, 'wiki', provider_id, proofs)
        person, owner = wiki.read(raw, provider_id, url, anchor, club['name'], roster.club_group(club),
                                 allow_entry_month=allow_wikipedia_entry_month, expected_name=source['name'])
    else:
        raise ValueError('unsupported within-club original biography provider')
    if (roster.normalise(duplicate_person['name']), duplicate_person['birth_date']) != (
            roster.normalise(names[0]), first['birth_date']):
        raise ValueError('native copies disagree with original full biography identity')
    if (roster.normalise(person['name']), person['birth_date']) != (
            roster.normalise(source['name']), source['birth_date']):
        raise ValueError('original reserve biography disagrees with target annual full name/DOB')
    if not 12 <= (date.fromisoformat(anchor) - date.fromisoformat(person['birth_date'])).days / 365.2425 <= 50:
        raise ValueError('reserve biography outside season age guard')
    position_review = None
    if reviewed_profile_position is not None:
        if biography_provider != 'wikipedia':
            raise ValueError('profile position review requires the verified original biography')
        position_review = centre_back_review(raw, source['position'], reviewed_profile_position)
        source['position'] = reviewed_profile_position
    # Optional missing annual nationality may use one literal original label.
    # No birthplace, current club or flag guessing; disagreements stay gaps.
    nation_values = []
    for tr in BeautifulSoup(raw, 'lxml').select('tr'):
        cells = tr.find_all(['th', 'td'], recursive=False)
        if len(cells) == 2 and cells[0].get_text(' ', strip=True) == 'Nationality':
            nation_values.append(cells[1].get_text(' ', strip=True))
    nations = {'Northern Ireland': 'NIR', 'Scotland': 'SCO', 'England': 'ENG',
        'Wales': 'WAL', 'Ireland': 'IRL'}
    if not source.get('nationality') and len(nation_values) == 1 and nation_values[0] in nations:
        source['nationality'] = nations[nation_values[0]]
        source['unresolved_fields'] = [f for f in source.get('unresolved_fields', []) if f != 'nationality']
    aliases = None
    if display_game_id is not None:
        if biography_provider != 'soccerbase':
            raise ValueError('original Soccerbase display witness cannot identify a Wikipedia person')
        # A literal past match label can fit a compact native window. It is
        # display evidence only, not a claim about the target opening lineup.
        profile_page = BeautifulSoup(raw, 'lxml')
        games = profile_page.select(f'tr#tpg{int(display_game_id)}')
        if len(games) != 1:
            raise ValueError('display game is not an original appearance of the reserve')
        dates = games[0].select('td.dateTime a[href]')
        if len(dates) != 1:
            raise ValueError('display match needs an original published date')
        result_url = urlparse(dates[0]['href'])
        result_query = parse_qs(result_url.query)
        if result_url.path != '/matches/results.sd' or set(result_query) != {'date'}:
            raise ValueError('display appearance date is not exact')
        date.fromisoformat(result_query['date'][0])
        display_raw, display_url = replay.read_original(cache, 'match', display_game_id, proofs)
        if display_url != f'https://www.soccerbase.com/matches/additional_information.sd?id_game={int(display_game_id)}':
            raise ValueError('display match original URL differs')
        links = BeautifulSoup(display_raw, 'lxml').select(
            f'div.lineup a[href="/players/player.sd?player_id={provider_id}"]')
        if len(links) != 1 or not links[0].get_text(' ', strip=True):
            raise ValueError('display match lacks one literal same-provider player label')
        aliases = {'policy': soccerbase.POLICY,
            'source_provider_person_id': person['source_player_id'],
            'source_person_id': person['source_player_id'], 'birth_date': person['birth_date'],
            'names': [{'field': 'dated-match-label', 'name': links[0].get_text(' ', strip=True)}]}
        # Two-token full name + the exact same surname and matching published
        # given initial establishes these components without inventing an
        # initial expansion, splitting multi-part names or losing a surname.
        person.update(name_components(person['name'], links[0].get_text(' ', strip=True)))
    update = {'layer': 'main', 'player_id': before['id'], 'carrier_id': displaced,
        'club_id': club['id'], 'before': copy.deepcopy(before),
        'retained_owner_player_id': keep['id'], 'retained_carrier_id': retained,
        'owner_evidence': owner, 'duplicate_source_person': duplicate_person,
        'duplicate_owner_evidence': duplicate_owner,
        'replacement_opening_evidence': {'date': anchor, 'policy': POLICY,
            'actual_first_fixture_claimed': False},
        'replacement': {'source_player': source, 'source_person': person,
            'raw_evidence': annual_proof}, 'duplicate_native_before': [first, second]}
    if aliases is not None:
        update['replacement']['source_display_aliases'] = aliases
    if position_review is not None:
        update['replacement']['position_review'] = position_review
    plan = {'schema_version': SCHEMA, 'season': release.season, 'release_id': release.release_id,
        'package_sha256': registry.sha256_file(release.package_path),
        'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
        'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
        'bindings': {'snapshot': {'project_url': url}, 'original_profiles': proofs,
            'annual_capture': capture, 'annual_proof': annual_proof,
            'display_game_id': display_game_id,
            'profile_cache': registry.relative_workspace_path(cache)},
        'updates': [update], 'unresolved': [], 'starting_XI_change_authorised': False,
        'source_title': 'Original dated reserve career bracket and target-season squad; equal native within-club identity',
        'proof_covers': ['native-within-club-equal-DOB-duplicate-and-unused-dated-annual-reserve']}
    if biography_provider == 'wikipedia':
        plan['bindings'].update(biography_provider=biography_provider,
            replacement_slug=provider_id, duplicate_slug=duplicate_provider_id)
        if allow_wikipedia_entry_month:
            plan['bindings']['allow_wikipedia_entry_month'] = True
        if reviewed_profile_position is not None:
            plan['bindings']['reviewed_profile_position'] = reviewed_profile_position
        plan['source_title'] = 'Original Wikipedia interior-year careers and target annual reserve; equal native within-club identity'
    elif primary_alias:
        plan['bindings']['biography_provider']='original-savio-bobb-2024'
        plan['source_title']='Original primary Savio/Savinho alias, dated first-league XI and positive August Bobb reserve; actual unused duplicate carrier only'
    return plan


def verify_plan(release, plan):
    if plan.get('schema_version') != SCHEMA or len(plan['updates']) != 1:
        raise ValueError('unsupported within-club reserve plan')
    row = plan['updates'][0]
    wiki = plan['bindings'].get('biography_provider') == 'wikipedia'
    primary_alias = plan['bindings'].get('biography_provider') == 'original-savio-bobb-2024'
    actual = make_plan(release, row['carrier_id'], row['retained_carrier_id'],
        row['replacement']['source_player']['name'],
        plan['bindings']['replacement_slug'] if wiki else row['replacement']['source_person']['provider_player_id'],
        registry.ROOT / plan['bindings']['profile_cache'],
        duplicate_provider_id=(plan['bindings']['duplicate_slug'] if wiki else
            row['duplicate_source_person']['provider_player_id']),
        display_game_id=plan['bindings']['display_game_id'],
        biography_provider='original-savio-bobb-2024' if primary_alias else ('wikipedia' if wiki else 'soccerbase'),
        allow_wikipedia_entry_month=plan['bindings'].get('allow_wikipedia_entry_month', False),
        reviewed_profile_position=plan['bindings'].get('reviewed_profile_position'))
    if actual != plan:
        raise ValueError('within-club reserve plan does not independently reproduce')


def centre_back_review(raw, annual_position, requested):
    """Explicit broad-role editorial decision, never claim a dated first-XI role."""
    labels = []
    for tr in BeautifulSoup(raw, 'lxml').select('table.infobox tr'):
        cells = tr.find_all(['th', 'td'], recursive=False)
        if len(cells) == 2 and cells[0].get_text(' ', strip=True) == 'Position':
            labels.append(cells[1].get_text(' ', strip=True))
    if requested != 'D' or labels != ['Centre-back']:
        raise ValueError('explicit defender review lacks one literal Centre-back label')
    return {'policy': 'explicit-editorial-broad-role-from-retained-biography',
            'annual_position_before': annual_position, 'profile_position': labels[0],
            'broad_position_after': requested, 'dated_first_fixture_position_claimed': False}
