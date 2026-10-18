import pytest
from scripts import season_retained_native_transfer_v1 as subject
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline


@pytest.fixture
def original():
    path = registry.locator_path('2018-19', 'sourced-barnet-original-opening-20261017-r143a')
    if not path.exists():
        pytest.skip('local immutable2018 baseline unavailable')
    release = registry.load_registered_release('2018-19', 'sourced-barnet-original-opening-20261017-r143a')
    plan = registry.ROOT / '.local/consolidated-audit-20261009/Barnet2018-complete-v1/ownership-plan-65a2a9410ee3.json'
    if not plan.exists():
        pytest.skip('runtime-proven capacity bundle unavailable')
    return ((release.game_path / 'DBDAT/JUG98030.FDI').read_bytes(),
            pipeline.read_json_file(plan)['bindings']['same_carrier_name_capacity'])


def moves():
    return [dict(source_carrier=11043, destination_carrier=11049,
                 expected_source_display='Adam M.', expected_destination_display='George E.'),
            dict(source_carrier=11313, destination_carrier=11043,
                 expected_source_display='Osborne', expected_destination_display='Adam M.',
                 recover_destination_capacity=True)]


def test_duplicate_destination_refused_before_parsing():
    with pytest.raises(ValueError, match='unique destination'):
        subject.compile_moves(b'', [dict(source_carrier=1, destination_carrier=2)] * 2)


def test_one_person_cannot_be_copied_twice():
    with pytest.raises(ValueError, match='multiple destinations'):
        subject.compile_moves(b'', [dict(source_carrier=1, destination_carrier=2),
                                    dict(source_carrier=1, destination_carrier=3)])


def test_native_person_fields_travel_exactly_and_reproduce(original):
    raw, bundle = original
    result, proof = subject.compile_moves(raw, moves(), capacity_bundle=bundle)
    assert subject.compile_moves(raw, moves(), capacity_bundle=bundle) == (result, proof)
    assert result != raw and len(result) == len(raw)
    assert len(proof) == 2
    assert all(row['original_semantics'] == row['transferred_semantics'] for row in proof)
    assert proof[1]['capacity_claim']['recovery']['exact_shrink_roundtrip']
    subject.preserve_other_records(raw, result, {11043, 11049})


def test_recovery_cannot_be_enabled_without_verified_runtime_bundle(original):
    raw, _ = original
    with pytest.raises(ValueError, match='runtime bundle'):
        subject.compile_moves(raw, moves())


@pytest.mark.parametrize('key', ['expected_source_display', 'expected_destination_display'])
def test_literal_original_preimages_required_even_with_capacity_recovery(original, key):
    raw, bundle = original
    request = moves()
    request[1][key] = 'invented alias'
    with pytest.raises(ValueError, match='preimage differs'):
        subject.compile_moves(raw, request, capacity_bundle=bundle)


def test_interleaved_unassigned_fine_role_slots_are_not_compressed(original):
    raw, _ = original
    index = subject.IndexedFDIFile.from_bytes(raw)
    entry = next(e for e in index.entries if e.record_id == 11043)
    payload = bytearray(entry.decode_payload(raw))
    native, _ = subject.read(payload, 11043)
    codes = [4, 98, 9, 98, 17, 98]
    payload[native['name_end'] + 2:native['name_end'] + 8] = bytes(
        (0 if value == 98 else value + 1) ^ 0x61 for value in codes)
    fixture = subject.compiler._rebuild_indexed(raw, index, {11043: bytes(payload)})
    _, proof = subject.compile_moves(fixture, moves()[:1])
    assert proof[0]['original_semantics']['fine_role_codes'] == codes
    assert proof[0]['transferred_semantics']['fine_role_codes'] == codes


def test_name_writer_must_prove_suffix_preservation(original, monkeypatch):
    raw, _ = original
    writer = subject.compiler._patch_indexed_player_variable_name_payload
    def unproven(*args):
        payload, proof = writer(*args)
        return payload, dict(proof, native_suffix_preserved_exactly=False)
    monkeypatch.setattr(subject.compiler, '_patch_indexed_player_variable_name_payload', unproven)
    with pytest.raises(ValueError, match='suffix preservation'):
        subject.compile_moves(raw, moves()[:1])
