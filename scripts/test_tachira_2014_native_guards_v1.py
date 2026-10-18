from types import SimpleNamespace as NS

import pytest

from scripts import verify_ofk_2004_private_native_v1 as reader
from scripts.prepare_tachira_2014_verified_inputs_v1 import native_dated


@pytest.mark.parametrize('source', ['tachira2014', 'tachira2015', 'jedinstvo2005',
    'borac2003', 'italchacao2001', 'hajduk2002', 'monagas2003', 'monagas2002', 'sartid2000', 'estudiantes2000', 'mladost2001'])
def test_each_published_source_adapter_requires_actual_all_club_ownership(source):
    assert reader.requires_exclusive_native_ownership(
        {'schema_version': f'pm99-private-original-{source}-verified-inputs-v1'})


@pytest.mark.parametrize('proposal', [{}, {'schema_version': 'legacy-ofk'},
    {'schema_version': 'pm99-private-original-monagas2000-verified-inputs-v1'}])
def test_other_schemas_do_not_silently_claim_an_ownership_check(proposal):
    assert not reader.requires_exclusive_native_ownership(proposal)


def test_source_manager_id_meets_native_package_contract():
    import re
    proposal = {'dated_manager_ground': {}, 'original_bindings': [{}]}
    assert re.fullmatch(r'[a-z][a-z0-9-]{1,79}', native_dated(proposal)['manager_person_id'])


def setup_rosters(monkeypatch, rosters):
    entries = [NS(record_id=club, payload_offset=n, payload_length=1)
               for n, club in enumerate(rosters)]
    monkeypatch.setattr(reader.native.IndexedFDIFile, 'from_bytes',
                        lambda raw: NS(entries=entries))
    rows = list(rosters.values())
    monkeypatch.setattr(reader.native, 'parse_eq_external_team_roster_payload',
                        lambda raw, names: NS(rows=[NS(player_record_id=id) for id in rows[raw[0]]]))
    return bytes(range(len(rows)))


def test_native_ownership_reads_other_clubs_not_just_recipe(monkeypatch):
    raw = setup_rosters(monkeypatch, {2953: [10, 11], 48: [12]})
    assert reader.verify_native_owners(raw, [10, 11], 2953)


@pytest.mark.parametrize('rosters', [{2953: [10], 48: [11]}, {2953: [10, 11], 48: [10]}])
def test_missing_or_duplicated_physical_ownership_refused(monkeypatch, rosters):
    raw = setup_rosters(monkeypatch, rosters)
    with pytest.raises(ValueError, match='ownership'):
        reader.verify_native_owners(raw, [10, 11], 2953)


def test_unreadable_possible_roster_not_silently_skipped(monkeypatch):
    monkeypatch.setattr(reader.native.IndexedFDIFile, 'from_bytes',
                        lambda raw: NS(entries=[NS(record_id=2953, payload_offset=0, payload_length=600)]))
    monkeypatch.setattr(reader.native, 'parse_eq_external_team_roster_payload', lambda *args: None)
    with pytest.raises(ValueError, match='unreadable'):
        reader.verify_native_owners(bytes(600), [10], 2953)
