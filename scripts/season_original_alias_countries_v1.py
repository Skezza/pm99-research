"""Literal source nationality-only completion for the new alias replacements.

These are published biography nationalities, not retroactive claims about caps
or international selection on August1. No nationality is inferred from place
of birth, club, name, photograph or current employer.
"""
import copy
import hashlib
from pathlib import Path
import re
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_v2 as packages,season_package_compiler_v2 as compiler
from scripts import prepare_stoke_alias_identity_evidence_20261016 as originals
from scripts import season_wikipedia_career_identity_v1 as wiki
from scripts.audit_shtanyuk_runtime_aliases_20261016 import ROOT as SOURCES

SCHEMA='pm99-original-new-alias-actors-literal-country-only-v1'
MODE='known-good-baseline-original-new-alias-actors-literal-country-only-v1'
FILENAME='original-alias-country-only.json'
SPECS={
    '2001-02':dict(base='sourced-stoke-commons-number-20261016-r118a',carrier=27013,
        name='Kris Commons',birthday='1983-08-30',after='SCO'),
    '2002-03':dict(base='sourced-shtanyuk-coupled-owners-20261016-r119a',carrier=10580,
        name='Jurgen Vandeurzen',birthday='1974-01-26',after='BEL'),
}


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return FILENAME


def literal(page,season):
    spec=SPECS[season]
    if season=='2001-02':
        profile=originals.soccerbase(page,spec['name'])
        if profile['birth_date']!=spec['birthday'] or originals.unique_field(page,'Nationality')!='Scotland':
            raise ValueError('original exact Commons profile/date/literal nationality differs')
    else:
        # A literal statement about nationality, NOT a Belgium birthplace.
        pattern=r'^Jurgen Vandeurzen \(born 26 January 1974\) is a former Belgian professional footballer\b'
        if len([p for p in page.find_all('p') if re.search(pattern,p.get_text(' ',strip=True))])!=1:
            raise ValueError('one literal original Belgian footballer statement required')
        birthdays=page.select('.bday')
        if len(birthdays)!=1 or birthdays[0].get_text(strip=True)!=spec['birthday']:
            raise ValueError('original Vandeurzen nationality belongs to another birthday')
    return spec['after']


def prepare(base):
    spec=SPECS[base.season]
    if base.release_id!=spec['base']:raise ValueError('country-only correction requires exact completed alias parent')
    key,url=('commons-soccerbase','https://www.soccerbase.com/players/player.sd?player_id=28633') if base.season=='2001-02' else (
        'vandeurzen-biography','https://en.wikipedia.org/wiki/Jurgen_Vandeurzen')
    page,binding=originals.original(SOURCES/'reserve-originals',key,url)
    code=literal(page,base.season)
    if base.season=='2002-03':
        person,_=wiki.read((registry.ROOT/binding['path']).read_bytes(),'Jurgen_Vandeurzen',url,
            '2002-08-01','Stoke City','england',expected_name=spec['name'])
        if person['birth_date']!=spec['birthday']:raise ValueError('positive biography identity differs')
    package=pipeline.read_json_file(base.package_path)
    player=next(p for p in package['players'] if p['carrier_id']==spec['carrier'])
    if (player['source_name'],player['facts']['birth_date'],player['facts']['nationality'])!=(spec['name'],spec['birthday'],'XXX'):
        raise ValueError('country target is not the exact sourced replacement with a declared unknown')
    countries=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    native_code=compiler._country_code(code,countries)
    if native_code==countries['XXX']:raise ValueError('literal nationality is not representable')
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'),original_source=binding,
        updates=[dict(carrier_id=spec['carrier'],before_player=player,before='XXX',after=code,native_country_code=native_code)],
        native_byte_changes=1,source_title='Literal full-identity-bound published biography nationality; not a claim about historical caps',
        implementation_inputs=[dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p)) for p in (
            Path(__file__),Path(originals.__file__),registry.ROOT/'upstream/pm99-skezmod-db-editor/app/indexed_jug_nationality.py')],
        scope='One selected actor nationality byte/fact only. All names, dates, skills, roles, shirt numbers, orders, tactics, managers, kits and portraits preserved.')


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:raise ValueError('literal country source or exact native parent no longer reproduces')


def bind(package,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    if pipeline.read_json_file(base.package_path)!=package or registry.sha256_file(base.package_path)!=plan['package_sha256']:
        raise ValueError('country recipe preimage changed')
    result=copy.deepcopy(package);row=plan['updates'][0]
    player=next(p for p in result['players'] if p['carrier_id']==row['carrier_id'])
    if player!=row['before_player']:raise ValueError('country target recipe row changed')
    aid='original-alias-country-'+plan['season'];proof=dict(artifact_id=aid,grade='source-receipt')
    player['facts']['nationality']=row['after'];player['proof']=proof
    player['fact_fallbacks']=[f for f in player.get('fact_fallbacks',[]) if f['field']!='nationality']
    result['artifacts'].append(dict(id=aid,kind='season-input',media_type='application/json',relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan))))
    result['sources'].append(dict(id=aid+'-source',title=plan['source_title'],uri=plan['original_source']['url'],
        proof_grade='source-receipt',evidence_artifact_id=aid))
    result['proofs'].append(dict(id='proof-'+aid,artifact_id=aid,grade='source-receipt',covers=['literal-published-biography-nationality-only']))
    for key in ('artifacts','sources','proofs'):result[key].sort(key=lambda r:r['id'])
    packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    original_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(original),digest(original_eq))!=(plan['jug_sha256'],plan['eq_sha256']) or eq!=original_eq:
        raise ValueError('country-only native preimage changed')
    updates={r['carrier_id']:r['native_country_code'] for r in plan['updates']}
    candidate,changes=rewrite_indexed_native_nationalities(original,updates)
    if len(changes)!=1 or jug not in (original,candidate):raise ValueError('country delta escaped exact one-byte pre/postimages')
    if rewrite_indexed_native_nationalities(candidate,updates)!=(candidate,[]):raise ValueError('country delta not idempotent')
    return candidate,original_eq


def reconstruction(previous,release_id):
    if pipeline.read_json_file(previous.compiler_receipt_path).get('compilation_mode')!=MODE:return None
    from scripts import publish_historical_role_delta_v1 as publisher
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    if path.resolve()!=(previous.package_path.parent/FILENAME).resolve():raise ValueError('country SOURCE plan is not release-local')
    if bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(previous.package_path):
        raise ValueError('country SOURCE cannot silently discard recipe edits')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('country SOURCE inert descriptor differs')
    publisher.publish(base.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(base.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=pipeline.read_json_file(previous.package_path):raise ValueError('entire country SOURCE recipe differs')
    return dict(season=base.season,release_id=release_id,complete_game_inventory_identical=True,complete_recipe_identical=True)
