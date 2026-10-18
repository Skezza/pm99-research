"""Exact period-country repairs with explicit unsupported and Congo semantics.

Leave the original secondary-fact source and its legacy mapping immutable.
Country evidence comes only from exact-DOB dated annual rows; the public feed
supplies stable identity, never current citizenship/club/position/photo facts.
Unsupported published countries become explicit XXX, not false England.
"""
import copy
from datetime import date
import hashlib
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from scripts import season_original_secondary_facts_v1 as prior
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts.build_2015_english92_release import NATIONALITY,UNREPRESENTABLE_NATIONALITY

SCHEMA='pm99-original-annual-explicit-country-policy-v2'
PREFIX='sourced-original-country-policy-v2-'
MODE='known-good-baseline-original-period-country-policy-v2'
compiler=prior.compiler
original=prior.original


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def filename(plan):
    return 'original-country-policy-v2-'+plan['transaction_id']+'.json'


def native_country(code,codes):
    if code=='CGO':
        label='CONGO'
    elif code in UNREPRESENTABLE_NATIONALITY:
        label='XXX'
    elif code in NATIONALITY:
        label=NATIONALITY[code]
    else:
        raise ValueError('unmapped original period country; do not guess a native flag')
    if label not in codes:
        raise ValueError('original period country mapping absent from actual TEXTOS')
    return int(codes[label]),label


def prepare(base,person_document_path,targets):
    if (not targets or any(not str(k).isdigit() or int(k)<1 or v!=['nationality'] for k,v in targets.items())
            or len({int(k) for k in targets})!=len(targets)):
        raise ValueError('explicit unique nationality-only target carriers required')
    targets={str(int(k)):v for k,v in targets.items()}
    path=Path(person_document_path);document=pipeline.read_json_file(path)
    original.biographies.merge({},document)
    for binding in document['historical_opening_inputs']:
        if registry.sha256_file(registry.ROOT/binding['path'])!=binding['sha256']:
            raise ValueError('original person query input changed')
    package=pipeline.read_json_file(base.package_path)
    people={p['carrier_id']:p for p in package['players']};clubs={c['id']:c for c in package['clubs']}
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners=original.order.native_owners(eq)
    codes=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    sources,bindings=original.audit.load_sources(base.season)
    verifier=original.audit.SourceVerifier(base.season)
    updates=[];unresolved=[]
    for key in sorted(targets,key=int):
        carrier=int(key);player=people[carrier];club=clubs[player['club_id']]
        name=original.names.undecorated(player.get('source_name') or player['name'])
        witnesses=original.witnesses(document,name,player['facts'].get('birth_date'))
        raw=entries[carrier].decode_payload(jug);native=original.audit.native_player(raw,carrier)
        end=native['name_end']
        birthday=date(int.from_bytes(bytes(v^0x61 for v in raw[end+14:end+16]),'little'),
            raw[end+13]^0x61,raw[end+12]^0x61).isoformat()
        if (len(witnesses)!=1 or player.get('policy')=='preserve-existing-mode1'
                or owners.get(carrier)!={club['carrier_id']}
                or original.names.literal_name(native['name'])!=original.names.literal_name(player['name'])
                or birthday!=player['facts'].get('birth_date')):
            unresolved.append(dict(carrier_id=carrier,reason='ambiguous original identity or native preimage'))
            continue
        evidence=[];values=set();valid=True
        for source in sources:
            matching=[p for p in source['players'] if original.audit.normalise(p['name'])==original.audit.normalise(name)
                and p.get('birth_date')==birthday]
            if not matching:
                continue
            proof=verifier.verify(source)
            if proof['status']!='raw-source-reparsed' or len(matching)!=1:
                valid=False;continue
            labels=matching[0].get('nationalities') or [matching[0].get('nationality')]
            values.update(prior.facts.country(label) for label in labels)
            evidence.append(dict(source_club=source['club_name'],original_player=matching[0],raw_proof=proof,
                approves_current_club_ownership=False))
        if not valid or not evidence or len(values)!=1 or None in values:
            unresolved.append(dict(carrier_id=carrier,reason='period country absent, ambiguous or raw reparse refused'))
            continue
        nationality=next(iter(values))
        try:
            code,label=native_country(nationality,codes)
        except ValueError as exc:
            unresolved.append(dict(carrier_id=carrier,reason=str(exc)));continue
        before_country=raw[end+8]^0x61
        if before_country==code and player['facts']['nationality']==nationality:
            unresolved.append(dict(carrier_id=carrier,reason='already source-correct in native and recipe'));continue
        updates.append(dict(carrier_id=carrier,fields=['nationality'],native_name=native['name'],
            before_player=copy.deepcopy(player),before_nationality_code=before_country,
            source_person=witnesses[0]['source_person'],nationality=nationality,native_country_code=code,
            native_label=label,nationality_evidence=evidence,
            representability='proven-native-capacity-XXX' if label=='XXX' else 'native-country-label'))
    result=dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=digest(jug),eq_sha256=digest(eq),
        original_person_document=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        targets=targets,period_source_bindings=bindings,updates=updates,unresolved=unresolved,
        implementation_inputs=[dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p))
            for p in (Path(__file__),registry.ROOT/'scripts/season_original_secondary_facts_v1.py',
                registry.ROOT/'scripts/build_2015_english92_release.py',base.game_path/'DBDAT/TEXTOS.PKF')],
        scope='Only exact selected nationality bytes/recipe country/default declarations and source artifact. Unsupported published countries retain original codes with nativeXXX. CGO uses CONGO, not COD/ZAIRE. All identities/DOB/roles/skills/ownership/tactics/managers/assets unchanged; no August ownership approval.')
    result['transaction_id']=digest(packages.canonical_json_bytes(result))[:24]
    return result


def verify(base,plan):
    binding=plan['original_person_document'];path=registry.ROOT/binding['path']
    if (plan.get('schema')!=SCHEMA or registry.sha256_file(path)!=binding['sha256']
            or prepare(base,path,plan['targets'])!=plan):
        raise ValueError('period country policy source/native plan no longer reproduces')


def bind(package,plan):
    if plan.get('schema')!=SCHEMA:
        raise ValueError('country policy recipe schema differs')
    result=copy.deepcopy(package)
    for row in plan['updates']:
        players=[p for p in result['players'] if p['carrier_id']==row['carrier_id']]
        if players!=[row['before_player']]:
            raise ValueError('country policy exact actor recipe preimage differs')
        players[0]['facts']['nationality']=row['nationality']
        if 'fact_fallbacks' in players[0]:
            players[0]['fact_fallbacks']=[f for f in players[0]['fact_fallbacks'] if f['field']!='nationality']
    result['artifacts'].append(dict(id=PREFIX+plan['transaction_id'],kind='season-input',relative_path=filename(plan),
        sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    if plan.get('schema')!=SCHEMA or not plan.get('updates') or digest(eq)!=plan['eq_sha256']:
        raise ValueError('nonempty country-only schema and exact EQ required')
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if digest(before)!=plan['jug_sha256']:
        raise ValueError('country policy immutable native baseline changed')
    countries={r['carrier_id']:r['native_country_code'] for r in plan['updates']}
    if len(countries)!=len(plan['updates']):
        raise ValueError('country policy duplicates a carrier')
    after,_=rewrite_indexed_native_nationalities(before,countries)
    if jug not in (before,after):
        raise ValueError('country policy input neither exact whole preimage nor postimage')
    return after,eq


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('versioned period-country recipe requires exact SOURCE reconstruction')


def reconstruction(previous,release_id):
    relative=previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        return None
    path=registry.ROOT/relative;plan=pipeline.read_json_file(path)
    if plan.get('schema')!=SCHEMA:
        return None
    receipt=pipeline.read_json_file(previous.compiler_receipt_path)
    if (receipt.get('compilation_mode')!=MODE
            or path.resolve()!=(previous.package_path.parent/filename(plan)).resolve()
            or registry.sha256_file(path)!=receipt['original_profile_assignment_plan_sha256']):
        raise ValueError('country policy original source artifact binding differs')
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    if bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(previous.package_path):
        raise ValueError('country policy SOURCE would discard recipe edits')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('country policy SOURCE descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():
        raise ValueError('country policy whole SOURCE recipe differs')
    return dict(season=previous.season,complete_game_inventory_identical=True,complete_recipe_identical=True)
