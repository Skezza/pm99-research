"""Strict guard composing annual-row identity with existing adjudication.

Official fact parsing remains in season_adjudicated_player_facts_v1. This module
only binds the annual person row to recipe/native identity and prevents the two
HTML witnesses used here from borrowing another profile's DOB/country.
"""
import hashlib
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_opening_order_repair_v1 as ownership
from scripts.season_historical_roster_audit_v1 import native_player, normalise
from scripts.season_within_club_reserve_repair_v1 import native_facts
from scripts.season_source_package_builder_v1 import _source_person_id
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES


def _read_file(binding):
    if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
        raise ValueError('annual identity file binding is malformed')
    path = registry.ROOT / binding['path']
    if (Path(binding['path']).is_absolute() or not path.resolve().is_relative_to(registry.ROOT.resolve())
            or path.is_symlink() or not path.is_file()):
        raise ValueError('annual identity path must be retained workspace file')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != binding.get('sha256'):
        raise ValueError('annual identity retained file digest differs')
    return path


def _json(binding):
    path = _read_file(binding)
    return path, pipeline.read_json_file(path)


def _verified_actor_club(selector_label, package, actor_club_id):
    """Join the annual source club to one exact selected package club label."""
    from scripts import season_official_career_context_v1 as career_source
    selected = [c for c in package.get('clubs', []) if c.get('id') == actor_club_id]
    if len(selected) != 1:
        raise ValueError('recipe club carrier is ambiguous')
    labels = [selected[0].get('name'), selected[0].get('full_name')]
    if (not isinstance(selector_label, str) or not selector_label.strip()
            or any(not isinstance(label, str) or not label.strip() for label in labels)):
        raise ValueError('annual source and selected actor need explicit club labels; review label repair')
    selector_key = career_source._club_identity_key(selector_label)
    keys = [career_source._club_identity_key(label) for label in labels]
    if not selector_key or len(set(keys)) != 1 or keys[0] != selector_key:
        raise ValueError('annual source club and selected actor package club differ; review label repair')
    same_label_clubs = [c for c in package.get('clubs', [])
                        if any(isinstance(c.get(field), str)
                               and career_source._club_identity_key(c[field]) == selector_key
                               for field in ('name', 'full_name'))]
    if len(same_label_clubs) != 1 or same_label_clubs[0].get('id') != actor_club_id:
        raise ValueError('annual source club label is ambiguous in the selected package')
    return labels[1]


def _require_unique_null_dob_name(row, source_club):
    """A null-DOB row without a provider ID must be the only same-name row in its club."""
    provider_id = str(row.get('opening_source_player_id') or '').strip()
    if provider_id:
        return
    name = row.get('facts', {}).get('name')
    if not isinstance(name, str) or not name.strip():
        raise ValueError('null-DOB annual identity needs a full source name')
    same_name = [candidate for candidate in source_club.get('players', [])
                 if candidate.get('facts', {}).get('name') == name]
    if len(same_name) != 1:
        raise ValueError('null-DOB annual name is not unique in its source club; needs another identity fact')


def _profile_context(source, full_name, date_value, official_sources):
    path = _read_file(source['body'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != source.get('sha256'):
        raise ValueError('official subject body hash differs')
    parsed = urlsplit(source.get('url', ''))
    if parsed.scheme != 'https':
        raise ValueError('official subject URL must be HTTPS')
    if not any(x.get('url') == source['url'] and x.get('path') == source['body']['path']
               and x.get('sha256') == source['sha256'] for x in official_sources):
        raise ValueError('subject guard must bind an official fact source in the same witness')
    page = BeautifulSoup(path.read_bytes(), 'lxml')
    text = ' '.join(page.get_text(' ', strip=True).replace('\u00ad', '').split())
    if source.get('profile_family') == 'inter-archive-player-v1':
        if (parsed.hostname != 'www.inter.it'
                or not re.fullmatch(r'/it/archivio_giocatore/[A-Za-z0-9_-]+', parsed.path)):
            raise ValueError('Inter archive source route differs')
        title = ' '.join(page.title.get_text(' ', strip=True).split()) if page.title else ''
        if title != f'{full_name} | Giocatori | F.C. Internazionale | inter.it':
            raise ValueError('Inter archive profile title does not bind the source person')
        cards = page.select('.spec-giocatore')
        if len(cards) != 1:
            raise ValueError('Inter archive profile card is not unique')
        lines = [' '.join(node.get_text(' ', strip=True).split()) for node in cards[0].select('h6')]
        birth_lines = [x for x in lines if x.startswith('Nato a ') and ' il ' in x]
        country_lines = [x for x in lines if x.startswith('Nazionalità: ')]
        if len(birth_lines) != 1 or len(country_lines) != 1:
            raise ValueError('Inter profile needs one DOB and one labeled nationality in its profile card')
        dm = re.fullmatch(r'Nato a .+ il (\d{2}-\d{2}-\d{4})', birth_lines[0])
        cm = re.fullmatch(r'Nazionalità: ([A-Za-zÀ-ÿ ]+)', country_lines[0])
        if not dm or not cm or datetime.strptime(dm.group(1), '%d-%m-%Y').date().isoformat() != date_value:
            raise ValueError('Inter named profile DOB differs from annual identity')
        country_literal = cm.group(1)
        code = NATIONALITY_CODES.get(country_literal)
        api_countries = {x.get('nationality', {}).get('code') for x in official_sources
                         if x.get('provider') == 'premier-league-sdp-player-api'
                         and isinstance(x.get('nationality'), dict)}
        if code is None or code not in api_countries:
            raise ValueError('Inter explicit nationality literal/code conflicts with official API claim')
        return {'profile_family': source['profile_family'], 'full_name': full_name,
                'birth_date': date_value, 'nationality_literal': country_literal,
                'nationality_code': code}
    if source.get('profile_family') == 'realmadrid-legend-profile-v1':
        if (parsed.hostname != 'www.realmadrid.com'
                or not re.fullmatch(r'/en-US/the-club/history/football-legends/[a-z0-9-]+/?', parsed.path)):
            raise ValueError('Real Madrid legend profile route differs')
        sections = page.select('section.rm-web-legend-detail__header__wrapper')
        if len(sections) != 1:
            raise ValueError('Real Madrid named-bio data section is not unique')
        header = sections[0]
        titles = [node.get_text(' ', strip=True).strip() for node in header.select('h1,h2')]
        if len(titles) != 1 or titles[0].casefold() not in {
                full_name.casefold(), full_name.split()[-1].casefold()}:
            raise ValueError('Real Madrid header subject does not identify the requested player')
        cards = header.select('ul.rm-web-legend-detail__header__card')
        if len(cards) != 1:
            raise ValueError('Real Madrid profile facts card is not unique')
        fields = {}
        for item in cards[0].find_all('li', recursive=False):
            labels = item.select('small')
            values = item.select('.rm-web-legend-detail__header__card--item-text > span')
            if len(labels) != 1 or len(values) != 1:
                continue
            label = ' '.join(labels[0].get_text(' ', strip=True).split())
            value = ' '.join(values[0].get_text(' ', strip=True).split())
            if label in ('Full name', 'Date of birth'):
                fields.setdefault(label, []).append(value)
        if (len(fields.get('Full name', [])) != 1
                or fields['Full name'][0] != full_name
                or len(fields.get('Date of birth', [])) != 1):
            raise ValueError('Real Madrid named biography block needs unique labeled full name and DOB')
        try:
            observed_dob = datetime.strptime(fields['Date of birth'][0], '%d/%m/%Y').date().isoformat()
        except ValueError as exc:
            raise ValueError('Real Madrid profile DOB is not a precise day/month/year') from exc
        if observed_dob != date_value:
            raise ValueError('Real Madrid named biography block does not bind exact DOB')
        return {'profile_family': source['profile_family'], 'full_name': full_name,
                'birth_date': date_value}
    raise ValueError('unsupported annual identity source-subject profile family')


def verify(witness):
    """Validate annual-row identity. No match ID, owner mutation or write occurs."""
    policy = witness.get('identity_policy')
    allowed_policies = {'annual-source-row-person-identity-v1',
                        'annual-source-row-with-opening-fixture-provider-id-v1',
                        'annual-source-row-person-identity-null-dob-v1'}
    if policy not in allowed_policies:
        raise ValueError('annual row identity policy is not explicit')
    fixture = witness.get('historical_fixture')
    if (policy == 'annual-source-row-with-opening-fixture-provider-id-v1') != (fixture is not None):
        raise ValueError('fixture evidence is required only by the explicit annual-fixture identity policy')
    annual = witness.get('annual_identity')
    if not isinstance(annual, dict):
        raise ValueError('annual row identity witness is required')
    _, pre = _json(annual['preallocation'])
    _, intake = _json(annual['source_intake'])
    package_path, package = _json(annual['package'])
    jug_path = _read_file(annual['native_jug'])
    eq_path = _read_file(annual['native_eq'])
    textos_path = _read_file(annual['native_textos'])
    base = registry.load_registered_release(annual['season'], annual['release_id'])
    if (base.package_path.resolve() != package_path.resolve()
            or base.game_path.joinpath('DBDAT/JUG98030.FDI').resolve() != jug_path.resolve()
            or base.game_path.joinpath('DBDAT/EQ98030.FDI').resolve() != eq_path.resolve()
            or base.game_path.joinpath('DBDAT/TEXTOS.PKF').resolve() != textos_path.resolve()
            or base.manifest_sha256 != annual['release_manifest_sha256']):
        raise ValueError('annual identity files do not bind the exact registered package/native parent')
    season_label = annual['season'].replace('-', '/')
    if (pre.get('season', {}).get('label') != season_label
            or intake.get('season', {}).get('label') != season_label):
        raise ValueError('annual source artifacts target a different season')
    selector = annual['selector']
    source_birth_date = witness['values']['birth_date']
    null_dob_policy = policy == 'annual-source-row-person-identity-null-dob-v1'
    if null_dob_policy:
        if witness.get('native_before_birth_date') is None:
            raise ValueError('null annual DOB identity still requires an exact native preimage')
        source_birth_date = None
    if fixture is not None:
        source_birth_date = annual.get('source_birth_date')
        if not isinstance(source_birth_date, str):
            raise ValueError('fixture DOB exception requires an explicit old annual-source DOB')
        datetime.strptime(source_birth_date, '%Y-%m-%d')
    selected = []
    for doc in (pre, intake):
        rows = [(club, row) for club in doc.get('source_clubs', []) for row in club.get('players', [])
                if row.get('source_row_sha256') == annual['source_row_sha256']]
        if len(rows) != 1:
            raise ValueError('annual row key must resolve exactly once in each retained artifact')
        club, row = rows[0]
        if row.get('source_row_index') != annual['source_row_index']:
            raise ValueError('annual source row index differs')
        if row.get('facts', {}).get('name') != witness['full_name'] or row.get('facts', {}).get('birth_date') != source_birth_date:
            raise ValueError('annual source row full name/DOB differs')
        if null_dob_policy:
            _require_unique_null_dob_name(row, club)
        observed = club.get('selector', {})
        if any(observed.get(k) != selector.get(k)
               for k in ('club_name', 'country_catalog', 'competition_catalog', 'source_path', 'source_sha256')):
            raise ValueError('annual selector binding differs between source artifacts/request')
        selected.append(row)
    if selected[0] != selected[1]:
        raise ValueError('preallocation/source-intake copies of annual identity row differ')
    fixture_result = None
    if fixture is not None:
        from scripts import season_annual_fixture_identity_bridge_v1 as fixture_bridge
        fixture_result = fixture_bridge.verify_opening_fixture(fixture, annual, witness['full_name'])
    person_id = _source_person_id(selected[0])
    if witness.get('person_id') != person_id:
        raise ValueError('recipe person identity does not derive from the exact annual row')
    actors = [a for a in package.get('players', []) if a.get('carrier_id') == annual['carrier_id']]
    if len(actors) != 1:
        raise ValueError('recipe actor carrier must resolve exactly once')
    actor = actors[0]
    source_artifact_id = f"opening-squad-preallocation-{annual['season']}"
    source_artifacts = [a for a in package.get('artifacts', []) if a.get('id') == source_artifact_id]
    if (len(source_artifacts) != 1
            or source_artifacts[0].get('sha256') != annual['preallocation']['sha256']
            or actor.get('proof') != {'artifact_id': source_artifact_id, 'grade': 'source-captured'}):
        raise ValueError('recipe actor proof must bind its exact annual preallocation artifact')
    if (actor.get('person_id') != person_id or actor.get('source_name') != witness['full_name']
            or (actor.get('facts', {}).get('birth_date') != {'policy': 'preserve-existing-mode1'} if null_dob_policy else actor.get('facts', {}).get('birth_date') != source_birth_date)
            or actor.get('facts', {}).get('nationality') != {'policy': 'preserve-existing-mode1'}
            or actor.get('club_id') != annual['club_id']):
        raise ValueError('recipe actor/name/DOB/country fallback differs from annual identity')
    clubs = [c for c in package.get('clubs', []) if c.get('id') == actor['club_id']]
    if len(clubs) != 1:
        raise ValueError('recipe club carrier is ambiguous')
    verified_source_club = None
    if null_dob_policy:
        from scripts import season_official_career_context_v1 as career_source
        verified_source_club = _verified_actor_club(selector.get('club_name'), package, actor['club_id'])
    jug = jug_path.read_bytes()
    from app.fdi_indexed import IndexedFDIFile
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    entry = entries.get(annual['carrier_id'])
    if entry is None:
        raise ValueError('native indexed profile carrier absent')
    record = native_player(entry.decode_payload(jug), annual['carrier_id'])
    facts = native_facts(jug, annual['carrier_id'])
    if normalise(record['name']) != normalise(actor['name']) or (facts['birth_date'] != witness.get('native_before_birth_date') if null_dob_policy else facts['birth_date'] != source_birth_date):
        raise ValueError('native full-name projection/DOB does not agree with exact annual/native preimage')
    if ownership.native_owners(eq_path.read_bytes()).get(annual['carrier_id']) != {clubs[0]['carrier_id']}:
        raise ValueError('native EQ owner differs; this is an unchanged preimage only')
    country_table = compiler._extract_country_codes_from_textos(textos_path)
    country_byte = jug[entry.payload_offset + record['name_end'] + 8]
    if country_byte not in set(country_table.values()):
        raise ValueError('native country preimage does not map through exact parent TEXTOS')
    if null_dob_policy:
        parsed_contexts = career_source.verify_official_career_contexts(
            witness, annual, source_club=verified_source_club)
    else:
        contexts = witness.get('official_subject_contexts', [])
        if len(contexts) < 1:
            raise ValueError('strict named HTML source-context guards required where HTML facts are used')
        parsed_contexts = [_profile_context(s, witness['full_name'], witness['values']['birth_date'],
                                            witness['official_sources']) for s in contexts]
    return {'person_id': person_id, 'full_name': witness['full_name'],
        'birth_date': witness['values']['birth_date'], 'source_row_sha256': annual['source_row_sha256'],
        'native_display_name': record['name'], 'native_country_byte': country_byte,
        'native_country_label': next(k for k, v in country_table.items() if v == country_byte),
        'club_owner_preimage': clubs[0]['carrier_id'], 'source_contexts': parsed_contexts,
        'fixture_provider_player_id': (fixture_result['provider_player_id'] if fixture_result else None),
        'historical_fixture': fixture_result, 'ownership_claim': 'none'}
