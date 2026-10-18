"""Country-scoped source timelines for related stale native coach owners.

Resolve the same named club entity in each season, not the same physical
carrier (carriers legitimately change clubs). Correct only actual disagreements;
retain compatible coaches unchanged and leave missing/overlapping dates open.
"""
from datetime import date
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_coupled_manager_club_histories_20261016 as captures
from scripts import remaining_manager_source_package_20261016 as sources
from scripts import audit_deferred_manager_tenures_20261016 as histories
from scripts import season_historical_roster_audit_v1 as roster
from scripts.season_historical_opening_review_v1 import _normalise

ALIASES = {
    26: ('switzerland', ('Basel', 'FC Basel', 'FC Basel 1893')),
    1450: ('peru', ('Sporting Cristal Lima', 'Sporting Cristal', 'Club Sporting Cristal')),
    5619: ('norway', ('Aalesund', 'Aalesunds', 'Aalesunds FK')),
    3725: ('russia', ('Terek Grozny', 'Akhmat Grozny')),
    683: ('greece', ('Olympiakos', 'Olympiacos', 'Olympiakos Piraeus', 'Olympiacos Piraeus')),
    1011: ('sweden', ('Halmstad', 'Halmstads', 'Halmstads BK')),
    496: ('sweden', ('Malmö FF', 'Malmo FF', 'Malmö', 'Malmo')),
    10010: ('brazil', ('Esporte Clube Bahia', 'Bahia', 'EC Bahia')),
    855: ('france', ('Guingamp', 'EA Guingamp', 'En Avant Guingamp')),
    46: ('italy', ('Internazionale', 'Inter', 'Inter Milan', 'FC Internazionale Milano')),
}
TITLES = {26: 'FC Basel 1893', 1450: 'Club Sporting Cristal', 5619: 'Aalesunds FK', 3725: 'Akhmat Grozny', 683: 'Olympiacos Piraeus', 1011: 'Halmstads BK',
    496: 'Malmö FF', 10010: 'Esporte Clube Bahia', 855: 'EA Guingamp', 46: 'Inter Milan'}


def originals():
    path = captures.ROOT / 'capture-summary.json'
    result = []
    documents = [pipeline.read_json_file(path)] + [pipeline.read_json_file(captures.ROOT / name / 'capture-summary.json')
        for name in ('olympiakos', 'halmstad', 'malmo', 'bahia', 'guingamp', 'inter')]
    for row in [r for document in documents for r in document['rows']]:
        if row['status'] != 'original-club-history-captured':
            raise ValueError('coupled original club source missing; no native fallback')
        receipt = registry.ROOT / row['receipt_path']; raw = registry.ROOT / row['path']
        if registry.sha256_file(receipt) != row['receipt_sha256'] or registry.sha256_file(raw) != row['sha256']:
            raise ValueError('coupled original history or download receipt changed')
        saved = pipeline.read_json_file(receipt)
        if saved['url'] != row['url'] or saved['sha256'] != row['sha256']:
            raise ValueError('coupled original download body URL/hash differs')
        result.append(dict(source_club_id=row['source_club_id'], path=row['path'], sha256=row['sha256'], url=row['url'],
            receipt_path=row['receipt_path'], receipt_sha256=row['receipt_sha256']))
    # The Terek/Akhmat entity is already positively identified by the original
    # exact2010 Russian club fixture; its numerical history covers older years.
    old = pipeline.read_json_file(sources.fresh.ROOT / 'capture-summary.json')
    row = next(r for r in old['rows'] if r['club'] == 'Terek Grozny')
    sources.fresh_claim(row)
    download = row['download']
    result.append(dict(source_club_id=3725, path=download['raw_path'], sha256=download['raw_sha256'], url=download['url'],
        receipt_path=download['receipt_path'], receipt_sha256=download['receipt_sha256'],
        original_exact_club_fixture_witness=row['original_case']))
    if {r['source_club_id'] for r in result} != set(ALIASES):
        raise ValueError('exact reviewed first-team source identities changed')
    return result


def exact_native_clubs(package, source_id):
    country, aliases = ALIASES[source_id]; names = {_normalise(n) for n in aliases}
    return [c for c in package['clubs'] if roster.club_group(c) == country
        and _normalise(c['name']) in names and _normalise(c.get('full_name') or c['name']) in names]


def original_roster_owner(base, package, source_id, clubs):
    """Disambiguate labels only with a complete, independently replayed squad.

    An annual squad identifies the club entity, NOT its opening XI. Every
    represented player must have a distinct exact source-name/DOB match and
    the actual native EQ roster must equal the declared roster. A second
    matching carrier remains ambiguous; no first-match or majority heuristic.
    """
    captured, bindings = roster.load_sources(base.season)
    country, aliases = ALIASES[source_id]
    names = {roster.normalise(n) for n in aliases}
    candidates = [r for r in captured if roster.source_group(r['country_catalog']) == country
        and roster.normalise(r['club_name']) in names]
    verifier = roster.SourceVerifier(base.season)
    verified = []
    for row in candidates:
        proof = verifier.verify(row)
        if proof['status'] == 'raw-source-reparsed':
            verified.append((row, proof))
    players = {p['id']: p for p in package['players']}
    matches = []
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in roster.IndexedFDIFile.from_bytes(eq).entries}
    for club in clubs:
        members = [players[pid] for pid in club['roster_player_ids']]
        keys = [roster.person_identity_key(p) for p in members]
        if (len(members) < 11 or any(k is None for k in keys) or len(set(keys)) != len(keys)
                or any(p['club_id'] != club['id'] for p in members)):
            continue
        entry = entries.get(club['carrier_id'])
        native = roster.parse_eq_external_team_roster_payload(
            eq[entry.payload_offset:entry.payload_offset + entry.payload_length], {}) if entry else None
        if native is None or [p.player_record_id for p in native.rows] != [p['carrier_id'] for p in members]:
            raise ValueError('club-entity native roster differs from canonical source candidates')
        for row, proof in verified:
            source_keys = [(roster.normalise(p['name']), p.get('birth_date')) for p in row['players']]
            if all(source_keys.count(key) == 1 for key in keys):
                matches.append((club, dict(policy='complete-exact-person-DOB-original-roster-and-native-EQ-entity-admission-v1',
                    source_club_id=source_id, country=country, source_capture_bindings=bindings,
                    raw_source=proof, all_native_roster_members_matched=len(members),
                    source_club=row['club_name'], source_roster_count=len(source_keys),
                    source_club_season=base.season, native_EQ_sha256=registry.sha256_file(base.game_path / 'DBDAT/EQ98030.FDI'),
                    not_opening_squad_or_other_carrier_approval=True)))
                break
    return matches[0] if len(matches) == 1 else (None, None)


def claims_for(base, package, native_names, already_selected, display_name):
    rows = []; unchanged = []; unresolved = []
    managers = {m['id']: m for m in package['managers']}
    for source in originals():
        sid = source['source_club_id']; clubs = exact_native_clubs(package, sid)
        entity_proof = None
        if len(clubs) > 1:
            owner, entity_proof = original_roster_owner(base, package, sid, clubs)
            unresolved.append(dict(source_club_id=sid, source=source,
                club_ids=[c['id'] for c in clubs], clubs=[c['name'] for c in clubs],
                reason='multiple native club representations need roster/entity ownership resolution; no manager assigned by name-only selection',
                positively_source_owned_club_id=owner['id'] if owner else None,
                other_carrier_entities_remain_open=True, manager_approved=False))
            if owner is None:
                continue
            clubs = [owner]
        if not clubs:
            continue
        club = clubs[0]; manager = managers[club['manager_id']]
        raw = (registry.ROOT / source['path']).read_bytes()
        page = BeautifulSoup(raw, 'html.parser')
        if page.title is None or _normalise(TITLES[sid]) not in _normalise(page.title.get_text(' ', strip=True)):
            raise ValueError('reviewed original first-team club heading differs')
        try:
            claim = histories.tenure(raw, sid, date(int(base.season[:4]), 8, 1))
        except histories.history.ManagerHistoryError as exc:
            unresolved.append(dict(club_id=club['id'], club=club['name'], source_club_id=sid,
                source=source, reason=str(exc), manager_approved=False))
            continue
        alias, method = display_name(claim['manager'])
        if alias is None:
            raise ValueError('coupled source manager requires explicit compact presentation')
        if club['id'] in already_selected:
            if (already_selected[club['id']]['after'], already_selected[club['id']]['source_manager_id']) != (
                    claim['manager'], claim['source_manager_id']):
                raise ValueError('original36 and coupled timeline disagree on current coach identity')
            continue
        observed = native_names[manager['carrier_id']]
        if (_normalise(manager['name']) == _normalise(claim['manager'])
                and _normalise(observed) in (_normalise(claim['manager']), _normalise(alias))):
            unchanged.append(dict(club_id=club['id'], club=club['name'], **claim,
                native_name=observed, source=source, native_or_recipe_write_needed=False))
            continue
        rows.append(dict(club=club, manager=manager, claim=claim, alias=alias, alias_method=method, source=source,
            entity_admission=dict(policy='ROOT-reviewed-country-scoped-complete-club-alias-and-original-numeric-first-team-history-v1',
                source_club_id=sid, country=ALIASES[sid][0], allowed_club_names=list(ALIASES[sid][1]),
                original_club_heading=TITLES[sid], source_club_identity_reviewed=True,
                independent_full_roster_disambiguation=entity_proof,
                club_names_or_memberships_changed=False)))
    return rows, unchanged, unresolved
