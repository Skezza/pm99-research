"""Reject guessed coach ownership and stale source/parent bindings."""
from types import SimpleNamespace
import pytest
from scripts import season_august_manager_tenures_20261016 as source
from scripts import build_august_manager_tenures_20261016 as batch
from scripts import archive_completed_italian_kit_replays_20261016 as archive


def row(mid, name):
    return dict(manager_id=mid, after=name, club_id='club-' + mid, club=mid)


def test_full_name_collision_needs_distinct_person_proof():
    package = dict(managers=[dict(id='wrexham', name='Phil Parkinson'), dict(id='altrincham', name='King')])
    updates, deferred = source.noncolliding(package, [row('altrincham', 'Phil Parkinson')])
    assert updates == [] and len(deferred) == 1


def test_two_proposals_cannot_duplicate_canonical_owner():
    package = dict(managers=[dict(id='a', name='A'), dict(id='b', name='B')])
    updates, deferred = source.noncolliding(package, [row('a', 'Patrick Walker'), row('b', 'Patrick Walker')])
    assert updates == [] and len(deferred) == 2


def test_coordinated_distinct_coach_swap_is_allowed():
    package = dict(managers=[dict(id='a', name='Patrick Walker'), dict(id='b', name='Soren Cratz')])
    updates, deferred = source.noncolliding(package, [row('a', 'Soren Cratz'), row('b', 'Patrick Walker')])
    assert len(updates) == 2 and not deferred


def test_collision_rejection_cascades_without_orphaning_another_owner():
    package = dict(managers=[dict(id='a', name='Alpha'), dict(id='b', name='Beta'), dict(id='c', name='Gamma')])
    updates, deferred = source.noncolliding(package, [row('a', 'Beta'), row('b', 'Gamma')])
    assert not updates and len(deferred) == 2


def test_original_source_sha_is_checked_before_parsing(tmp_path, monkeypatch):
    path = tmp_path / 'source.json'; path.write_bytes(b'{}')
    monkeypatch.setattr(source.pipeline, 'read_json_file', lambda _: pytest.fail('parsed stale source'))
    with pytest.raises(ValueError, match='source document changed'):
        source.checked_json(path, '0' * 64)


def build_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
    plan = dict(release_id='exact-v53-parent', updates=[1])
    monkeypatch.setattr(batch.pipeline, 'read_json_file', lambda _: plan)
    base = SimpleNamespace(release_id='exact-v53-parent', manifest_sha256='parent-sha')
    monkeypatch.setattr(batch.registry, 'load_registered_release', lambda *a: base)
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda *a: base)
    monkeypatch.setattr(batch.source, 'prepare', lambda _: plan)
    calls = []
    monkeypatch.setattr(batch.build_core, 'build', lambda *a, **kw: calls.append(kw))
    return plan, calls


def test_build_uses_current_exact_parent_not_old_donor_baseline(tmp_path, monkeypatch):
    _, calls = build_fixture(tmp_path, monkeypatch)
    batch.build('2006-07')
    assert calls[0]['source_release_id'] == 'exact-v53-parent'


def test_intervening_preferred_changes_are_not_discarded(tmp_path, monkeypatch):
    _, calls = build_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda _: SimpleNamespace(release_id='later-fix'))
    with pytest.raises(ValueError, match='intervening changes'):
        batch.build('2006-07')
    assert not calls


def test_changed_admitted_plan_stops_before_build(tmp_path, monkeypatch):
    _, calls = build_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(batch.source, 'prepare', lambda _: {'different': True})
    with pytest.raises(ValueError, match='sources or exact parent'):
        batch.build('2006-07')
    assert not calls


def test_empty_admission_does_not_regenerate_a_game(tmp_path, monkeypatch):
    plan, calls = build_fixture(tmp_path, monkeypatch)
    plan['updates'] = []
    batch.build('2006-07')
    assert not calls


def test_archive_cannot_target_an_actual_parent_or_arbitrary_game(tmp_path, monkeypatch):
    monkeypatch.setattr(archive.registry, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='unexpected private workspace'):
        archive.safe_workspace(SimpleNamespace(game_path=tmp_path / 'current-game'), '2005-06')


def checkpoint_fixture(tmp_path, monkeypatch):
    from scripts import checkpoint_august_manager_tenures_20261016 as checkpoint
    root = tmp_path / 'batch'; root.mkdir()
    monkeypatch.setattr(checkpoint.batch, 'ROOT', root)
    seasons = [f'{y}-{str(y+1)[-2:]}' for y in range(2000, 2026)]
    selected = [s for s in seasons if s not in ('2002-03', '2003-04', '2007-08', '2009-10', '2015-16')]
    old = dict(current_release_bindings=[dict(season=s, release_id='parent', manifest_sha256='sha') for s in seasons])
    admission = dict(original_receipt_backed_candidates=53, admitted=49, unresolved=4,
        seasons=[dict(season=s, corrections=1) for s in selected])
    monkeypatch.setattr(checkpoint.pipeline, 'read_json_file', lambda p: admission if p.name == 'source-admission-summary.json' else old)
    monkeypatch.setattr(checkpoint.registry, 'supported_seasons', lambda: seasons)
    monkeypatch.setattr(checkpoint.registry, 'load_preferred_release', lambda s: SimpleNamespace(release_id='parent', manifest_sha256='sha'))
    writes = []
    monkeypatch.setattr(checkpoint.publisher, 'register_completed_delta', lambda *a: writes.append(a))
    return checkpoint, selected, admission, writes


def test_last_missing_original_blocks_entire_manager_publication(tmp_path, monkeypatch):
    checkpoint, seasons, _, writes = checkpoint_fixture(tmp_path, monkeypatch)
    def verify(s):
        if s == seasons[-1]:
            raise ValueError('last original screenshot unreviewed')
        return dict(season=s, canonical_manager_updates=2)
    monkeypatch.setattr(checkpoint, 'verify', verify)
    with pytest.raises(ValueError, match='unreviewed'):
        checkpoint.run()
    assert not writes


def test_admission_denominator_drift_blocks_before_readback(tmp_path, monkeypatch):
    checkpoint, _, admission, writes = checkpoint_fixture(tmp_path, monkeypatch)
    admission['admitted'] = 50
    monkeypatch.setattr(checkpoint, 'verify', lambda _: pytest.fail('must reject changed denominator first'))
    with pytest.raises(ValueError, match='counts changed'):
        checkpoint.run()
    assert not writes


def test_game_counts_not_just_source_summary_must_match(tmp_path, monkeypatch):
    checkpoint, _, _, writes = checkpoint_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(checkpoint, 'verify', lambda s: dict(season=s, canonical_manager_updates=1))
    with pytest.raises(ValueError, match='actual verified canonical'):
        checkpoint.run()
    assert not writes


def test_changed_untouched_2015_blocks_all_publication(tmp_path, monkeypatch):
    checkpoint, seasons, _, writes = checkpoint_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(checkpoint, 'verify', lambda s: dict(season=s, canonical_manager_updates=9 if s == seasons[0] else 2,
        manifest_sha256='new-sha'))
    monkeypatch.setattr(checkpoint.registry, 'load_preferred_release', lambda s: SimpleNamespace(
        release_id='unexpected' if s == '2015-16' else 'parent', manifest_sha256='sha'))
    with pytest.raises(ValueError, match='unexpected preferred'):
        checkpoint.run()
    assert not writes


def test_completed_checkpoint_is_never_republished(tmp_path, monkeypatch):
    checkpoint, _, _, writes = checkpoint_fixture(tmp_path, monkeypatch)
    (tmp_path / 'release-delivery-checklist-v54.json').touch()
    with pytest.raises(ValueError, match='must not repeat'):
        checkpoint.run()
    assert not writes
