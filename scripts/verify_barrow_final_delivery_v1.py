"""Independent readback for the private coupled Wrexham/retained Barrow fix."""
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.editor_actions import _read_native_dd6360_fields
from scripts import season_barrow_opening_repair_v1 as source
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_italian_opening_layer_v1 as roster
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_package_v2 as packages
from scripts import verify_paired_club_identity_v1 as identity
from scripts import season_published_person_identity_v1 as public
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph


def verify(release, output):
    if output.exists():
        raise ValueError('Barrow delivery readback is immutable')
    package = pipeline.read_json_file(release.package_path); packages.validate_package(package)
    plan_path = release.package_path.parent / source.FILENAME
    plan = pipeline.read_json_file(plan_path)
    artifact = next(a for a in package['artifacts'] if a['id'] == source.PREFIX + release.season)
    if registry.sha256_file(plan_path) != artifact['sha256']:
        raise ValueError('retained opening source artifact changed')
    baseline = registry.load_registered_release(release.season, plan['release_id'])
    jug = (release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    players = {p['carrier_id']:p for p in package['players']}
    clubs = {c['carrier_id']:c for c in package['clubs']}
    if clubs[3325]['name'] != 'Barrow' or clubs[3312]['name'] != 'Wrexham':
        raise ValueError('final retained/replaced club labels are incorrect')
    index, raw, rows = roster.roster_rows(eq,3325)
    if set(rows) != {(id,0) for id in set(source.REPLACE) | set(source.KEEP.values())}:
        raise ValueError('final Barrow roster readback differs')
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    native = parse_eq_external_team_roster_payload(raw,{})
    if native is None or native.short_name != 'Barrow' or native.full_club_name != 'Barrow':
        raise ValueError('actual native retained club label differs')
    ordered = []; readback = []
    countries = delta.compiler._extract_country_codes_from_textos(release.game_path/'DBDAT/TEXTOS.PKF')
    base_jug = (baseline.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    base_entries = {e.record_id:e for e in IndexedFDIFile.from_bytes(base_jug).entries}
    for id in sorted(source.REPLACE.keys() | source.KEEP.values()):
        p = players[id]; data = entries[id].decode_payload(jug)
        actual = source.core.roster.native_player(data,id); end = actual['name_end']
        fields = _read_native_dd6360_fields(data,end)
        born = f"{fields['birth_year']:04d}-{fields['birth_month']:02d}-{fields['birth_day']:02d}"
        roles = p['facts']['fine_roles']
        if isinstance(roles,dict):
            if roles != {'policy':'preserve-existing-mode1'}:
                raise ValueError('unsupported retained native role policy')
            base_entry = base_entries[id]
            expected_roles = source.core.roster.native_player(base_entry.decode_payload(base_jug),id)['roles']
            roles_match = actual['roles'] == expected_roles
        else:
            roles_match = {v for v in actual['roles'] if v!=98} == set(roles)
        if (actual['name'].casefold() != p['name'].casefold()
                or actual['position'] != p['facts']['primary_position'] or not roles_match):
            raise ValueError('native Barrow identity/roles differ from recipe')
        if isinstance(p['facts']['birth_date'],str) and born != p['facts']['birth_date']:
            raise ValueError('native Barrow birthday differs from recipe')
        if (fields['skills'] != [p['ratings']['values'][s] for s in delta.compiler.SKILLS]
                or fields['handling'] != p['ratings']['values']['handling']):
            raise ValueError('native Barrow skills differ from recipe')
        nationality = p['facts']['nationality']
        if isinstance(nationality,dict):
            if nationality != {'policy':'preserve-existing-mode1'}:
                raise ValueError('unsupported retained nationality policy')
            original = base_entries[id].decode_payload(base_jug)
            original_end = source.core.roster.native_player(original,id)['name_end']
            expected_nationality = _read_native_dd6360_fields(original,original_end)['visible_nationality_code']
        else:
            expected_nationality = delta.compiler._country_code(nationality,dict(countries))
        if fields['visible_nationality_code'] != expected_nationality:
            raise ValueError('native Barrow nationality differs from recipe')
        order = data[end] ^ 0x61
        expected = next(r['after'] for r in plan['orders'] if r['carrier_id']==id)
        if order != expected:
            raise ValueError('actual opening order differs from source plan')
        ordered.append((order,id,actual['position']))
        readback.append(dict(carrier_id=id,name=actual['name'],birth_date=born,position=actual['position'],startup_order=order))
    ordered.sort()
    xi = [r['carrier_id'] for r in plan['starting_xi']]
    if ([r[1] for r in ordered[:11]] != xi or ordered[0][2]!='G'
            or sum(r[2]=='G' for r in ordered[:11]) != 1
            or [r[1] for r in ordered[11:16]] != plan['original_published_bench']):
        raise ValueError('original full XI/bench does not read back')
    preserve_other_records((baseline.game_path/'DBDAT/JUG98030.FDI').read_bytes(),jug,
        set(source.REPLACE) | set(source.KEEP.values()))
    before_label = registry.load_registered_release(release.season,'sourced-barrow-retained-opening-20261010-r65d')
    preserve_other_records((before_label.game_path/'DBDAT/EQ98030.FDI').read_bytes(),eq,{3325})
    preserve_other_records((before_label.game_path/'DBDAT/ENT98030.FDI').read_bytes(),
        (release.game_path/'DBDAT/ENT98030.FDI').read_bytes(),{822})
    holders,names = _manager_graph(eq_path=release.game_path/'DBDAT/EQ98030.FDI',ent_path=release.game_path/'DBDAT/ENT98030.FDI')
    if names[822] != 'Bayliss' or [c['carrier_id'] for c in holders[822]] != [3325]:
        raise ValueError('actual dated manager/club ownership differs')
    corrected = set(source.REPLACE)
    archive = (release.game_path/'DBDAT/MINIFOTO.PKF').read_bytes()
    cleared,_ = delta.no_photo_archive(archive,corrected)
    if cleared != archive or any((release.game_path/'DBDAT/MINIFOTO'/f'J96{id:05d}.BMP').exists() for id in corrected):
        raise ValueError('old portrait is still attached to a new substitute')
    people,_ = identity.identities.load_identity_snapshot()
    input_path = registry.ROOT/plan['published_person_binding']['path']
    if registry.sha256_file(input_path) != plan['published_person_binding']['sha256']:
        raise ValueError('fixed identity reader input changed')
    people,_ = public.merge(people,pipeline.read_json_file(input_path))
    first = registry.load_registered_release(release.season,'sourced-goalkeeper-role-repairs-20261007-r50a')
    old = identity.groups(pipeline.read_json_file(first.package_path),people)
    new = identity.groups(package,people)
    if new.keys()-old.keys():
        raise ValueError('combined delivery introduces cross-club candidates')
    rowes = [p for p in package['players'] if p['club_id']==clubs[3325]['id'] and p.get('source_name')=='Danny Rowe']
    if len(rowes)!=1 or rowes[0]['carrier_id']!=11218 or rowes[0]['facts']['birth_date']!='1992-03-09':
        raise ValueError('legitimate young Rowe not uniquely retained')
    proof = dict(schema_version='pm99-independent-final-Barrow-coupled-delivery-v1',
        season=release.season,release_id=release.release_id,package_sha256=registry.sha256_file(release.package_path),
        original_xi_readback=True,original_published_bench_readback=True,unselected_native_records_exact=True,
        dated_Bayliss_exclusive_native_owner=True,stale_portraits_cleared=True,young_Rowe_count=1,
        before_cross_club_candidate_groups=len(old),after_cross_club_candidate_groups=len(new),
        introduced_candidate_groups=len(new.keys()-old.keys()),players=readback,
        historical_verification_complete=False,runtime_XI_captured=False,
        resolved_followups=['retained Barrow label and dated Bayliss manager'],
        remaining=[r for r in plan['remaining'] if not r.startswith('Retained wrong club label')]
            + ['Retained Barrow kit and ground historical identity not yet approved.'])
    pipeline.write_canonical_json(output,proof)
    return proof
