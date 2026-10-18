"""Source-bound nationality/ability-only deltas over an immutable playable game.

Never rebuild identities, roles, squads, tactics, managers, images or game code.
The exact old/new native record pair is checked, including every unknown byte.
"""
import copy
import hashlib
from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_v2 as packages,season_package_compiler_v2 as compiler
from scripts import season_historical_roster_audit_v1 as roster

SCHEMA='pm99-source-bound-nationality-or-rating-only-delta-v1'
PREFIX='source-bound-quality-only-'
MODE='known-good-baseline-source-bound-quality-only-v1'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return 'quality-only-'+plan['transaction_id']+'.json'
def artifact_id(plan):return PREFIX+plan['transaction_id']


def verified_source(base,kind):
    if kind=='woking-original-nationalities':
        from scripts import woking_original_nationalities_v1 as source
        return source.rows(base)
    if kind=='season-rating-calibration':
        from scripts import season_rating_calibration_v1 as source
        return source.rows(base)
    if kind=='season-rating-calibration-v3':
        from scripts import season_rating_calibration_v3 as source
        return source.rows(base)
    if kind=='season-rating-calibration-2015-english-v3':
        from scripts import season_2015_english_rating_calibration_v3 as source
        return source.rows(base)
    raise ValueError('unknown quality source policy')


def prepare(base,kind):
    rows,bindings=verified_source(base,kind)
    if not rows or len({r['carrier_id'] for r in rows})!=len(rows):raise ValueError('nonempty unique quality updates required')
    doc=dict(schema=SCHEMA,season=base.season,release_id=base.release_id,kind=kind,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        source_bindings=bindings,updates=rows,scope='Only declared nationality or ten native skill bytes; all identities/facts not selected/roles/orders/squads/tactics/managers/assets/EXE and unknown bytes exact.')
    doc['transaction_id']=digest(packages.canonical_json_bytes(doc))[:24]
    return doc


def verify(base,plan):
    # JSON has arrays, not Python tuples. Compare the canonical wire contract
    # so a declarative (low, high) policy pair survives its JSON round trip,
    # without weakening any source/preimage/transaction fingerprint.
    if plan.get('schema')!=SCHEMA or packages.canonical_json_bytes(prepare(base,plan['kind']))!=packages.canonical_json_bytes(plan):
        raise ValueError('quality sources/preimage no longer reproduce')


def bind(package,plan):
    if digest(packages.canonical_json_bytes(package))!=plan['package_sha256']:
        # Registered legacy JSON may use a different whitespace encoding.
        base=registry.load_registered_release(plan['season'],plan['release_id'])
        if registry.sha256_file(base.package_path)!=plan['package_sha256'] or pipeline.read_json_file(base.package_path)!=package:
            raise ValueError('quality recipe preimage differs')
    if plan['kind']=='season-rating-calibration-2015-english-v3':
        from scripts import season_2015_english_rating_calibration_v3 as english
        return english.bind(package,plan)
    result=copy.deepcopy(package);players={p['carrier_id']:p for p in result['players']}
    aid=artifact_id(plan)
    for row in plan['updates']:
        p=players[row['carrier_id']]
        if 'before_sha256' in row:
            if digest(packages.canonical_json_bytes(p))!=row['before_sha256']:
                raise ValueError('quality player identity/preimage differs')
        elif p!=row['before']:raise ValueError('quality player identity/preimage differs')
        if 'nationality' in row:
            p['facts']['nationality']=row['nationality']
            p['fact_fallbacks']=[f for f in p.get('fact_fallbacks',[]) if f['field']!='nationality']
        if 'ratings' in row:p['ratings']=copy.deepcopy(row['ratings'])
    result['artifacts'].append(dict(id=aid,kind='season-input',relative_path=filename(plan),
        sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    if plan['kind'] in ('season-rating-calibration','season-rating-calibration-v3'):
        from scripts.season_rating_calibration_v1 import SOURCE_ID as OLD_SOURCE
        from scripts.season_rating_calibration_v3 import SOURCE_ID as NEW_SOURCE
        SOURCE_ID=NEW_SOURCE if plan['kind']=='season-rating-calibration-v3' else OLD_SOURCE
        title=('Deterministic rating calibration v3: source identity/DOB FIFA matches or age-optional editorial estimates; unknown XI is not reserve'
            if plan['kind']=='season-rating-calibration-v3' else 'Deterministic rating calibration v2: exact identity/edition FIFA matches or explicit editorial estimates')
        result['sources'].append(dict(id=SOURCE_ID,title=title,
            proof_grade='reviewed-editorial',evidence_artifact_id=aid))
        result['sources'].sort(key=lambda s:s['id'])
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def record_patch(raw,carrier,row,countries):
    original=bytes(raw);end=roster.native_player(original,carrier)['name_end'];family=original[2:5].hex()
    if family not in ('dd6360','dd6361'):raise ValueError('unproved quality carrier family')
    allowed=set();changed=bytearray(original)
    if 'nationality' in row:
        code=compiler._country_code(row['nationality'],countries)
        if code==countries['XXX']:raise ValueError('quality nationality must be representable')
        allowed.add(end+8);changed[end+8]=code^0x61
    if 'ratings' in row:
        values=row['ratings']['values']
        if set(values)!=set(compiler.SKILLS)|{'handling'} or any(type(v)!=int or not 1<=v<=99 for v in values.values()):
            raise ValueError('quality ratings must be ten bounded integer abilities')
        start=end+18 if family=='dd6360' else len(original)-16
        if family=='dd6360':compiler._read_native_dd6360_fields(original,end)
        for i,key in enumerate((*compiler.SKILLS,'handling')):
            allowed.add(start+i);changed[start+i]=values[key]^0x61
    if any(a!=b for i,(a,b) in enumerate(zip(original,changed)) if i not in allowed):raise ValueError('quality patch changed an unknown byte')
    if len(changed)!=len(original):raise ValueError('quality patch changed native record length')
    return bytes(changed)


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();original_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if digest(original)!=plan['jug_sha256'] or eq!=original_eq:raise ValueError('quality native preimage/EQ differs')
    index=IndexedFDIFile.from_bytes(original);entries={e.record_id:e for e in index.entries}
    countries=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    replacements={r['carrier_id']:record_patch(entries[r['carrier_id']].decode_payload(original),r['carrier_id'],r,countries)
        for r in plan['updates']}
    candidate=compiler._rebuild_indexed(original,index,replacements)
    if jug not in (original,candidate):raise ValueError('quality requires exact whole native pre/postimage')
    from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
    preserve_other_records(original,candidate,set(replacements))
    return candidate,original_eq


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('quality-only recipe requires exact source-bound reconstruction')


def reconstruction(previous,release_id):
    path=previous.locator.get('sourced_profile_assignment_plan_path')
    if not path:return None
    path=registry.ROOT/path;plan=pipeline.read_json_file(path)
    if plan.get('schema')!=SCHEMA:return None
    from scripts import publish_historical_role_delta_v1 as publisher
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path)
    artifact=next(a for a in package['artifacts'] if a['id']==artifact_id(plan))
    if path.resolve()!=(previous.package_path.parent/filename(plan)).resolve() or registry.sha256_file(path)!=artifact['sha256']:
        raise ValueError('quality SOURCE artifact differs')
    if bind(pipeline.read_json_file(base.package_path),plan)!=package:raise ValueError('quality SOURCE would discard recipe edits')
    if plan['kind']=='season-rating-calibration-2015-english-v3':
        from scripts import season_2015_english_rating_calibration_v3 as english
        if english.overlay(previous)[0]!=english.updated_english(plan):raise ValueError('quality SOURCE would discard English recipe edits')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
        package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('quality SOURCE input is not exact inert descriptor')
    for r in (base,previous):pipeline.assert_tree_matches_inventory(r.game_path,pipeline.read_json_file(r.inventory_path))
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:raise ValueError('quality SOURCE recipe differs')
    if plan['kind']=='season-rating-calibration-2015-english-v3' and english.overlay(rebuilt)[0]!=english.overlay(previous)[0]:
        raise ValueError('quality SOURCE English recipe differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,complete_recipe_identical=True)
