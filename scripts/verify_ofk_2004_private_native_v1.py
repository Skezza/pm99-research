"""Independent reader-side proof for the private OFK source candidate."""
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import prepare_duplicate_whole_club_native_v1 as native
from app.editor_actions import _read_native_dd6360_fields
from app.player_initial_order import read_initial_order
from app.ent_manager_profiles import parse_indexed_ent_manager_profile

EXCLUSIVE_NATIVE_SCHEMAS = frozenset(
    f'pm99-private-original-{source}-verified-inputs-v1'
    for source in ('tachira2014', 'tachira2015', 'jedinstvo2005', 'borac2003',
                   'italchacao2001', 'hajduk2002', 'monagas2003', 'monagas2002', 'sartid2000', 'estudiantes2000', 'mladost2001'))


def requires_exclusive_native_ownership(proposal):
    """Use one adapter policy for the actual check and its evidence flag."""
    return proposal.get('schema_version') in EXCLUSIVE_NATIVE_SCHEMAS


def verify_native_owners(eq, ordered, carrier):
    """Prove actual ownership from every readable native EQ roster, not JSON."""
    owners = {id: set() for id in ordered}
    for entry in native.IndexedFDIFile.from_bytes(eq).entries:
        raw = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
        roster = native.parse_eq_external_team_roster_payload(raw, {})
        if roster is None:
            if len(raw) >= 600 and raw[0x29] in (0, 1):
                raise ValueError('unreadable native roster prevents ownership readback')
            continue
        for row in roster.rows:
            if row.player_record_id in owners:
                owners[row.player_record_id].add(entry.record_id)
    if any(value != {carrier} for value in owners.values()):
        raise ValueError('actual native player ownership is missing or cross-club duplicated')
    return True


def verify(candidate, output, *, proposal_path=None, source_bound_game=False):
    if output.exists(): raise ValueError('native readback evidence is immutable')
    receipt_path = candidate / ('candidate-receipt.json' if source_bound_game else 'native-proof.json')
    receipt = pipeline.read_json_file(receipt_path)
    if receipt['registered'] or receipt['publication_authorised'] or receipt.get('duplicate_case_closed', False):
        raise ValueError('source candidate falsely claims publication')
    if source_bound_game:
        from scripts import season_foreign_fixed_roster_delta_v1 as foreign
        if receipt.get('schema_version') != foreign.SCHEMA:
            raise ValueError('unsupported source-bound foreign candidate receipt')
        plan_path = candidate / foreign.FILENAME
        if registry.sha256_file(plan_path) != receipt['plan_sha256']:
            raise ValueError('source-bound foreign plan changed')
        foreign.verify_plan(pipeline.read_json_file(plan_path))
    proposal_path = proposal_path or source.AUDIT / 'ofk-2004-fixed18-private-allocation-v1.json'
    if registry.sha256_file(proposal_path) != receipt['source_proposal_sha256']:
        raise ValueError('source allocation receipt changed')
    proposal = pipeline.read_json_file(proposal_path)
    borac = proposal.get('schema_version') == 'pm99-private-original-borac2003-verified-inputs-v1'
    italchacao = proposal.get('schema_version') == 'pm99-private-original-italchacao2001-verified-inputs-v1'
    hajduk = proposal.get('schema_version') == 'pm99-private-original-hajduk2002-verified-inputs-v1'
    monagas = proposal.get('schema_version') in ('pm99-private-original-monagas2003-verified-inputs-v1', 'pm99-private-original-monagas2002-verified-inputs-v1')
    jedinstvo=proposal.get('schema_version')=='pm99-private-original-jedinstvo2005-verified-inputs-v1'
    tachira_2015=proposal.get('schema_version')=='pm99-private-original-tachira2015-verified-inputs-v1'
    tachira = tachira_2015 or proposal.get('schema_version') == 'pm99-private-original-tachira2014-verified-inputs-v1'
    if proposal.get('schema_version') == 'pm99-private-original-mladost2001-verified-inputs-v1':
        import tempfile
        from pathlib import Path
        from scripts import prepare_mladost_2001_verified_inputs_v1 as inputs
        with tempfile.TemporaryDirectory(prefix='pm99-mladost-native-readback-') as temporary:
            original=inputs.prepare(Path(temporary)/'source.json',proposal['baseline_release_id'])
        expected_name,expected_ground,expected_manager='Mladost Apatin','Stadion Mladosti','Dragi Bogić'
        native_manager='Bogic';count,carrier=18,706
    elif proposal.get('schema_version') == 'pm99-private-original-estudiantes2000-verified-inputs-v1':
        import tempfile
        from pathlib import Path
        from scripts import prepare_estudiantes_2000_verified_inputs_v1 as inputs
        with tempfile.TemporaryDirectory(prefix='pm99-estudiantes-native-readback-') as temporary:
            original=inputs.prepare(Path(temporary)/'source.json',proposal['baseline_release_id'])
        expected_name,expected_ground,expected_manager='Estudiantes de Mérida','Guillermo Soto Rosa','Antonio D’Accorso'
        native_manager="D'Accorso";count,carrier=16,2953
    elif proposal.get('schema_version') == 'pm99-private-original-sartid2000-verified-inputs-v1':
        import tempfile
        from pathlib import Path
        from scripts import prepare_sartid_2000_verified_inputs_v1 as inputs
        with tempfile.TemporaryDirectory(prefix='pm99-sartid-native-readback-') as temporary:
            original=inputs.prepare(Path(temporary)/'source.json',proposal['baseline_release_id'])
        expected_name,expected_ground,expected_manager='Sartid Smederevo','Gradski stadion','Slobodan Dogandžić'
        native_manager='Dogandzic';count,carrier=18,706
    elif proposal.get('schema_version') == 'pm99-private-original-monagas2002-verified-inputs-v1':
        import tempfile
        from pathlib import Path
        from scripts import prepare_monagas_2002_verified_inputs_v1 as monagas_inputs
        with tempfile.TemporaryDirectory(prefix='pm99-monagas2002-native-readback-') as temporary:
            original=monagas_inputs.prepare(Path(temporary)/'source.json',proposal['baseline_release_id'])
        expected_name,expected_ground,expected_manager='Monagas SC','Estadio Alexander Bottini','Eduardo Borrero'
        native_manager='Borrero';count,carrier=16,2953
    elif monagas:
        import tempfile
        from pathlib import Path
        from scripts import prepare_monagas_2003_verified_inputs_v1 as monagas_inputs
        with tempfile.TemporaryDirectory(prefix='pm99-monagas-native-readback-') as temporary:
            original=monagas_inputs.prepare(Path(temporary)/'source.json',proposal['baseline_release_id'])
        expected_name,expected_ground,expected_manager='Monagas SC','Estadio Alexander Bottini','Daniel Lanata'
        native_manager='Lanata';count,carrier=16,2953
    elif hajduk:
        import tempfile
        from pathlib import Path
        from scripts import prepare_hajduk_2002_verified_inputs_v1 as hajduk_inputs
        with tempfile.TemporaryDirectory(prefix='pm99-hajduk-native-readback-') as temporary:
            original=hajduk_inputs.prepare(Path(temporary)/'source.json',proposal['baseline_release_id'])
        expected_name,expected_ground,expected_manager='Hajduk Kula','Gradski stadion','Miloljub Ostojić'
        native_manager='Ostojic';count,carrier=18,706
    elif italchacao:
        import tempfile
        from pathlib import Path
        from scripts import prepare_italchacao_2001_verified_inputs_v1 as ital_inputs
        with tempfile.TemporaryDirectory(prefix='pm99-italchacao-native-readback-') as temporary:
            original=ital_inputs.prepare(Path(temporary)/'source.json',proposal['baseline_release_id'])
        expected_name,expected_ground,expected_manager='Deportivo Italchacao','Olimpico de la UCV','Raúl Cavallieri'
        native_manager='Cavallieri'
        count,carrier=16,2953
    elif borac:
        import tempfile
        from pathlib import Path
        from scripts import prepare_borac_2003_verified_inputs_v1 as borac_inputs
        with tempfile.TemporaryDirectory(prefix='pm99-borac-native-readback-') as temporary:
            original = borac_inputs.prepare(Path(temporary) / 'source.json', proposal['baseline_release_id'],
                fallback_defaults=proposal['secondary_fact_review']['policy'] in (borac_inputs.EDITORIAL_POLICY, borac_inputs.STABLE_SKILLS_POLICY),
                preserve_skills=proposal['secondary_fact_review']['policy'] == borac_inputs.STABLE_SKILLS_POLICY)
        expected_name, expected_ground, expected_manager = 'Borac Cacak', 'Gradski stadion', 'Radovan Gudurić'
        native_manager = 'Guduric'
        count, carrier = 18, 706
    elif jedinstvo:
        import tempfile
        from pathlib import Path
        from scripts import prepare_jedinstvo_2005_verified_inputs_v1 as jedinstvo_inputs
        with tempfile.TemporaryDirectory(prefix='pm99-jedinstvo-native-readback-') as temporary:
            original=jedinstvo_inputs.prepare(Path(temporary)/'source.json',proposal['baseline_release_id'])
        expected_name,expected_ground,expected_manager='Jedinstvo Bijelo Polje','Gradski stadion','Sava Kovačević'
        native_manager='Kovacevic'
        count,carrier=18,706
    elif tachira:
        import tempfile
        from pathlib import Path
        if tachira_2015:
            from scripts import prepare_tachira_2015_verified_inputs_v1 as tachira_inputs
        else:
            from scripts import prepare_tachira_2014_verified_inputs_v1 as tachira_inputs
        with tempfile.TemporaryDirectory(prefix='pm99-tachira-native-readback-') as temporary:
            original = tachira_inputs.prepare(Path(temporary)/'source.json', proposal['baseline_release_id'])
        expected_name, expected_ground, expected_manager = 'Deportivo Tachira', 'Pueblo Nuevo', 'Daniel Farías'
        native_manager = 'Farias'
        count, carrier = 16, 2953
    else:
        original = source.replay_sources(secondary_facts=bool(proposal.get('secondary_fact_review')))
        expected_name, expected_ground, expected_manager = 'OFK Beograd', 'Omladinski stadion', 'Branko Babic'
        native_manager = 'Babic'
        count, carrier = 18, 706
    if any(original[key] != proposal[key] for key in original):
        raise ValueError('source allocation no longer reproduces from originals')
    package = pipeline.read_json_file(candidate / 'season-package.json')
    if source_bound_game and registry.sha256_file(candidate / 'season-package.json') != receipt['recipe_sha256']:
        raise ValueError('source-bound foreign recipe changed')
    native.package_v2.validate_package(package)
    baseline = registry.load_registered_release(proposal['season'], receipt['baseline_release_id'])
    data = {}
    for name, digest in receipt['native_hashes'].items():
        path = candidate / ('game/DBDAT' if source_bound_game else 'DBDAT') / name
        if registry.sha256_file(path) != digest: raise ValueError('private native file changed')
        if not source_bound_game and registry.sha256_file(baseline.game_path / 'DBDAT' / name) != receipt['baseline_hashes'][name]:
            raise ValueError('private baseline native file changed')
        data[name] = path.read_bytes()
    club = next(c for c in package['clubs'] if c['carrier_id'] == carrier)
    eq = data['EQ98030.FDI']
    entry = next(e for e in native.IndexedFDIFile.from_bytes(eq).entries if e.record_id == carrier)
    roster = native.parse_eq_external_team_roster_payload(eq[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
    players = {p['id']: p for p in package['players']}
    ordered = [players[id]['carrier_id'] for id in club['roster_player_ids']]
    if requires_exclusive_native_ownership(proposal):
        verify_native_owners(eq, ordered, carrier)
    assigned = {row['replacement']['source_person']['source_player_id']: row for row in proposal['allocation']}
    if (roster is None or roster.mode_byte != 1 or roster.short_name != expected_name
            or roster.full_club_name != expected_name or roster.stadium_name != expected_ground
            or [(r.flag, r.player_record_id) for r in roster.rows] != [(0, id) for id in ordered]):
        raise ValueError('actual native target club/ground/roster differs from source recipe')
    jug = data['JUG98030.FDI']
    entries = {e.record_id: e for e in native.IndexedFDIFile.from_bytes(jug).entries}
    baseline_jug = (baseline.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    baseline_entries = {e.record_id: e for e in native.IndexedFDIFile.from_bytes(baseline_jug).entries}
    countries = native.delta.compiler._extract_country_codes_from_textos(baseline.game_path / 'DBDAT/TEXTOS.PKF')
    rows = []
    for n, (player_id, desired) in enumerate(zip(club['roster_player_ids'], original['desired_people']), 1):
        player = players[player_id]
        source_id = desired['source_person']['source_player_id']
        allocation = assigned[source_id]
        from scripts import season_soccerbase_duplicate_source_policy_v1 as person_namespace
        if (player['id'] != allocation['player_id'] or player['carrier_id'] != allocation['carrier_id']
                or player['person_id'] != person_namespace.person_id(desired['source_person'])
                or player['name'] != allocation['display']['display_name']):
            raise ValueError('native carrier/person/display is outside the original exact allocation')
        raw = entries[player['carrier_id']].decode_payload(jug)
        if raw[2:5] != bytes.fromhex('dd6360'):
            raise ValueError('compact foreign readback cannot decode an extended player record')
        actual = native.source.roster.native_player(raw, player['carrier_id'])
        field = _read_native_dd6360_fields(raw, actual['name_end'])
        date = f"{field['birth_year']:04d}-{field['birth_month']:02d}-{field['birth_day']:02d}"
        source_birthday=desired['source_person']['birth_date']
        if source_birthday is None:
            from scripts import season_original_fixture_display_v1 as fixture_display
            if desired['source_person'].get('identity_policy') in ('original-Monagas2003-person-ID-and-explicit-unpublished-DOB-v1', 'original-Monagas2002-person-ID-and-explicit-unpublished-DOB-v1'):
                from scripts import season_monagas_2003_missing_birthday_v1 as missing
                missing.verify(desired['source_person'])
            else:
                fixture_display.verify_actor(desired['source_person'])
            old_payload=baseline_entries[player['carrier_id']].decode_payload(baseline_jug)
            old_end=native.source.roster.native_player(old_payload,player['carrier_id'])['name_end']
            if (player['facts']['birth_date']!={'policy':'preserve-existing-mode1'} or
                    raw[actual['name_end']+12:actual['name_end']+16]!=old_payload[old_end+12:old_end+16]):
                raise ValueError('surname actor unknown birthday did not preserve declared native fallback')
        elif date != source_birthday or date != player['facts']['birth_date']:
            raise ValueError('actual native biography birthday differs from original source')
        # The established native name writer uppercases the surname string.
        # Permit case only: do not strip initials, punctuation or accents.
        if (actual['name'].casefold() != player['name'].casefold() or player['source_name'] != desired['source_person']['name']
                or actual['position'] != desired['source_player']['position']
                or {r for r in actual['roles'] if r != 98} != set(player['facts']['fine_roles'])
                or read_initial_order(raw).order != n):
            raise ValueError('actual native biography/role/order differs from original source')
        rating = player['ratings']['values']
        if field['skills'] != [rating[k] for k in native.delta.compiler.SKILLS] or field['handling'] != rating['handling']:
            raise ValueError('actual native skills differ from deterministic recipe')
        if field['visible_nationality_code'] != native.delta.compiler._country_code(player['facts']['nationality'], dict(countries)):
            raise ValueError('actual native nationality fallback differs from recipe')
        for key in ('height_cm', 'weight_kg'):
            expected = desired['source_player'].get(key)
            if isinstance(expected, int) and (player['facts'][key] != expected or field[key] != expected):
                raise ValueError('native secondary fact differs from the declared source/fallback recipe')
            if borac and expected is None:
                old_raw = baseline_entries[player['carrier_id']].decode_payload(baseline_jug)
                old_person = native.source.roster.native_player(old_raw, player['carrier_id'])
                old_fields = _read_native_dd6360_fields(old_raw, old_person['name_end'])
                if player['facts'][key] != {'policy': 'preserve-existing-mode1'} or field[key] != old_fields[key]:
                    raise ValueError('declared unavailable secondary fact did not preserve the seed slot')
        rows.append(dict(carrier_id=player['carrier_id'], source_player_id=desired['source_person']['source_player_id'],
            name=actual['name'], source_name=player['source_name'], birth_date=date,
            position=actual['position'], startup_order=n, handling=field['handling']))
        if source_birthday is None:
            rows[-1].update(birth_date_historically_sourced=False,
                birth_date_policy='explicit-native-field-fallback-not-source-person-birthday',
                first_name_unknown=not monagas)
    if len(rows) != count or len({r['source_player_id'] for r in rows}) != count or rows[0]['position'] != 'G':
        raise ValueError('actual native fixed roster is not18 unique sourced people')
    if sum(r['position'] == 'G' for r in rows[:11]) != 1:
        raise ValueError('actual native opening XI has multiple keepers')
    ent = data['ENT98030.FDI']
    manager = next(m for m in package['managers'] if m['id'] == club['manager_id'])
    entry = next(e for e in native.IndexedFDIFile.from_bytes(ent).entries if e.record_id == manager['carrier_id'])
    profile = parse_indexed_ent_manager_profile(
        ent[entry.payload_offset:entry.payload_offset + entry.payload_length], record_id=manager['carrier_id'])
    if profile.display_name != native_manager or profile.surname != native_manager or manager['name'] != expected_manager:
        raise ValueError('actual native coach differs from dated original')
    for name, ids in [('JUG98030.FDI', set(ordered)), ('EQ98030.FDI', {carrier}), ('ENT98030.FDI', {manager['carrier_id']})]:
        native.preserve_other_records((baseline.game_path / 'DBDAT' / name).read_bytes(), data[name], ids)
    keys = [(r['source_name'], r['birth_date']) for r in rows]
    collisions = [dict(carrier_id=p['carrier_id'], club_id=p['club_id'], name=p.get('source_name') or p['name'])
        for p in package['players'] if p['club_id'] != club['id']
        and ((p.get('source_name') or p['name']), p['facts'].get('birth_date')) in keys]
    proof = dict(schema_version='pm99-private-foreign-independent-native-readback-v1',
        source_allocation_replayed=True, players=rows, source_people_unique=True,
        native_manager=native_manager, native_ground=roster.stadium_name,
        unrelated_native_records_byte_identical=True, cross_club_same_name_DOB_candidates=collisions,
        source_candidate_receipt_sha256=registry.sha256_file(receipt_path),
        package_sha256=registry.sha256_file(candidate / 'season-package.json'),
        native_hashes=receipt['native_hashes'], source_bound_complete_game=source_bound_game,
        registered=False, runtime_verified=False, historical_clearance=False,
        scope=f'Exact native{count} identities/DOB/broad roles/order/skills/coach/ground only. No historical fine-role/secondary-fact/kit/tactics approval.')
    if requires_exclusive_native_ownership(proposal):
        proof['all_selected_native_ownership_exclusive'] = True
    pipeline.write_canonical_json(output, proof)
    return proof


if __name__ == '__main__':
    verify(source.AUDIT / 'ofk-2004-private-native-v1', source.AUDIT / 'ofk-2004-independent-native-readback-v1.json')
