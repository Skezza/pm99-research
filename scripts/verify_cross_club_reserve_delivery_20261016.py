"""Independent literal native facts and frozen-case disposition for r107."""
import hashlib
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_cross_club_reserve_repair_v1 as source
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_opening_order_repair_v1 as ownership
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_cross_club_reviewed_reserve_20261016 import ROOT, SEASON, RELEASE


def verify():
    release = registry.load_registered_release(SEASON, RELEASE)
    plan = pipeline.read_json_file(ROOT / SEASON / 'ownership-plan.json')
    base = registry.load_registered_release(SEASON, plan['release_id'])
    source.verify_plan(base, plan)
    before = pipeline.read_json_file(base.package_path)
    after = pipeline.read_json_file(release.package_path)
    old = {p['carrier_id']: p for p in before['players']}
    new = {p['carrier_id']: p for p in after['players']}
    if set(old) != set(new) or any(new[k] != old[k] for k in new if k != 9171):
        raise ValueError('cross-club repair changed another recipe player')
    for key in ('clubs', 'managers', 'competitions'):
        if before.get(key) != after.get(key):
            raise ValueError('cross-club repair changed club/order/manager/competition declarations')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
    preserve_other_records(original, jug, {9171})
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if eq != (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes():
        raise ValueError('cross-club repair changed actual roster/order/tactic bytes')
    owners = ownership.native_owners(eq)
    if owners.get(9171) != {311} or owners.get(2774) != {1251}:
        raise ValueError('actual City/Rangers player ownership differs')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    countries = delta.compiler._extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF')
    rows = []
    for carrier, name, birthday in ((9171, 'Shaun Wright-Phillips', '1981-10-25'),
                                  (2774, 'Andrei Kanchelskis', '1969-01-23')):
        raw = entries[carrier].decode_payload(jug)
        record = facts.native_facts(jug, carrier)
        end, roles = read_indexed_native_roles(raw, carrier)
        if (record['birth_date'] != birthday or record['name'].casefold() != name.casefold()
                or record['position'] != new[carrier]['facts']['primary_position']):
            raise ValueError('native identity/DOB/broad position readback differs')
        if raw[2:5] == bytes.fromhex('dd6361'):
            actual_values = {key: raw[len(raw)-16+i] ^ 0x61
                for i, key in enumerate((*delta.compiler.SKILLS, 'handling'))}
        elif raw[2:5] == bytes.fromhex('dd6360'):
            actual_values = {key: raw[end+18+i] ^ 0x61
                for i, key in enumerate((*delta.compiler.SKILLS, 'handling'))}
        else:
            raise ValueError('unproven selected player native family')
        if actual_values != new[carrier]['ratings']['values']:
            raise ValueError('independent literal ten-skill readback differs from actual recipe')
        if carrier == 9171:
            if (roles != [11,98,98,98,98,98] or record['startup_order'] != 16
                    or (raw[end+8] ^ 0x61) != delta.compiler._country_code('ENG', dict(countries))
                    or actual_values['handling'] != 8):
                raise ValueError('new actual reserve role/order/country/handling differs')
        elif record != facts.native_facts(original, carrier):
            raise ValueError('retained Rangers player facts changed')
        rows.append(dict(carrier_id=carrier, **record, native_roles=roles,
            native_country_code=raw[end+8] ^ 0x61, literal_native_values=actual_values))
    cross_path = ROOT.parent / 'cross-club-identities-enriched.json'
    frozen = pipeline.read_json_file(cross_path)
    season = next(s for s in frozen['seasons'] if s['season'] == SEASON)
    cases = [c for c in season['candidates'] if c['identity'] ==
        ['full-source-name-dob-candidate', 'andreikanchelskis', '1969-01-23']]
    if len(cases) != 1 or {p['carrier_id'] for p in cases[0]['players']} != {9171,2774}:
        raise ValueError('frozen cross-club case scope differs')
    remaining = [p for p in after['players'] if source.identity_key(p) == ('andreikanchelskis','1969-01-23')]
    added = [p for p in after['players'] if source.identity_key(p) == ('shaunwrightphillips','1981-10-25')]
    if [p['carrier_id'] for p in remaining] != [2774] or [p['carrier_id'] for p in added] != [9171]:
        raise ValueError('actual recipe retains/adds another copy of the source identities')
    old_files = {f['path']: f['sha256'] for f in pipeline.read_json_file(base.inventory_path)['files']}
    new_files = {f['path']: f['sha256'] for f in pipeline.read_json_file(release.inventory_path)['files']}
    allowed = {'DBDAT/JUG98030.FDI', 'DBDAT/MINIFOTO.PKF', 'DBDAT/MINIFOTO/J9609171.BMP'}
    if any(old_files.get(k) != new_files.get(k) for k in set(old_files) | set(new_files) if k not in allowed):
        raise ValueError('an unrelated actual game file changed')
    result = dict(season=SEASON, release_id=RELEASE, manifest_sha256=release.manifest_sha256,
        package_sha256=registry.sha256_file(release.package_path), JUG_sha256=hashlib.sha256(jug).hexdigest(),
        plan_sha256=registry.sha256_file(ROOT / SEASON / 'ownership-plan.json'),
        frozen_case_source=dict(path=registry.relative_workspace_path(cross_path), sha256=registry.sha256_file(cross_path)),
        frozen_case=cases[0], case_id=pipeline.canonical_json_sha256(dict(season=SEASON, case=cases[0])),
        native_readbacks=rows, all_other_native_records_identical=True,
        all_unselected_recipe_players_identical=True, all_roster_tactics_managers_and_kits_preserved=True,
        old_identity_retained_only_at_Rangers=True, new_reserve_not_duplicated=True,
        native_birthday_exact=True, actual_year_based_UI_age_expected=19,
        historical_age_at_August1=18, native_age_display_policy='Game uses year difference; do not alter the correct1981 birthday to manufacture a day-aware age display.',
        existing_case_resolved_in_candidate=True, preferred_and_runtime_pending=True)
    retained(ROOT / 'independent-native-case-proof.json', result)
    return result


if __name__ == '__main__':
    result = verify()
    print(dict(case_id=result['case_id'], actual_source_and_native_identity_fix=True,
        preferred_and_runtime_pending=True), flush=True)
