import copy
import json
import pytest
from scripts import season_published_family_component_v1 as family
from scripts import season_published_person_identity_v1 as people
from scripts import season_release_registry_v1 as registry


@pytest.mark.parametrize('full,alias,surname',[
    ('Reece Hall-Johnson','R. Hall-Johnson','Hall-Johnson'),
    ('Reece Hall-Johnson','R Hall-Johnson','Hall-Johnson'),
    ('Dawid Szczepaniak','D. Szczepaniak','Szczepaniak'),
    ('Robin van Persie','R. van Persie','van Persie'),
    ('Edwin van der Sar','E. van der Sar','van der Sar'),
    ('Alexander Sørloth','A. Sørloth','Sørloth'),
    ('Steven Naismith','S.Naismith','Naismith')])
def test_entire_compound_or_particle_surname_is_preserved_from_both_original_fields(full,alias,surname):
    raw={'name':full,'shortName':alias};before=copy.deepcopy(raw)
    result=family.components(raw)
    assert len(result)==1 and result[0]['name']==surname
    assert raw==before


@pytest.mark.parametrize('full,alias',[
    ('Reece Hall-Johnson','R. Johnson'),('Reece Hall-Johnson','R. Hall'),
    ('Reece Hall-Johnson','S. Hall-Johnson'),('Kai Lukas Havertz','K. Havertz'),
    ('Robin van Persie','R. Persie'),('R. Hall-Johnson','R. Hall-Johnson'),
    ('R Hall-Johnson','R. Hall-Johnson'),('Ronaldinho','R. Ronaldinho'),
    ('David Jones','D. Jones Jr'),('Jean Pierre Jones','J.P. Jones')])
def test_abbreviations_mismatches_lost_middle_names_and_shortened_surnames_are_never_guessed(full,alias):
    assert family.components({'name':full,'shortName':alias})==[]


def original(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'ROOT',tmp_path)
    raw={'id':99,'name':'Reece Hall-Johnson','shortName':'R. Hall-Johnson',
        'lifeDates':{'dateOfBirth':'1995-05-09','isDateOfBirthUnknown':False},
        'relativeUrl':'/reece-hall-johnson/profil/spieler/99'}
    path=tmp_path/'original.json';path.write_text(json.dumps({'success':True,'data':[raw]}))
    sha=registry.sha256_file(path);url=people.url([99]);receipt=tmp_path/'original.source.json'
    receipt.write_text(json.dumps({'url':url,'sha256':sha}))
    batch={'status':'original-entities-parsed','requested_ids':[99],'source_url':url,
        'raw_path':'original.json','raw_sha256':sha,'source_receipt_path':'original.source.json'}
    source=tmp_path/'person-input.json';source.write_text(json.dumps({'schema_version':people.SCHEMA,
        'policy':people.POLICY,'batches':[batch]}))
    return source,{'source_player_id':99,'birth_date':'1995-05-09'},path


def test_family_component_claim_has_independent_original_ID_DOB_URL_and_hash_binding(tmp_path,monkeypatch):
    source,person,path=original(tmp_path,monkeypatch);claim=family.claims(source,{99})[99]
    assert family.verify(claim,person)==[{'field':'family-component-of-original-shortName','name':'Hall-Johnson'}]
    assert family.claims(source,{100})=={}


@pytest.mark.parametrize('problem',['surname','given','alias','DOB','id','policy','raw','receipt'])
def test_forged_or_changed_name_component_identity_or_original_source_is_refused(tmp_path,monkeypatch,problem):
    source,person,path=original(tmp_path,monkeypatch);claim=family.claims(source,{99})[99]
    if problem=='surname':claim['components'][0]['name']='Johnson'
    if problem=='given':claim['components'][0]['explicit_given_component']='Richard'
    if problem=='alias':claim['components'][0]['original_alias']='R. Johnson'
    if problem=='DOB':claim['birth_date']='1995-05-10'
    if problem=='id':claim['source_player_id']=100
    if problem=='policy':claim['policy']='inferred'
    if problem=='raw':path.write_text('changed')
    if problem=='receipt':(tmp_path/'original.source.json').write_text('{}')
    with pytest.raises(ValueError):family.verify(claim,person)


def test_default_plan_keeps_previous_policy():
    family.verify_plan({'updates':[],'bindings':{}})


def test_native_candidates_do_not_mistake_a_surname_particle_for_a_given_name(tmp_path,monkeypatch):
    source,person,path=original(tmp_path,monkeypatch)
    doc=json.loads(path.read_text());doc['data'][0].update(name='Paul di Giacomo',shortName='P. di Giacomo')
    path.write_text(json.dumps(doc));sha=registry.sha256_file(path)
    receipt=tmp_path/'original.source.json';receipt.write_text(json.dumps({'url':people.url([99]),'sha256':sha}))
    supplement=json.loads(source.read_text());supplement['batches'][0]['raw_sha256']=sha
    source.write_text(json.dumps(supplement));claim=family.claims(source,{99})[99]
    assert family.native_candidates(claim,person)==[{'field':'full-family-from-original-shortName','name':'P. di Giacomo'}]


@pytest.mark.parametrize('problem',[None,'no-optin','no-policy','wrong-policy','changed-input','forged-claim'])
def test_plan_requires_explicit_policy_and_exact_bound_original(tmp_path,monkeypatch,problem):
    source,person,_=original(tmp_path,monkeypatch)
    claim=family.claims(source,{99})[99]
    plan={'allow_published_family_components':True,'bindings':{
        'published_family_component_policy':family.POLICY,
        'published_person_supplement':{'path':source.name,'sha256':registry.sha256_file(source)}},
        'updates':[{'published_family_component':claim,'replacement':{'source_person':person}}]}
    if problem=='no-optin':plan.pop('allow_published_family_components')
    if problem=='no-policy':plan['bindings'].pop('published_family_component_policy')
    if problem=='wrong-policy':plan['bindings']['published_family_component_policy']='guessed'
    if problem=='changed-input':source.write_text('{}')
    if problem=='forged-claim':claim['components'][0]['name']='Johnson'
    if problem is None:family.verify_plan(plan)
    else:
        with pytest.raises(ValueError):family.verify_plan(plan)
