"""Read-only visibility QA for current generic opening-exchange identities.

This is an isolated review gate, not a publisher or native writer. It follows
only exchange artifacts in the inspected release package and counts native
owners only when their exact EQ roster row has flag zero.
"""
from __future__ import annotations

import hashlib
import json
import argparse
import sys
from pathlib import Path


def _find_workspace_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if ((parent / 'scripts').is_dir()
                and (parent / 'upstream/pm99-skezmod-db-editor').is_dir()):
            return parent
    raise RuntimeError('PM99 workspace root not found from source-authored visibility gate')


ROOT = _find_workspace_root()
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]

from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


class UnsupportedArtifactSchema(ValueError):
    def __init__(self, artifact: dict, schema):
        self.artifact = artifact
        self.schema = schema
        super().__init__(f"unsupported schema in prefixed artifact {artifact.get('id')}: {schema!r}")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_plan_identity(plan: dict) -> dict:
    transaction = plan.get('transaction_id')
    body = dict(plan)
    body.pop('transaction_id', None)
    if (not isinstance(transaction, str)
            or hashlib.sha256(packages.canonical_json_bytes(body)).hexdigest()[:24] != transaction):
        raise ValueError('transaction plan content does not reproduce its transaction ID')
    source = plan.get('source_input')
    if not isinstance(source, dict) or not isinstance(source.get('path'), str):
        raise ValueError('transaction plan lacks its exact source input binding')
    source_path = _rooted(source['path'])
    source_sha = _sha(source_path)
    if source_sha != source.get('sha256'):
        raise ValueError('transaction source input SHA-256 differs')
    return {'path': source['path'], 'sha256': source_sha}


def _rooted(value: str) -> Path:
    path = (ROOT / value).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _verify_source_bodies(value, verified: list[dict], trail='evidence') -> None:
    """Verify each retained path/hash pair without fetching or modifying it."""
    if isinstance(value, dict):
        path_value = value.get('path') or value.get('local_path')
        sha_value = value.get('sha256') or value.get('source_sha256')
        if path_value is not None or sha_value is not None:
            is_source_container = (isinstance(path_value, str) and sha_value is None
                                   and _rooted(path_value).is_dir())
            if is_source_container:
                pass
            elif not isinstance(path_value, str) or not isinstance(sha_value, str):
                raise ValueError(f'{trail}: source path/hash pair is incomplete')
            else:
                path = _rooted(path_value)
                observed = _sha(path)
                if observed != sha_value:
                    raise ValueError(f'{trail}: retained source body SHA-256 differs: {path_value}')
                verified.append({'path': path_value, 'sha256': observed})
        archive_path, archive_sha = value.get('match_archive_path'), value.get('match_archive_sha256')
        if archive_path is not None or archive_sha is not None:
            if not isinstance(archive_path, str) or not isinstance(archive_sha, str):
                raise ValueError(f'{trail}: match archive path/hash pair is incomplete')
            archive = _rooted(archive_path)
            observed_archive = _sha(archive)
            if observed_archive != archive_sha:
                raise ValueError(f'{trail}: retained match archive SHA-256 differs: {archive_path}')
            verified.append({'path': archive_path, 'sha256': observed_archive, 'kind': 'match-archive'})
        receipt_path, receipt_sha = value.get('receipt_path'), value.get('receipt_sha256')
        if receipt_path is not None or receipt_sha is not None:
            if not isinstance(receipt_path, str) or not isinstance(receipt_sha, str):
                raise ValueError(f'{trail}: source receipt path/hash pair is incomplete')
            receipt = _rooted(receipt_path)
            observed_receipt = _sha(receipt)
            if observed_receipt != receipt_sha:
                raise ValueError(f'{trail}: retained source receipt SHA-256 differs: {receipt_path}')
            verified.append({'path': receipt_path, 'sha256': observed_receipt, 'kind': 'receipt'})
        for key, child in value.items():
            if key not in ('path', 'local_path', 'sha256', 'source_sha256',
                           'match_archive_path', 'match_archive_sha256'):
                _verify_source_bodies(child, verified, f'{trail}.{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _verify_source_bodies(child, verified, f'{trail}[{index}]')


def _identity_tuple(player):
    return (exchange.identity(player), player.get('person_id'))


def _matches_person(player, source_person: dict) -> bool:
    name = source_person.get('name', '')
    birthday = source_person.get('birth_date', '')
    provider = source_person.get('source_provider', '')
    source_id = source_person.get('source_player_id', '')
    if provider == 'transfermarkt' and str(source_id).isdigit():
        expected_id = f'person-transfermarkt-{source_id}'
    elif provider == '11v11' and str(source_id).startswith('11v11:'):
        expected_id = 'person-11v11-' + str(source_id).split(':', 1)[1]
    elif provider == 'wikipedia' and str(source_id).startswith('wikipedia:'):
        expected_id = 'person-wikipedia-' + hashlib.sha256(
            (str(source_id) + '|' + birthday).encode()).hexdigest()[:24]
    elif provider in ('tempofradi', 'hlsz'):
        # Reuse the source adapter's exact provider URL/key validation and its
        # shared person namespace for HLSZ and Tempó identities.
        from scripts import season_tempofradi_whole_roster_v1 as ftc_roster
        expected_id = ftc_roster.person_key(source_person)
    else:
        # Retained source plans can only be matched through a namespace this
        # gate knows how to reproduce exactly.
        return False
    # Provider person ID plus DOB is the matching identity. Native display
    # labels may be abbreviated/transliterated (for example Siggi's original
    # Icelandic profile versus the database's roster label), so expose rather
    # than use the label as a second identity key.
    return player.get('facts', {}).get('birth_date') == birthday and player.get('person_id') == expected_id


def _external_rosters(eq: bytes):
    records = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(eq).entries}
    payloads = ownership.tactics.payloads(eq)
    for club_carrier, payload in payloads.items():
        entry = records.get(club_carrier)
        if entry is None:
            continue
        parsed = parse_eq_external_team_roster_payload(payload, {})
        if parsed is None:
            continue
        yield club_carrier, parsed, entry.payload_offset


def _owner_status(eq: bytes, player_carrier: int, declared_club_carrier: int) -> dict:
    active, dormant = [], []
    for club_carrier, roster, payload_offset in _external_rosters(eq):
        for row in roster.rows:
            if row.player_record_id != player_carrier:
                continue
            target = active if row.flag == 0 else dormant
            target.append({'club_carrier_id': club_carrier, 'flag': row.flag,
                           'mode_byte': roster.mode_byte,
                           'row_flag_offset': payload_offset + row.raw_row_offset})
    return classify_owners(active, dormant, declared_club_carrier)


def classify_owners(active: list[dict], dormant: list[dict], declared_club_carrier: int) -> dict:
    active_clubs = sorted({row['club_carrier_id'] for row in active})
    target_active = [row for row in active if row['club_carrier_id'] == declared_club_carrier]
    target_dormant = [row for row in dormant if row['club_carrier_id'] == declared_club_carrier]
    if len(target_active) == 1 and active_clubs == [declared_club_carrier]:
        status = 'visible-single-active-declared-owner'
    elif target_dormant and not target_active:
        status = 'runner-confirmation-required-flagged-declared-owner'
    elif target_active or active:
        status = 'active-owner-conflict-or-duplicate'
    else:
        status = 'declared-owner-row-missing'
    return {'status': status, 'active_owners': active, 'flagged_owners': dormant,
            'declared_active_rows': target_active, 'declared_flagged_rows': target_dormant}


def _parent_actor(plan, carrier):
    parent = registry.load_registered_release(plan['season'], plan['release_id'])
    package = pipeline.read_json_file(parent.package_path)
    actors = [p for p in package['players'] if p['carrier_id'] == carrier]
    if len(actors) != 1:
        raise ValueError('source parent must contain one actor at the consumed carrier')
    if (registry.sha256_file(parent.package_path) != plan['package_sha256']
            or registry.sha256_file(parent.game_path / 'DBDAT/EQ98030.FDI') != plan['eq_sha256']
            or registry.sha256_file(parent.game_path / 'DBDAT/JUG98030.FDI') != plan['jug_sha256']):
        raise ValueError('exchange source parent package/native hashes differ')
    return parent, package, actors[0]


def _current_target(package, carrier):
    actors = [p for p in package['players'] if p['carrier_id'] == carrier]
    if len(actors) != 1:
        raise ValueError('current package must contain one actor at source carrier')
    clubs = [c for c in package['clubs'] if c['id'] == actors[0]['club_id']]
    if len(clubs) != 1:
        raise ValueError('current source actor must resolve to one declared club')
    return actors[0], clubs[0]


def _new_person_witnesses(request: dict, membership_evidence: dict, selection: dict) -> list[dict]:
    expected_url = membership_evidence.get('match_url')
    expected_date = membership_evidence.get('date')
    evidence = request.get('evidence', {})
    if not expected_url and selection.get('match') in evidence:
        selected = evidence[selection['match']]
        expected_url = selected.get('url') or selected.get('report_url')
        expected_date = selected.get('date')
        if selected.get('path') and selected.get('sha256'):
            return [dict(selected, membership_claim='exact source request match witness',
                         membership_date=expected_date)]
    contract = selection.get('opening_contract', {})
    if contract:
        selected_contract = []
        for field in ('fixture', 'season_roster'):
            key = contract.get(field)
            value = evidence.get(key) if isinstance(key, str) else None
            if isinstance(value, dict) and value.get('path') and value.get('sha256'):
                selected_contract.append(dict(value,
                    membership_claim=f"exact opening_contract {field} source", 
                    membership_date=contract.get('opening_date')))
        if selected_contract:
            return selected_contract
    found = []
    def walk(value):
        if isinstance(value, dict):
            if (value.get('membership_mode') and (value.get('url') == expected_url
                    or value.get('report_url') == expected_url)
                    and value.get('date') == expected_date):
                found.append(value)
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(evidence)
    walk(selection.get('_provider_evidence', {}))
    return found


def _positive_membership(witnesses: list[dict]) -> list[dict]:
    return [w for w in witnesses if isinstance(w, dict)
            and (w.get('membership_mode') or w.get('membership_claim')
                 or w.get('dfb_registration_row') or w.get('opening_contract'))]


def _walsall_membership(request: dict, update: dict) -> tuple[str, list[dict]]:
    carrier = update['carrier_id']
    evidence = request.get('evidence', {})
    if carrier == 21064:
        if (update.get('replacement_opening_evidence', {}).get('date') != '2000-08-12'
                or carrier not in request.get('bench', {}).get('five', [])):
            return '', []
        witness = evidence.get('sky')
        if not witness:
            return '', []
        return 'published-opening-bench-member', [dict(witness, membership_claim='named substitute on 2000-08-12 published team sheet')]
    if carrier == 21065:
        witness = evidence.get('siggi_match')
        claim = update.get('replacement', {}).get('raw_evidence', {}).get('decision', '')
        if (update.get('replacement_opening_evidence', {}).get('date') != '2000-08-22'
                or 'used substitute' not in claim or not witness):
            return '', []
        return 'dated-used-substitute-member', [dict(witness, membership_claim=claim)]
    return '', []


def _audit_exchange(release, package, eq: bytes, artifact: dict) -> list[dict]:
    artifact_path = _rooted(str(release.package_path.parent / artifact['relative_path']))
    raw = artifact_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact.get('sha256'):
        raise ValueError(f"opening exchange artifact hash differs: {artifact['id']}")
    plan = json.loads(raw)
    if plan.get('schema') != exchange.SCHEMA:
        raise UnsupportedArtifactSchema(artifact, plan.get('schema'))
    if plan.get('season') != release.season:
        raise ValueError('opening-exchange artifact season differs from inspected release')
    if artifact['id'] != exchange.PREFIX + plan.get('transaction_id', ''):
        raise ValueError('exchange artifact ID does not bind its transaction')
    source_input_binding = _verify_plan_identity(plan)
    if plan.get('release_id') is None:
        raise ValueError('exchange artifact lacks exact source parent')
    # First identify exact current matches cheaply. Most inherited exchange
    # artifacts are stale by now; their old source trees need not be rehashed.
    prospective = []
    for update in plan.get('updates', []):
        replacement = update.get('replacement', {})
        source_person = replacement.get('source_person')
        if not source_person or (not replacement.get('membership')
                and plan.get('request', {}).get('schema') != 'pm99-walsall-opening-two-person-v4'):
            continue
        if replacement.get('membership') == 'dated-opening-contract-bracket-not-matchday-claim':
            continue
        current, club = _current_target(package, update['carrier_id'])
        if _matches_person(current, source_person):
            prospective.append(('new', update, current, club))
    for decision in plan.get('decisions', []):
        source_carrier = decision.get('preserved_source_carrier')
        if source_carrier is None:
            continue
        current, club = _current_target(package, decision['carrier_id'])
        moved_before = decision.get('moved_before')
        if moved_before is not None and _identity_tuple(current) == _identity_tuple(moved_before):
            prospective.append(('move', decision, current, club))
    if not prospective:
        return []
    # A current identity match makes this artifact relevant. Now bind its exact
    # parent files and source bodies before making an assertion.
    parent = registry.load_registered_release(plan['season'], plan['release_id'])
    if (registry.sha256_file(parent.package_path) != plan['package_sha256']
            or registry.sha256_file(parent.game_path / 'DBDAT/EQ98030.FDI') != plan['eq_sha256']
            or registry.sha256_file(parent.game_path / 'DBDAT/JUG98030.FDI') != plan['jug_sha256']):
        raise ValueError('exchange source parent package/native hashes differ')
    parent_binding = {'release_id': parent.release_id,
        'package_sha256': plan['package_sha256'], 'eq_sha256': plan['eq_sha256'],
        'jug_sha256': plan['jug_sha256']}
    parent_package = pipeline.read_json_file(parent.package_path)
    parent_players = {p['carrier_id']: p for p in parent_package['players']}
    verified_sources = []
    _verify_source_bodies(plan.get('request', {}).get('evidence', {}), verified_sources)
    out = []
    # New source-authored identities are admitted in updates and referenced by
    # the exact source provider identity, not merely a similar display name.
    for kind, item, current, club in prospective:
        if kind != 'new':
            continue
        update = item
        replacement = update['replacement']
        source_person = replacement['source_person']
        membership = replacement.get('membership')
        carrier = update['carrier_id']
        raw_evidence = replacement.get('raw_evidence', {})
        _verify_source_bodies(raw_evidence, verified_sources)
        if plan['request'].get('schema') == 'pm99-walsall-opening-two-person-v4':
            membership, witnesses = _walsall_membership(plan['request'], update)
        else:
            selection = next((row for row in plan['request'].get('new_people', [])
                              if row.get('carrier_id') == carrier), {})
            witnesses = _positive_membership(_new_person_witnesses(
                plan['request'], replacement.get('membership_evidence', {}), selection))
            if (not witnesses and membership and raw_evidence.get('status') == 'raw-source-reparsed'
                    and 'positive' in raw_evidence.get('statement', '').casefold()
                    and raw_evidence.get('event_date')):
                witnesses = [dict(raw_evidence, membership_claim=raw_evidence['statement'])]
        if not witnesses:
            raise ValueError(f"current source-authored new identity lacks positive membership witness: {artifact['id']} carrier {carrier}")
        owners = _owner_status(eq, carrier, next(c['carrier_id'] for c in package['clubs'] if c['id'] == club['id']))
        out.append({'artifact_id': artifact['id'], 'carrier_id': carrier,
            'artifact_path': artifact['relative_path'], 'artifact_sha256': artifact['sha256'],
            'source_parent': parent_binding,
            'person_id': current['person_id'], 'source_name': current.get('source_name') or current['name'],
            'source_identity_name': source_person['name'],
            'source_identity_display_label_matches': exchange.roster.normalise(
                current.get('source_name') or current['name']) == exchange.roster.normalise(source_person['name']),
            'birth_date': current['facts']['birth_date'], 'declared_club_id': club['id'],
            'membership': membership, 'membership_witnesses': witnesses,
            'source_input_binding': source_input_binding,
            'verified_source_bodies': verified_sources, **owners})
    # A moved identity is resolved from the exact source-parent carrier, then
    # matched against the current destination actor. Other dormant rows are
    # reported but never counted as active owners.
    for kind, item, current, club in prospective:
        if kind != 'move':
            continue
        decision = item
        source_carrier = decision['preserved_source_carrier']
        current_carrier = decision['carrier_id']
        source_actor = parent_players.get(source_carrier)
        if source_actor is None:
            raise ValueError('moved identity source carrier absent from exact parent')
        if _identity_tuple(current) != _identity_tuple(source_actor):
            raise ValueError('moved current identity differs from exact source-parent actor')
        request_move = next((m for m in plan['request'].get('moves', [])
                             if m['destination'] == current_carrier and m['source'] == source_carrier), None)
        if request_move is None:
            raise ValueError('moved decision lacks exact request mapping')
        witnesses = []
        expected_name = current.get('source_name') or current['name']
        for value in plan['request'].get('evidence', {}).values():
            if not isinstance(value, dict) or not value.get('membership_mode'):
                continue
            try:
                lineup, bench = exchange.match_people(value)
            except Exception:
                continue
            if any(exchange.roster.normalise(row.get('display_name', row.get('name', '')))
                   == exchange.roster.normalise(expected_name) for row in lineup + bench):
                witnesses.append(value)
        witnesses = _positive_membership(witnesses)
        if not witnesses:
            continue  # ownership/arrival alone does not prove an opening squad member
        owners = _owner_status(eq, current_carrier,
            next(c['carrier_id'] for c in package['clubs'] if c['id'] == club['id']))
        out.append({'artifact_id': artifact['id'], 'carrier_id': current_carrier,
            'artifact_path': artifact['relative_path'], 'artifact_sha256': artifact['sha256'],
            'source_parent': parent_binding,
            'source_parent_carrier': source_carrier, 'person_id': current['person_id'],
            'source_name': current.get('source_name') or current['name'],
            'source_identity_name': source_actor.get('source_name') or source_actor['name'],
            'source_identity_display_label_matches': exchange.identity(current) == exchange.identity(source_actor),
            'birth_date': current['facts']['birth_date'], 'declared_club_id': club['id'],
            'membership': 'moved-source-person-positive-opening-membership',
            'membership_witnesses': witnesses, 'source_input_binding': source_input_binding,
            'verified_source_bodies': verified_sources, **owners})
    return out


def audit_release(season: str, release_id: str) -> dict:
    release = registry.load_registered_release(season, release_id)
    package = pipeline.read_json_file(release.package_path)
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    rows, unsupported = [], []
    artifacts = [a for a in package.get('artifacts', [])
                 if a.get('id', '').startswith(exchange.PREFIX)]
    for artifact in artifacts:
        try:
            rows.extend(_audit_exchange(release, package, eq, artifact))
        except UnsupportedArtifactSchema as exc:
            # _audit_exchange verifies the artifact bytes before examining its
            # schema, so an unknown producer is visible and hash-bound here.
            unsupported.append({'artifact_id': artifact['id'],
                'relative_path': artifact.get('relative_path'),
                'artifact_sha256': artifact.get('sha256'),
                'observed_schema': exc.schema,
                'status': 'unsupported-schema-not-audited'})
    coverage = {'scope': 'generic-opening-identity-exchange-artifacts-only',
        'whole_workspace_complete': False,
        'supported_artifact_schemas': [exchange.SCHEMA],
        'request_adapter_exceptions': ['pm99-walsall-opening-two-person-v4 has an explicit bounded membership reader',
            'FTC whole-roster v3 can be read only via audit_ftc_whole_roster_plan when separately requested'],
        'unsupported_artifact_families': ['all package artifact families outside the opening-identity-exchange prefix',
            'all unrecognized schemas using that prefix'],
        'unsupported_prefixed_artifacts': unsupported,
        'coverage_status': 'unsupported-schema-present' if unsupported else 'scoped-complete-not-global'}
    return {'schema_version': 'pm99-source-authored-visibility-gate-v1',
        'season': season, 'release_id': release_id,
        'current_binding': {'manifest_sha256': release.manifest_sha256,
            'package_sha256': registry.sha256_file(release.package_path),
            'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI')},
        'scope': 'current matching source-authored identities in generic opening-exchange artifacts only; foreign modes are parsed directly; nonzero flags are not globally interpreted as loans or removals',
        'native_writes': 0, 'exchange_artifacts_checked': len(artifacts),
        'matched_current_people': len(rows), 'results': rows, 'coverage': coverage}


def audit_ftc_whole_roster_plan(season: str, release_id: str, plan_path: str) -> dict:
    """Explicit supplementary reader for the retained FTC whole-roster v3 plan."""
    release = registry.load_registered_release(season, release_id)
    plan_file = _rooted(plan_path)
    plan = json.loads(plan_file.read_bytes())
    if (plan.get('schema') != exchange.SCHEMA
            or plan.get('season') != season or len(plan.get('updates', [])) != 20):
        raise ValueError('FTC supplementary visibility input is not the exact v3 twenty-person plan')
    source_input_binding = _verify_plan_identity(plan)
    parent = registry.load_registered_release(season, plan['release_id'])
    if (registry.sha256_file(parent.package_path) != plan['package_sha256']
            or registry.sha256_file(parent.game_path / 'DBDAT/EQ98030.FDI') != plan['eq_sha256']
            or registry.sha256_file(parent.game_path / 'DBDAT/JUG98030.FDI') != plan['jug_sha256']):
        raise ValueError('FTC source parent package/native hashes differ')
    parent_binding = {'release_id': parent.release_id,
        'package_sha256': plan['package_sha256'], 'eq_sha256': plan['eq_sha256'],
        'jug_sha256': plan['jug_sha256']}
    package = pipeline.read_json_file(release.package_path)
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    rows, unmatched = [], []
    for update in plan['updates']:
        carrier = update['carrier_id']
        replacement = update['replacement']
        person = replacement['source_person']
        evidence = replacement['raw_evidence']
        current = next((p for p in package['players'] if p['carrier_id'] == carrier), None)
        if current is None or not _matches_person(current, person):
            current_club = next((c for c in package['clubs'] if current and c['id'] == current['club_id']), None)
            native = (_owner_status(eq, carrier, current_club['carrier_id']) if current and current_club else None)
            unmatched.append({'carrier_id': carrier, 'expected_source_person_id': person['source_player_id'],
                'expected_provider': person['source_provider'], 'expected_name': person['name'],
                'expected_birth_date': person['birth_date'],
                'source_evidence': {'local_path': evidence['local_path'],
                    'source_sha256': evidence['source_sha256'],
                    'match_archive_path': evidence['match_archive_path'],
                    'match_archive_sha256': evidence['match_archive_sha256']},
                'current_person_id': current.get('person_id') if current else None,
                'current_source_name': (current.get('source_name') or current['name']) if current else None,
                'native_visibility_observation_without_identity_match': native})
            continue
        if (evidence.get('status') != 'raw-source-reparsed'
                or evidence.get('statement') != 'positive observed matchday squad membership; not official season registration'
                or not evidence.get('event_date')):
            raise ValueError(f'FTC source membership proof/status differs for current carrier {carrier}')
        verified = []
        _verify_source_bodies({'profile': {'path': evidence['local_path'],
                              'sha256': evidence['source_sha256']},
                'match_archive': {'path': evidence['match_archive_path'],
                                  'sha256': evidence['match_archive_sha256']}}, verified)
        club = next(c for c in package['clubs'] if c['id'] == current['club_id'])
        owners = _owner_status(eq, carrier, club['carrier_id'])
        rows.append({'carrier_id': carrier, 'person_id': current['person_id'],
            'source_parent': parent_binding,
            'source_name': current.get('source_name') or current['name'],
            'source_identity_name': person['name'],
            'source_identity_display_label_matches': exchange.roster.normalise(
                current.get('source_name') or current['name']) == exchange.roster.normalise(person['name']),
            'birth_date': current['facts']['birth_date'], 'declared_club_id': club['id'],
            'membership': evidence['statement'], 'event_date': evidence['event_date'],
            'source_input_binding': source_input_binding,
            'verified_source_bodies': verified, **owners})
    return {'schema_version': 'pm99-source-authored-visibility-gate-v1',
        'season': season, 'release_id': release_id, 'source_plan': plan_path,
        'source_plan_sha256': _sha(plan_file),
        'current_binding': {'manifest_sha256': release.manifest_sha256,
            'package_sha256': registry.sha256_file(release.package_path),
            'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI')},
        'scope': 'exact FTC whole-roster v3 source-admitted carriers still matching current provider identity; observed matchday squad claims only, not season registration',
        'native_writes': 0, 'source_plan_updates': len(plan['updates']),
        'matched_current_people': len(rows), 'unmatched_source_identity_rows': unmatched,
        'results': rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', required=True, help='one exact registered season, e.g. 2000-01')
    parser.add_argument('--release-id', required=True, help='one exact registered release ID')
    parser.add_argument('--output', required=True, help='new workspace-relative JSON receipt path')
    args = parser.parse_args(argv)
    output = _rooted(args.output)
    if output.exists():
        raise ValueError('visibility audit output is immutable and already exists')
    if not output.parent.is_dir():
        raise ValueError('visibility audit output parent directory must already exist')
    result = audit_release(args.season, args.release_id)
    pipeline.write_canonical_json(output, result)
    coverage = result['coverage']
    print(json.dumps({'season': result['season'], 'release_id': result['release_id'],
        'matched_current_people': result['matched_current_people'],
        'unsupported_prefixed_artifacts': len(coverage['unsupported_prefixed_artifacts']),
        'coverage_status': coverage['coverage_status'], 'whole_workspace_complete': False,
        'output': registry.relative_workspace_path(output)}, sort_keys=True))
    return 2 if coverage['unsupported_prefixed_artifacts'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
