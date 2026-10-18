import struct

from app.models import PlayerRecord

from scripts.pm99_season_qa_v1 import _normalise, audit_recipe


def test_manager_proof_label_alone_is_not_independent_verification():
    from scripts.pm99_season_qa_v1 import verified_manager_plan_rows
    assert verified_manager_plan_rows('2025-26', {'artifacts': [{'id': 'world-2015-club-metadata-dispositions'}]}) == ({}, None)


def test_explicit_roles_are_checked_but_preserve_is_not_certification(tmp_path):
    from scripts.pm99_season_qa_v1 import audit_compiled_roles
    from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6361_player_payload
    dbdat = tmp_path / 'DBDAT'
    dbdat.mkdir()
    jug = dbdat / 'JUG98030.FDI'
    jug.write_bytes(_indexed_fdi([(1, '', _dd6361_player_payload(1, role=3))]))
    p = {'players': [{'id': 'player-1', 'carrier_id': 1,
                     'facts': {'primary_position': 'F', 'fine_roles': [11]}}]}
    assert audit_compiled_roles(p, game=tmp_path)['failure_count'] == 1
    p['players'][0]['facts']['fine_roles'] = {'policy': 'preserve-existing-mode1'}
    report = audit_compiled_roles(p, game=tmp_path)
    assert report['failure_count'] == 0
    assert report['unresolved_role_count'] == report['inherited_conflict_count'] == 1


def test_native_identity_qa_catches_cloned_donor_id(tmp_path):
    from scripts.pm99_season_qa_v1 import audit_compiled_player_identities
    from scripts.test_season_package_compiler_v2 import _indexed_fdi
    from app.indexed_jug_identity import rebind_indexed_player_id
    payload = b'\x40\x00\xdd\x63\x61' + bytes(v ^ 0x61 for v in (7952).to_bytes(2, 'little')) + b'opaque tail'
    dbdat = tmp_path / 'DBDAT'
    dbdat.mkdir()
    jug = dbdat / 'JUG98030.FDI'
    jug.write_bytes(_indexed_fdi([(7952, '', payload), (33191, '', payload)]))
    report = audit_compiled_player_identities(game=tmp_path)
    assert report['failure_count'] == 1
    assert report['failures'] == [{'directory_id': 33191, 'native_id': 7952}]
    jug.write_bytes(_indexed_fdi([(7952, '', payload), (33191, '',
        rebind_indexed_player_id(payload, 33191, expected_id=7952))]))
    assert audit_compiled_player_identities(game=tmp_path)['failure_count'] == 0


def _package(*, handling: int = 8, position: str = "M", birth_date: str = "1980-01-01"):
    values = {
        "quality": 60, "speed": 62, "stamina": 64, "aggression": 60,
        "passing": 65, "tackling": 55, "heading": 50, "shooting": 58,
        "dribbling": 63, "handling": handling,
    }
    players = []
    for index in range(11):
        player_position = "G" if index == 0 else position
        player_values = {**values, "handling": 60 if player_position == "G" else handling}
        players.append({
            "id": f"player-{index}", "name": f"Player {index}", "club_id": "club-1",
            "facts": {"primary_position": player_position, "birth_date": birth_date, "height_cm": 180, "weight_kg": 75, "nationality": "ENG"},
            "ratings": {"values": player_values, "provenance": {"method": "deterministic editorial rating model v1"}},
        })
    return {
        "clubs": [{"id": "club-1", "name": "Example", "opening": {"starting_xi_player_ids": [row["id"] for row in players]}}],
        "players": players,
    }


def test_recipe_accepts_position_plausible_handling():
    report = audit_recipe(_package(), season="2004-05")
    assert report["rating_failure_count"] == 0
    assert report["lineup_failure_count"] == 0


def test_recipe_rejects_outfield_goalkeeper_handling():
    report = audit_recipe(_package(handling=81), season="2004-05")
    assert report["rating_failure_count"] == 10
    assert all(row["reason"] == "outfield-handling-above-20" for row in report["rating_failures"])


def test_recipe_rejects_future_birth_date():
    report = audit_recipe(_package(birth_date="2005-01-01"), season="2004-05")
    assert report["date_failure_count"] == 11


def test_recipe_accepts_contract_boundary_ratings_for_preserved_unknown_rows():
    package = _package()
    player = package["players"][1]
    player["facts"]["primary_position"] = {"policy": "preserve-existing-mode1"}
    player["ratings"]["values"] = {field: 0 for field in player["ratings"]["values"]}
    package["players"][2]["ratings"]["values"]["quality"] = 100

    report = audit_recipe(package, season="2004-05")

    assert report["rating_failure_count"] == 0


def test_storage_transliteration_is_not_a_manager_mismatch():
    assert _normalise("Arsène Wenger") == _normalise("Arsene Wenger")
    assert _normalise("Abdullah Avcı") == _normalise("Abdullah Avci")


def test_dd6361_nationality_roundtrip_uses_parser_backed_field():
    surname, display = "TESTIMITANU", "Ivan TESTIMITANU"
    prefix = (
        bytes([len(surname) ^ 0x61, 0x61]) + surname.encode("ascii")
        + bytes([len(display) ^ 0x61, 0x61]) + display.encode("ascii")
    )
    payload = bytearray(struct.pack("<H", 42) + b"\xdd\x63\x61" + prefix)
    anchor = len(payload)
    fields = [10, 0, 1, 2, 3, 4, 5, 6, 30, 1, 5, 2, 16, 11, 1974 & 0xFF, 1974 >> 8, 170, 68]
    payload.extend(bytes(value ^ 0x61 for value in fields))
    payload.extend(b"\x60" * 80)
    parsed = PlayerRecord.from_bytes(bytes(payload), 0)
    assert parsed.nationality == 30

    changed = parsed
    changed.set_nationality(9)
    assert PlayerRecord.from_bytes(changed.to_bytes(), 0).nationality == 9


def test_registered_kit_patch_requires_bound_receipt_and_outputs(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import pytest
    from scripts import pm99_season_qa_v1 as qa

    monkeypatch.setattr(qa, "ROOT", tmp_path)
    game = tmp_path / "game"
    (game / "DBDAT").mkdir(parents=True)
    archive = game / "DBDAT/MINIESC.PKF"
    archive.write_bytes(b"new-kit")
    application = tmp_path / "application.json"
    application.write_text(json.dumps({"season": "2022-23", "unrelated_files_unchanged": True,
        "difference": {"changed": [{"path": "DBDAT/MINIESC.PKF", "left": {"sha256": "0" * 64},
                                    "right": {"sha256": qa._sha256(archive)}}]}}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"external_artifacts": [{"sha256": qa._sha256(application),
                                                          "size": application.stat().st_size}]}))
    chain = tmp_path / "chain.json"
    chain.write_text(json.dumps({"stages": [{"receipt_sha256": qa._sha256(application),
        "outputs": {"DBDAT/MINIESC.PKF": qa._sha256(archive)}}]}))
    release = SimpleNamespace(locator={"portrait_patch_application_path": "application.json"},
        release_manifest_path=manifest, manifest_sha256=qa._sha256(manifest), build_chain_path=chain)
    monkeypatch.setattr(qa.release_registry, "load_preferred_release", lambda season: release)
    assert qa._registered_kit_patch_hashes("2022-23", game)["MINIESC.PKF"]["before"] == "0" * 64
    archive.write_bytes(b"unrecorded-change")
    with pytest.raises(qa.QaError, match="differs"):
        qa._registered_kit_patch_hashes("2022-23", game)
    archive.write_bytes(b"new-kit")
    application.write_text(application.read_text() + " ")
    with pytest.raises(qa.QaError, match="hash-bound"):
        qa._registered_kit_patch_hashes("2022-23", game)


def test_ownership_no_photo_delta_must_preserve_all_kit_ancestry(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import pytest
    from scripts import pm99_season_qa_v1 as qa

    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.release_registry, 'LOCAL_ROOT', tmp_path)
    previous = tmp_path / 'releases/2022-23/old/build-chain.json'
    previous.parent.mkdir(parents=True)
    outputs = {'DBDAT/' + name: str(index) * 64 for index, name in enumerate(
        ('MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF'), 1)}
    previous.write_text(json.dumps({'season': '2022-23', 'stages': [{'id': 'kits', 'outputs': outputs}]}))
    current = tmp_path / 'current.json'
    def bind(values):
        current.write_text(json.dumps({'season': '2022-23', 'stages': [{
            'id': 'bounded-portrait-fallback-and-unchanged-assets',
            'source_build_chain_sha256': qa._sha256(previous), 'outputs': values}]}))
    bind(outputs)
    release = SimpleNamespace(build_chain_path=current)
    manifest = {'external_artifacts': [{'sha256': qa._sha256(previous), 'size': previous.stat().st_size}]}
    assert qa._artwork_chain_through_unchanged_role_deltas('2022-23', release, manifest)['stages'][0]['id'] == 'kits'
    bind({**outputs, 'DBDAT/NANOESC.PKF': 'changed'})
    with pytest.raises(qa.QaError, match='changed inherited kit'):
        qa._artwork_chain_through_unchanged_role_deltas('2022-23', release, manifest)
    bind(outputs)
    with pytest.raises(qa.QaError, match='not hash-bound'):
        qa._artwork_chain_through_unchanged_role_deltas('2022-23', release, {})


def test_portrait_only_release_retains_hash_bound_ancestor_kit_patch(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from scripts import pm99_season_qa_v1 as qa

    monkeypatch.setattr(qa, "ROOT", tmp_path)
    game = tmp_path / "game"
    (game / "DBDAT").mkdir(parents=True)
    archive = game / "DBDAT/MINIESC.PKF"
    archive.write_bytes(b"corrected-kit")
    kit = tmp_path / "kit.json"
    kit.write_text(json.dumps({"season": "2022-23", "unrelated_files_unchanged": True,
        "difference": {"changed": [{"path": "DBDAT/MINIESC.PKF",
            "left": {"sha256": "0" * 64}, "right": {"sha256": qa._sha256(archive)}}]}}))
    photo = tmp_path / "photo.json"
    photo.write_text(json.dumps({"season": "2022-23", "unrelated_files_unchanged": True,
                                "difference": {"changed": []}}))
    ancestor = tmp_path / "ancestor.json"
    ancestor.write_text(json.dumps({"portrait_patch_application_path": "kit.json"}))
    monkeypatch.setattr(qa.release_registry, "locator_path", lambda season, revision: ancestor)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"external_artifacts": [
        {"sha256": qa._sha256(path), "size": path.stat().st_size} for path in (kit, photo)]}))
    chain = tmp_path / "chain.json"
    chain.write_text(json.dumps({"stages": [
        {"id": "portrait-kits-r7", "receipt_sha256": qa._sha256(kit),
         "outputs": {"DBDAT/MINIESC.PKF": qa._sha256(archive)}},
        {"id": "portrait-photos-r9", "receipt_sha256": qa._sha256(photo), "outputs": {}}]}))
    release = SimpleNamespace(locator={"portrait_patch_application_path": "photo.json"},
        release_manifest_path=manifest, manifest_sha256=qa._sha256(manifest), build_chain_path=chain)
    monkeypatch.setattr(qa.release_registry, "load_preferred_release", lambda season: release)
    assert qa._registered_kit_patch_hashes("2022-23", game)["MINIESC.PKF"]["after"] == qa._sha256(archive)
    # An archived locator cannot grant approval to a replacement receipt.
    kit.write_text(kit.read_text() + " ")
    assert qa._registered_kit_patch_hashes("2022-23", game) == {}


def test_successive_kit_patches_compose_and_preserve_other_sizes(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import pytest
    from scripts import pm99_season_qa_v1 as qa

    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    names = ['MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF']
    first_hashes = {}
    for name in names:
        path = game / 'DBDAT' / name
        path.write_bytes(('first-' + name).encode())
        first_hashes[name] = qa._sha256(path)
    nano = game / 'DBDAT/NANOESC.PKF'
    nano.write_bytes(b'second-nano')
    first = tmp_path / 'first.json'
    first.write_text(json.dumps({'season': '2022-23', 'unrelated_files_unchanged': True,
        'difference': {'changed': [{'path': 'DBDAT/' + name,
            'left': {'sha256': '0' * 64}, 'right': {'sha256': first_hashes[name]}} for name in names]}}))
    second = tmp_path / 'second.json'
    second.write_text(json.dumps({'season': '2022-23', 'unrelated_files_unchanged': True,
        'difference': {'changed': [{'path': 'DBDAT/NANOESC.PKF',
            'left': {'sha256': first_hashes['NANOESC.PKF']}, 'right': {'sha256': qa._sha256(nano)}}]}}))
    ancestor = tmp_path / 'ancestor.json'
    ancestor.write_text(json.dumps({'kit_patch_application_path': 'first.json'}))
    monkeypatch.setattr(qa.release_registry, 'locator_path', lambda *args: ancestor)
    manifest, chain = tmp_path / 'manifest.json', tmp_path / 'chain.json'
    def bind():
        manifest.write_text(json.dumps({'external_artifacts': [
            {'sha256': qa._sha256(p), 'size': p.stat().st_size} for p in [first, second]]}))
        chain.write_text(json.dumps({'stages': [
            {'id': 'portrait-first', 'receipt_sha256': qa._sha256(first),
             'outputs': {'DBDAT/' + n: h for n, h in first_hashes.items()}},
            {'id': 'portrait-second', 'receipt_sha256': qa._sha256(second),
             'outputs': {'DBDAT/NANOESC.PKF': qa._sha256(nano)}}]}))
        return SimpleNamespace(locator={'kit_patch_application_path': 'second.json'},
            release_manifest_path=manifest, manifest_sha256=qa._sha256(manifest), build_chain_path=chain)
    release = bind()
    monkeypatch.setattr(qa.release_registry, 'load_preferred_release', lambda *args: release)
    result = qa._registered_kit_patch_hashes('2022-23', game)
    assert result['MINIESC.PKF']['after'] == first_hashes['MINIESC.PKF']
    assert result['RIDIESC.PKF']['after'] == first_hashes['RIDIESC.PKF']
    assert result['NANOESC.PKF']['before'] == '0' * 64
    assert len(result['NANOESC.PKF']['history']) == 2
    # Even a fully hash-bound later application cannot skip its predecessor.
    value = json.loads(second.read_text())
    value['difference']['changed'][0]['left']['sha256'] = 'f' * 64
    second.write_text(json.dumps(value))
    release = bind()
    with pytest.raises(qa.QaError, match='predecessor'):
        qa._registered_kit_patch_hashes('2022-23', game)
    first.write_text(first.read_text() + ' ')
    with pytest.raises(qa.QaError, match='hash-bound'):
        qa._registered_kit_patch_hashes('2022-23', game)


def test_2015_replays_foreign_and_english_bitmap_predecessors(tmp_path, monkeypatch):
    import json
    import pytest
    from scripts import pm99_season_qa_v1 as qa

    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    english = tmp_path / 'seasons/2015-16/english-layer/2015-16-english-92-native-kit-receipt.json'
    english.parent.mkdir(parents=True)
    english.write_text(json.dumps({'patched': [{'archive_name': 'NANOESC.PKF',
        'team_id': 2, 'bitmap_sha256_after': 'english-original'}]}))
    receipt = {'foreign_events': [{'archive': 'NANOESC.PKF', 'carrier_id': 1,
        'bitmap_sha256_after': 'foreign-original'}]}
    history = []
    for i, events in enumerate([
        [{'archive': 'NANOESC.PKF', 'carrier_id': 1, 'before_bitmap_sha256': 'foreign-original',
          'after_bitmap_sha256': 'foreign-intermediate'}],
        [{'archive': 'NANOESC.PKF', 'carrier_id': 1, 'before_bitmap_sha256': 'foreign-intermediate',
          'after_bitmap_sha256': 'foreign-final'},
         {'archive': 'NANOESC.PKF', 'carrier_id': 2, 'before_bitmap_sha256': 'english-original',
          'after_bitmap_sha256': 'english-final'}],
    ]):
        material = tmp_path / f'material-{i}.json'
        material.write_text(json.dumps({'events': events,
            'kit_before_sha256s': {'DBDAT/NANOESC.PKF': f'archive-{i}'}}))
        application = tmp_path / f'application-{i}.json'
        application.write_text(json.dumps({'materialisation_path': str(material),
            'materialisation_sha256': qa._sha256(material)}))
        history.append({'application_path': application.name, 'before': f'archive-{i}', 'stage_index': i})
    patches = {'NANOESC.PKF': {'history': history}}
    revised, accepted, english_changed = qa._apply_2015_kit_patch_history(receipt, patches)
    assert len(revised['foreign_events']) == 1
    assert revised['foreign_events'][0]['bitmap_sha256_after'] == 'foreign-final'
    assert len(accepted) == 3
    assert english_changed == {('NANOESC.PKF', 2): 'english-final'}
    receipt['foreign_events'][0]['bitmap_sha256_after'] = 'unrecorded-original'
    with pytest.raises(qa.QaError, match='predecessor'):
        qa._apply_2015_kit_patch_history(receipt, patches)


def test_role_delta_inherits_kit_evidence_only_through_bound_unchanged_outputs(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import pytest
    from scripts import pm99_season_qa_v1 as qa

    monkeypatch.setattr(qa.release_registry, 'LOCAL_ROOT', tmp_path)
    previous = tmp_path / 'releases/2025-26/previous/build-chain.json'
    previous.parent.mkdir(parents=True)
    kits = {'DBDAT/' + name: str(i) * 64 for i, name in enumerate(
        ('MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF'), 1)}
    old = {'season': '2025-26', 'stages': [{'id': 'portrait-kits', 'outputs': kits}]}
    previous.write_text(json.dumps(old))
    new = tmp_path / 'current-chain.json'
    wrapped = {'season': '2025-26', 'stages': [{'id': 'inherited-known-good-assets',
        'source_build_chain_sha256': qa._sha256(previous), 'outputs': kits}]}
    new.write_text(json.dumps(wrapped))
    release = SimpleNamespace(build_chain_path=new)
    manifest = {'external_artifacts': [{'sha256': qa._sha256(previous), 'size': previous.stat().st_size}]}
    assert qa._artwork_chain_through_unchanged_role_deltas('2025-26', release, manifest) == old
    with pytest.raises(qa.QaError, match='hash-bound'):
        qa._artwork_chain_through_unchanged_role_deltas('2025-26', release, {})
    wrapped['stages'][0]['outputs'] = {**kits, 'DBDAT/NANOESC.PKF': 'f' * 64}
    new.write_text(json.dumps(wrapped))
    with pytest.raises(qa.QaError, match='changed inherited'):
        qa._artwork_chain_through_unchanged_role_deltas('2025-26', release, manifest)


def test_recipe_only_revision_requires_all_inherited_outputs_unchanged(tmp_path, monkeypatch):
    import json
    import pytest
    from types import SimpleNamespace
    from scripts import pm99_season_qa_v1 as qa
    monkeypatch.setattr(qa.release_registry, 'LOCAL_ROOT', tmp_path)
    previous = tmp_path / 'releases/2015-16/previous/build-chain.json'
    previous.parent.mkdir(parents=True)
    outputs = {'DBDAT/' + name: str(i) * 64 for i, name in enumerate(
        ('MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF', 'EQ98030.FDI'), 1)}
    old = {'season': '2015-16', 'stages': [{'id': 'assets', 'outputs': outputs}]}
    previous.write_text(json.dumps(old))
    wrapped = {'season': '2015-16', 'stages': [{'id': 'inherited-identical-game',
        'source_build_chain_sha256': qa._sha256(previous), 'outputs': outputs}]}
    path = tmp_path / 'new.json'; path.write_text(json.dumps(wrapped))
    release = SimpleNamespace(build_chain_path=path)
    manifest = {'external_artifacts': [{'sha256': qa._sha256(previous), 'size': previous.stat().st_size}]}
    assert qa._artwork_chain_through_unchanged_role_deltas('2015-16', release, manifest) == old
    wrapped['stages'][0]['outputs'] = {**outputs, 'DBDAT/EQ98030.FDI': 'f' * 64}
    path.write_text(json.dumps(wrapped))
    with pytest.raises(qa.QaError, match='recipe-only revision changed'):
        qa._artwork_chain_through_unchanged_role_deltas('2015-16', release, manifest)


def test_calendar_accepts_only_exact_guarded_transform_not_other_exe_edits(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from scripts import pm99_season_qa_v1 as qa

    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    expected = tmp_path / '.local/calendar-v1/2025-26/MANAGPRE.EXE'
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b'exact-calendar')
    game = tmp_path / 'game'; game.mkdir()
    actual = game / 'MANAGPRE.EXE'
    actual.write_bytes(b'exact-calendar-with-two-guard-bytes')
    monkeypatch.setitem(sys.modules, 'player_birth_year_guard', SimpleNamespace(
        patch_native_birth_year_guard=lambda data: (data + b'-with-two-guard-bytes', {'calendar_rebased': False})))
    assert qa.audit_calendar('2025-26', game)['passed']
    actual.write_bytes(actual.read_bytes() + b'-unrecorded-other-edit')
    assert not qa.audit_calendar('2025-26', game)['passed']


def test_legacy_manager_graph_does_not_require_unrelated_player_bytes_to_stay_old(tmp_path, monkeypatch):
    from scripts import pm99_season_qa_v1 as qa
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    game = tmp_path / 'game'; (game / 'DBDAT').mkdir(parents=True)
    for name in ('EQ98030.FDI', 'ENT98030.FDI', 'JUG98030.FDI'):
        (game / 'DBDAT' / name).write_bytes(name.encode())
    raw = {'failures': [], 'written_manager_count': 1, 'failure_count': 0}
    monkeypatch.setattr(qa, 'audit_managers', lambda **kw: raw)
    monkeypatch.setattr(qa, '_manager_graph', lambda **kw: ({620: [{'carrier_id': 309}]}, {620: 'Arsene Wenger'}))
    manifest = {'teams': [{'record_id': 309, 'manager_record_id': 3, 'manager_name': 'Arsene Wenger', 'club': 'Arsenal'}]}
    receipt = {'state': 'applied-to-candidate-game', 'readback_failure_count': 0, 'byte_contract': {
        'eq_after_sha256': qa._sha256(game / 'DBDAT/EQ98030.FDI'),
        'ent_after_sha256': qa._sha256(game / 'DBDAT/ENT98030.FDI'),
        'jug_unchanged_sha256': 'old-player-hash'}}
    marker = tmp_path / '.local/operations/2015-16/manager-facts-manager-graph-application-v1-r2-20260913.json'
    marker.parent.mkdir(parents=True); marker.write_text('receipt')
    monkeypatch.setattr(qa, '_read_object', lambda path, label: manifest if 'manifest' in label else receipt)
    assert qa.audit_compiled_managers({}, game=game, season='2015-16')['failure_count'] == 0
    manifest['teams'][0]['manager_name'] = 'Wrong Manager'
    assert qa.audit_compiled_managers({}, game=game, season='2015-16')['failure_count'] == 1


def test_manager_readback_checks_short_field_even_when_full_name_is_correct(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import pm99_season_qa_v1 as qa
    game = tmp_path / 'game'; (game / 'DBDAT').mkdir(parents=True)
    (game / 'DBDAT/ENT98030.FDI').write_bytes(b'profile')
    monkeypatch.setattr(qa, 'audit_managers', lambda **kw: {'failures': [], 'written_manager_count': 1, 'failure_count': 0})
    entry = SimpleNamespace(record_id=7, payload_offset=0, payload_length=7)
    monkeypatch.setattr(qa, 'IndexedFDIFile', SimpleNamespace(from_bytes=lambda _: SimpleNamespace(entries=[entry])))
    profile = SimpleNamespace(surname='Wrong', display_name='Arsene Wenger')
    monkeypatch.setattr(qa, 'parse_indexed_ent_manager_profile', lambda *_a, **_kw: profile)
    package = {'managers': [{'carrier_id': 7, 'name': 'Arsene Wenger',
                            'native_names': {'surname': 'Wenger', 'display_name': 'Arsene Wenger'}}]}
    result = qa.audit_compiled_managers(package, game=game, season='2016-17')
    assert result['native_alias_failure_count'] == result['failure_count'] == 1
    profile.surname = 'Wenger'
    result = qa.audit_compiled_managers(package, game=game, season='2016-17')
    assert result['failure_count'] == 0
