import pytest
from scripts import scan_duplicate_whole_club_sources_v1 as scanner


def test_snapshot_is_loaded_once_but_rehashed_after_decisions(tmp_path, monkeypatch):
    database, receipt = tmp_path / 'db', tmp_path / 'receipt'
    database.write_bytes(b'fixed-data')
    receipt.write_bytes(b'fixed-pin')
    binding = {'sha256': scanner.whole.registry.sha256_file(database),
        'pinned_receipt_sha256': scanner.whole.registry.sha256_file(receipt)}
    calls = []
    def load(*args):
        calls.append(args)
        return {}, {}, binding
    monkeypatch.setattr(scanner.context, 'load_snapshot', load)
    cache = scanner.BoundSnapshotCache()
    assert cache.load(database, receipt) == cache.load(database, receipt)
    assert len(calls) == 1
    cache.verify()
    database.write_bytes(b'changed')
    with pytest.raises(ValueError, match='snapshot changed'):
        cache.verify()


def test_cached_public_originals_cannot_change_during_scan(tmp_path):
    raw = tmp_path / 'raw'
    raw.write_bytes(b'original')
    cache = scanner.BoundSnapshotCache()
    cache.public_files[raw] = scanner.whole.registry.sha256_file(raw)
    cache.verify()
    raw.write_bytes(b'changed')
    with pytest.raises(ValueError, match='public original changed'):
        cache.verify()


def test_only_source_invariants_can_skip_another_native_carrier_attempt():
    assert scanner.source_gap_scope('Soccerbase club identity lacks two consistent dated starter ownership brackets', 18) == ('club-original-identity',)
    assert scanner.source_gap_scope('fixed capacity lacks 2 positively dated opening reserves', 18) == ('opening-reserve-evidence', 18)
    assert scanner.source_gap_scope('actual opening roster cannot fit the native name windows', 18) is None
    assert scanner.source_gap_scope('some unknown error', 18) is None


def test_explicit_matchday_route_does_not_change_default_or_omit_required_authority():
    assert scanner.explicit_matchday_route(False)=={}
    assert scanner.explicit_matchday_route(True)==dict(allow_original_matchday_only_club_identity=True,
        allow_original_provider_career_reserves=True,fit_verified_reserve_pool=False)
    assert scanner.explicit_matchday_route(True,True)['fit_verified_reserve_pool'] is True
    with pytest.raises(ValueError,match='explicit matchday/career'):
        scanner.explicit_matchday_route(False,True)


@pytest.mark.parametrize('decision,accepted',[
    (dict(status='complete-source-fit',outside_collisions=[]),True),
    (dict(status='complete-source-fit',outside_collisions=[dict(other_player_id='copy')]),False),
    (dict(status='complete-source-fit'),False),
    (dict(status='allocation-gap',outside_collisions=[]),False),
    (dict(status='source-gap',outside_collisions=[]),False),
])
def test_early_finish_requires_explicit_complete_fit_and_zero_outside_copies(decision,accepted):
    assert scanner.complete_without_outside_copies(decision) is accepted
