"""Independent literal identity/ten-skill readbacks of the private alias games."""
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_compiler_v2 as compiler
from scripts import season_within_club_reserve_repair_v1 as native
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts import build_stoke_commons_number_20261016 as first
from scripts import build_shtanyuk_2002_coupled_alias_20261016 as second


def verify(batch,expected):
    output=batch.ROOT/'actual-actor-readbacks.json'
    if output.exists():raise ValueError('completed independent alias readback must not repeat')
    release=registry.load_registered_release(batch.SEASON,batch.RELEASE)
    parent=registry.load_registered_release(batch.SEASON,'sourced-remaining-manager-tenures-20261016-r116a')
    data=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    old=(parent.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    preserve_other_records(old,data,set(expected))
    for name in ('EQ98030.FDI','ENT98030.FDI'):
        if (release.game_path/'DBDAT'/name).read_bytes()!=(parent.game_path/'DBDAT'/name).read_bytes():
            raise ValueError('alias changed another club/order/tactics/manager file')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(data).entries}
    countries=compiler._extract_country_codes_from_textos(release.game_path/'DBDAT/TEXTOS.PKF')
    package=pipeline.read_json_file(release.package_path)
    people={p['carrier_id']:p for p in package['players']};rows=[]
    for carrier,(birthday,position,owner) in expected.items():
        person=people[carrier];raw=entries[carrier].decode_payload(data)
        actual=native.native_facts(data,carrier);end,roles=read_indexed_native_roles(raw,carrier)
        if (actual['name'].casefold(),actual['birth_date'],actual['position'])!=(person['name'].casefold(),birthday,position):
            raise ValueError('literal actual name/birthday/position differs from the sourced replacement')
        club=next(c for c in package['clubs'] if c['id']==person['club_id'])
        if club['carrier_id']!=owner:raise ValueError('selected actor club changed')
        if roles[0]!=9:raise ValueError('new sourced midfield actor lacks the declared central role')
        offset=len(raw)-16 if raw[2:5]==bytes.fromhex('dd6361') else end+18
        values={key:raw[offset+i]^0x61 for i,key in enumerate((*compiler.SKILLS,'handling'))}
        if values!=person['ratings']['values']:
            raise ValueError('literal ten native skill values differ from the selected actor recipe')
        declared=person['facts']['nationality'];code=raw[end+8]^0x61
        if code!=compiler._country_code(declared,countries):
            raise ValueError('literal selected nationality byte differs from the explicit recipe policy')
        rows.append(dict(carrier_id=carrier,**actual,native_roles=roles,native_ten_skills=values,
            club=club['name'],declared_country=declared,native_country_code=code,
            country_fact_unknown=(declared=='XXX'),
            source_country_representable=(declared!='XXX' and code!=countries['XXX'])))
    retained(output,dict(season=batch.SEASON,release_id=batch.RELEASE,manifest_sha256=release.manifest_sha256,
        recipe_sha256=registry.sha256_file(release.package_path),rows=rows,
        all_unselected_player_payloads_identical_to_manager_parent=True,
        complete_native_club_order_tactics_and_manager_files_identical=True,
        original_source_replay_proof_sha256=registry.sha256_file(batch.ROOT/'complete-SOURCE-replay.json'),
        runtime_approval=False,cases_closed=0))
    print(dict(season=batch.SEASON,independent_literal_actor_readbacks=True,actors=len(rows),runtime_pending=True),flush=True)


if __name__=='__main__':
    verify(first,{27013:('1983-08-30','M',375)})
    verify(second,{10580:('1974-01-26','M',348),7972:('1969-08-23','M',757)})
