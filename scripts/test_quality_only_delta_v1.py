import pytest
from scripts import season_quality_only_delta_v1 as source
from scripts import woking_original_nationalities_v1 as country


@pytest.mark.parametrize('name,code',[('England','ENG'),('France','FRA'),('Dominica','DMA'),('New Zealand','NZL')])
def test_country_from_literal_single_table_row(name,code):
    assert country.nationality(f'<table><tr><th>Nationality</th><td>{name}</td></tr></table>'.encode())==code


@pytest.mark.parametrize('body',['<p>Nationality England</p>',
    '<table><tr><th>Nationality</th><td>England / France</td></tr></table>',
    '<table><tr><th>Nationality</th><td>England</td></tr><tr><th>Nationality</th><td>France</td></tr></table>'])
def test_ambiguous_or_non_structural_country_refuses(body):
    with pytest.raises(ValueError):country.nationality(body.encode())


def test_factory_refuses_quality_layer():
    with pytest.raises(ValueError):source.reject_factory_recipe(dict(artifacts=[dict(id=source.PREFIX+'test')]))


def test_dominica_is_not_dominican_republic():
    assert country.COUNTRIES['Dominica']=='DMA'
    assert 'Dominican Republic' not in country.COUNTRIES


def test_unknown_source_policy_refuses():
    with pytest.raises(ValueError):source.verified_source(None,'wrong')


def test_source_plan_verifies_exact_canonical_json_roundtrip(monkeypatch):
    import json
    plan=dict(schema=source.SCHEMA,kind='policy-test',bounds=(68,84),transaction_id='same')
    monkeypatch.setattr(source,'prepare',lambda base,kind:plan)
    source.verify(None,json.loads(json.dumps(plan)))
    with pytest.raises(ValueError):source.verify(None,dict(plan,bounds=[68,85]))
