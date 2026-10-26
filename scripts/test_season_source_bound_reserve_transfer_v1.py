"""Dated reserve admission rejects stale, ambiguous and starter transactions."""
import copy
from pathlib import Path
import pytest
from scripts import season_source_bound_reserve_transfer_v1 as a
from scripts import season_pipeline_v2 as p, season_release_registry_v1 as r
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order

SOURCE = r.ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/nardiello-2007-opening-owner-v1/reserve-transfer-request-v1.json'


@pytest.fixture(scope='module')
def data():
    if not SOURCE.is_file():
        pytest.skip('retained historical corpus unavailable')
    request = p.read_json_file(SOURCE)
    base = r.load_registered_release(request['season'], request['parent']['release_id'])
    plan = a.prepare(base, SOURCE)
    package = p.read_json_file(base.package_path)
    return request, base, plan, package


def test_complete_narrow_native_recipe_postimages(data):
    request, base, plan, package = data
    out = a._outputs(plan)
    before = {z['carrier_id']: z for z in package['players']}
    after = {z['carrier_id']: z for z in out['main']['players']}
    for cid, actor in before.items():
        expected = copy.deepcopy(actor)
        if cid == 9834:
            expected['club_id'] = 'english-club-339'
        assert after[cid] == expected
    for layer in (out['main'], out['english']):
        clubs = {z['carrier_id']: z for z in layer['clubs']}
        assert 'english-player-9834' not in clubs[331]['roster_player_ids']
        assert clubs[339]['roster_player_ids'][-1] == 'english-player-9834'
        assert (len(clubs[331]['roster_player_ids']), len(clubs[339]['roster_player_ids'])) == (23, 22)
    oldclubs = {z['carrier_id']: z for z in package['clubs']}
    newclubs = {z['carrier_id']: z for z in out['main']['clubs']}
    for cid in oldclubs:
        if cid not in (331, 339):
            assert oldclubs[cid] == newclubs[cid]
        else:
            assert oldclubs[cid]['opening']['starting_xi_player_ids'] == newclubs[cid]['opening']['starting_xi_player_ids']
            assert oldclubs[cid]['opening']['tactics_context'] == newclubs[cid]['opening']['tactics_context']
    assert out['main']['assets'] == package['assets']
    assert out['main']['managers'] == package['managers']
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    assert a.apply(out['jug'], out['eq'], plan) == (out['jug'], out['eq'])
    with pytest.raises(ValueError):
        a.apply(jug, out['eq'], plan)
    e0 = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    e1 = {e.record_id: e for e in IndexedFDIFile.from_bytes(out['jug']).entries}
    for cid in e0:
        old, new = e0[cid].decode_payload(jug), e1[cid].decode_payload(out['jug'])
        if cid not in out['changed_order_carriers']:
            assert old == new
        else:
            offset = read_initial_order(old).offset
            assert old[:offset] == new[:offset] and old[offset+1:] == new[offset+1:]
    assert a.bind(package, plan)['players'] == out['main']['players']
    with pytest.raises(ValueError):
        a.reject_factory_recipe({'artifacts': [{'id': a.artifact_id(plan)}]})


@pytest.mark.parametrize('field,value', [
    ('opening_date', '2007-07-11'), ('opening_date', '2008-08-11'),
    ('to_provider_club_id', 349), ('from_provider_club_id', 1039),
    ('provider_player_id', 3537), ('name', 'Another Person'),
    ('birth_date', '1982-10-23'), ('carrier_id', 9809),
])
def test_wrong_source_identity_date_owner_or_starter_refused(data, field, value):
    request, base, plan, package = data
    bad = copy.deepcopy(request)
    bad[field] = value
    with pytest.raises((ValueError, StopIteration, KeyError)):
        a._reconstruct(base, bad)


def test_changed_source_hash_and_plan_refused(data):
    request, base, plan, package = data
    for source in ('history', 'identity'):
        bad = copy.deepcopy(request)
        bad[source]['sha256'] = '0' * 64
        with pytest.raises(ValueError):
            a._reconstruct(base, bad)
    with pytest.raises(ValueError):
        a.verify(base, {**plan, 'scope': 'tampered'})
    bad = copy.deepcopy(package)
    bad['players'][0]['name'] = 'tampered'
    with pytest.raises(ValueError):
        a.bind(bad, plan)


def test_moved_starter_and_capacity_refused(data):
    request, base, plan, package = data
    bad = copy.deepcopy(package)
    clubs = {z['carrier_id']: z for z in bad['clubs']}
    clubs[331]['opening']['starting_xi_player_ids'][0] = 'english-player-9834'
    with pytest.raises(ValueError):
        a._layer(bad, request)

    bad = copy.deepcopy(package)
    clubs = {z['carrier_id']: z for z in bad['clubs']}
    clubs[339]['roster_player_ids'] += ['padding'] * 5
    with pytest.raises(ValueError):
        a._layer(bad, request)


@pytest.mark.parametrize('mutation', ['valid', 'missing_exit', 'same_day', 'wrong_dob', 'wrong_club'])
def test_synthetic_chronology_admission(tmp_path, monkeypatch, mutation):
    import json
    def edge(id, when, source, target):
        return dict(id=str(id), details=dict(playerId='3536', isPending=False, date=when),
                    transferSource=dict(clubId=str(source)), transferDestination=dict(clubId=str(target)),
                    relativeUrl=f'/daniel-nardiello/transfers/spieler/3536/transfer_id/{id}')
    rows = [edge(1, '2007-07-01T00:00:00+02:00', 349, 1039),
            edge(2, '2008-01-24T00:00:00+02:00', 1039, 349)]
    if mutation == 'missing_exit':
        rows.pop()
    if mutation == 'same_day':
        rows.append(edge(3, '2007-07-01T00:00:00+02:00', 1039, 349))
    history = tmp_path / 'history.json'
    history.write_text(json.dumps(dict(success=True, data=dict(playerId='3536', history=dict(terminated=rows, pending=[])))))
    page = tmp_path / 'identity.html'
    dob = '23/10/1982' if mutation == 'wrong_dob' else '22/10/1982'
    target = 'Another Club' if mutation == 'wrong_club' else 'QPR'
    page.write_text(f'<title>Daniel Nardiello - profile</title><p>{dob}</p><table><tr><td>Barnsley</td><td>{target}</td><td>27 Jun 2007</td></tr></table>')
    monkeypatch.setattr(a, '_original', lambda row, url: history if row['kind'] == 'history' else page)
    request = dict(provider_player_id=3536, opening_date='2007-08-11', season='2007-08',
                   from_club_carrier_id=331, to_club_carrier_id=339, from_provider_club_id=349,
                   to_provider_club_id=1039, history=dict(kind='history'),
                   identity=dict(kind='identity', url='https://www.skysports.com/football/player/11813/daniel-nardiello'))
    actor = dict(name='Daniel Nardiello', facts=dict(birth_date='1982-10-22'))
    clubs = {331: dict(name='Barnsley'), 339: dict(name='Queens Park Rangers')}
    if mutation == 'valid':
        assert a.verify_chronology(request, actor, clubs)['entry']['to_club_id'] == 1039
    else:
        with pytest.raises(ValueError):
            a.verify_chronology(request, actor, clubs)
