"""Literal fixture labels, never guessed family names or cross-provider IDs."""
import hashlib
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import hajduk_2002_original_opening_v1 as opening
from scripts import season_august_source_fallback_v1 as fallback
from scripts import season_published_display_names_v1 as display

POLICY = 'original-hajduk2002-literal-fixture-display-label-v1'


def reparse(bindings):
    if len(bindings) != 3:
        raise ValueError('fixture display requires three original source bindings')
    originals=[]
    for binding in bindings:
        path=registry.ROOT/binding['path'];registry.relative_workspace_path(path)
        if registry.sha256_file(path)!=binding['sha256']:
            raise ValueError('original fixture display source changed')
        originals.append(path.read_bytes())
    return opening.parse(*originals)


def candidates(replacement):
    claim=replacement.get('original_fixture_display')
    if claim is None:return []
    if claim.get('policy')=='original-sartid2000-literal-fixture-display-label-v1':
        from scripts import prepare_sartid_2000_source_allocation_v1 as sartid
        return sartid.fixture_candidates(replacement)
    if claim.get('policy')!=POLICY:
        raise ValueError('unsupported original fixture display policy')
    parsed=reparse(claim['original_bindings'])
    labels=parsed['starting_xi']+parsed['used_substitutes']
    index=claim['match_person_index']
    if type(index) is not int or not 0<=index<len(labels):
        raise ValueError('fixture display index outside original XI/used substitutes')
    label=labels[index]['published_match_name'];person=replacement['source_person']
    if claim['published_label']!=label or claim['source_player_id']!=person['source_player_id']:
        raise ValueError('fixture display changes the published label or person')
    _,persons=display.read_batch(claim['original_person_batch'])
    original=persons.get(person['source_player_id'])
    if original is None or any(original[key]!=person[key] for key in ('name','birth_date')):
        raise ValueError('fixture label is not bound to the original person biography')
    # The original label is an exact published shorthand, NOT an inferred full
    # family component. Vojnic must not be expanded to a guessed first name.
    expected={0:1514015,1:35918,2:10290,3:28688,5:35921,6:35929,
        7:145641,8:35932,9:36121,10:212936,11:87808}
    if expected.get(index)!=person['source_player_id']:
        raise ValueError('fixture label identifies an unreviewed person bridge')
    return [dict(name=label,method='original-published-fixture-label-not-full-family-claim')]


def verify_actor(person):
    claim=person.get('identity_evidence',{})
    if claim.get('policy')=='original-Mladost2001-published-surname-unresolved-identity-v1':
        from scripts import mladost_2001_original_august_v1 as mladost
        return mladost.verify_actor(person)
    if claim.get('policy')=='original-Estudiantes2000-published-Javier-Gomez-unresolved-identity-v1':
        from scripts import estudiantes_2000_original_august_v1 as estudiantes
        return estudiantes.verify_actor(person)
    bindings=person.get('original_fixture_bindings')
    if bindings is None:raise ValueError('surname-only actor lacks original fixture sources')
    parsed=reparse(bindings)
    expected=fallback.surname(published_surname='Trajkovic',provider='dekisa',
        club=parsed['club'],fixture_date=parsed['fixture_date'],source_binding=bindings[0])
    key='fixture-actor:'+hashlib.sha256(pipeline.canonical_json_bytes(expected)).hexdigest()[:24]
    if (claim!=expected or parsed['starting_xi'][4]['published_match_name']!='Trajkovic'
            or person.get('source_player_id')!=key or person.get('name')!='Trajkovic'
            or person.get('family_name')!='Trajkovic'
            or person.get('given_name') is not None or person.get('birth_date') is not None
            or person.get('identity_policy')!=fallback.SCHEMA or person.get('source_provider')!='original-fixture'):
        raise ValueError('surname-only actor changed source, name, provider or unpublished birthday')
    return 'person-original-fixture-'+key.split(':')[1]
