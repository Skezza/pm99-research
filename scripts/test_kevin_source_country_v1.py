"""Exact DFB source guards plus optional immutable native corpus checks."""
import copy
import hashlib
import json

import pytest

from scripts import season_known_wrong_profile_nationality_v1 as subject
from scripts import season_source_verified_player_changes_v1 as writer
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline

ROOT = registry.ROOT
AUDIT = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023'
BODY = (f'<html><head><link rel="canonical" href="{subject.KEVIN_DFB_URL}"></head><table>'
        '<tr><td>Name</td><td>Kevin Stuhr-Ellegaard</td></tr>'
        '<tr><td>Geburtstag</td><td>23.05.1983</td></tr>'
        '<tr><td>Nation</td><td>Dänemark</td></tr></table></html>').encode()


def test_exact_german_dfb_identity_and_nation():
    value = subject.parse_dfb_kevin(BODY, url=subject.KEVIN_DFB_URL,
        name=subject.KEVIN_DFB_NAME, birth_date='1983-05-23')
    assert value['nationality'] == 'DEN' and value['published_country'] == 'Dänemark'
    assert value['target_season_ownership_claimed'] is False


@pytest.mark.parametrize('fault', ['url', 'actor', 'birthday', 'published_name',
    'published_dob', 'nation', 'missing_canonical', 'duplicate_canonical', 'duplicate_nation'])
def test_wrong_identity_source_or_ambiguous_fields_reject(fault):
    raw, url, name, dob = BODY, subject.KEVIN_DFB_URL, subject.KEVIN_DFB_NAME, '1983-05-23'
    if fault == 'url': url += '?other=1'
    elif fault == 'actor': name = 'Another keeper'
    elif fault == 'birthday': dob = '1983-05-24'
    elif fault == 'published_name': raw = raw.replace(b'Kevin Stuhr-Ellegaard', b'Another keeper')
    elif fault == 'published_dob': raw = raw.replace(b'23.05.1983', b'24.05.1983')
    elif fault == 'nation': raw = raw.replace('Dänemark'.encode(), b'Deutschland')
    elif fault == 'missing_canonical': raw = raw.replace(b'rel="canonical"', b'rel="other"')
    elif fault == 'duplicate_canonical':
        raw = raw.replace(b'</head>', f'<link rel="canonical" href="{url}"></head>'.encode())
    elif fault == 'duplicate_nation':
        raw = raw.replace(b'</table>', '<tr><td>Nation</td><td>Dänemark</td></tr></table>'.encode())
    with pytest.raises(ValueError):
        subject.parse_dfb_kevin(raw, url=url, name=name, birth_date=dob)


def test_typed_receipt_is_optional_hash_bound_and_legacy_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    body = tmp_path/'original.html'; body.write_bytes(BODY)
    value = dict(url=subject.KEVIN_DFB_URL, sha256=hashlib.sha256(BODY).hexdigest())
    explicit = tmp_path/'capture.source.json'
    explicit.write_text(json.dumps(value))
    source = dict(receipt_path='capture.source.json', receipt_sha256=registry.sha256_file(explicit))
    assert subject.profile_receipt(body, source) == (explicit, value)
    with pytest.raises(ValueError): subject.profile_receipt(body, {'receipt_path': source['receipt_path']})
    with pytest.raises(ValueError): subject.profile_receipt(body, {**source, 'receipt_sha256': '0'*64})
    with pytest.raises(ValueError): subject.profile_receipt(body, {**source, 'receipt_path': '/etc/hosts'})
    with pytest.raises(ValueError): subject.profile_receipt(body, {**source, 'receipt_path': '../outside.json'})
    legacy = tmp_path/'original.html.source.json'; legacy.write_text(json.dumps(value))
    assert subject.profile_receipt(body, {}) == (legacy, value)


@pytest.mark.parametrize('season,carrier', [('2004-05',9184),('2005-06',28340),('2006-07',18955)])
def test_actual_country_only_write_and_whole_postimage_idempotence(season, carrier):
    path = AUDIT/'kevin-country-delivery-v1'/season/'source-input.json'
    if not path.is_file(): pytest.skip('optional source/native corpus unavailable')
    request = pipeline.read_json_file(path)
    base = registry.load_registered_release(season, request['release_id'])
    plan = writer.prepare(base, path); writer.verify(base, json.loads(json.dumps(plan)))
    before = pipeline.read_json_file(base.package_path)
    bound = writer.bind(before, plan)
    old_actor = next(p for p in before['players'] if p['carrier_id']==carrier)
    expected = copy.deepcopy(old_actor); expected['facts']['nationality']='DEN'
    if 'fact_fallbacks' in expected:
        expected['fact_fallbacks']=[f for f in expected['fact_fallbacks'] if f['field']!='nationality']
    assert next(p for p in bound['players'] if p['carrier_id']==carrier)==expected
    assert [p for p in bound['players'] if p['carrier_id']!=carrier] == [p for p in before['players'] if p['carrier_id']!=carrier]
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after, after_eq=writer.apply(jug,eq,plan)
    assert after_eq==eq and len(jug)==len(after)
    assert {i for i,(a,b) in enumerate(zip(jug,after)) if a!=b} == {plan['updates'][0]['native_mask']['file_offset']}
    assert writer.apply(after,eq,plan)==(after,eq)


@pytest.mark.parametrize('season', ['2000-01','2001-02','2002-03','2003-04','2004-05','2005-06','2006-07'])
def test_all_thirteen_retained_legacy_plans_still_reproduce(season):
    path=AUDIT/'keeper-country-delivery-v1'/season/'country-plan.json'
    if not path.is_file(): pytest.skip('optional retained legacy corpus unavailable')
    plan=pipeline.read_json_file(path)
    writer.verify(registry.load_registered_release(season,plan['release_id']),plan)
