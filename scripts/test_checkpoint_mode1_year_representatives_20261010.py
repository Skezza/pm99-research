"""Representative coverage must be explicit, modern and the same native family."""
import copy
import pytest
from app.fdi_indexed import IndexedFDIFile
from scripts import checkpoint_compact_original_person_year_delivery_20261010 as checkpoint
from scripts.test_season_number_label_names_v2 import example


def fixture():
    jug, plan = example()
    entry = next(e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id == 2)
    raw = bytearray(entry.decode_payload(jug))
    end = checkpoint.layer.original.audit.native_player(raw, 2)['name_end']
    raw[end+14:end+16] = bytes(v ^ 0x61 for v in (2004).to_bytes(2, 'little'))
    return bytes(raw), copy.deepcopy(plan['updates'][0]['before_player'])


def test_explicit_same_family_modern_representative():
    raw, person = fixture()
    checkpoint.validate_representative(raw, raw, person, '2024-25', 20, True)


@pytest.mark.parametrize('fault', ['family', 'unknown-family', 'old-year', 'wrong-recipe', 'wrong-age', 'not-declared'])
def test_bad_representative_never_certifies_target(fault):
    raw, person = fixture()
    target = bytearray(raw)
    age, declared = 20, True
    if fault == 'family': target[4] = 0x60
    if fault == 'unknown-family': target[4] = 0x62
    if fault == 'old-year':
        row = bytearray(raw)
        end = checkpoint.layer.original.audit.native_player(raw, 2)['name_end']
        row[end+14:end+16] = bytes(v ^ 0x61 for v in (1990).to_bytes(2, 'little'))
        raw = bytes(row)
    if fault == 'wrong-recipe': person['facts']['birth_date'] = '2004-11-15'
    if fault == 'wrong-age': age = 21
    if fault == 'not-declared': declared = False
    with pytest.raises(ValueError, match='same native family'):
        checkpoint.validate_representative(bytes(target), raw, person, '2024-25', age, declared)
