"""Close a proved dual-role warning without changing a correct native player."""
import argparse
import copy
from datetime import UTC, datetime
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from scripts import season_exact_primary_position_delta_v2 as roles
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = roles.registry.ROOT / '.local/consolidated-audit-20261009/period-secondary-position-adjudications-20261017'


def confirm(player, native, fifa_row, annual_players):
    if player['facts']['birth_date'] != fifa_row['dob']:
        raise ValueError('secondary position person birthday differs')
    labels = fifa_row['player_positions'].split(', ')
    primary = roles.primary(labels[0])
    fine = list(dict.fromkeys(roles.fifa.ROLE_MAP[label] for label in labels))[:6]
    fine = roles.conservative.preserve_cb_side(dict(fine_roles=fine,
        before_native_roles=native['roles'], source=fifa_row))
    broad = {roles.primary(label) for label in labels}
    active = [value for value in native['roles'] if value != 98]
    if (len(broad) < 2 or native['position'] != primary
            or player['facts']['primary_position'] != primary
            or active != fine or player['facts']['fine_roles'] != fine):
        raise ValueError('native primary and complete secondary roles do not match period FIFA')
    accepted = roles.annual_person_names(player, fifa_row)
    if not annual_players or any(
            row.get('birth_date') != fifa_row['dob']
            or roles.roster.normalise(row['name']) not in accepted
            or row.get('position') not in broad for row in annual_players):
        raise ValueError('original annual exact-person role not covered by period role set')
    if not any(row['position'] != primary for row in annual_players):
        raise ValueError('not a warning explained by a sourced secondary broad role')
    return dict(primary_position=primary, fine_roles=fine,
                annual_broad_positions=sorted({row['position'] for row in annual_players}),
                exact_FIFA_positions=labels, native_changes_required=False,
                August_ownership_or_match_deployment_approved=False)


def main(previous_version):
    season, carrier = '2017-18', 18201
    output = ROOT.parent / f'release-delivery-checklist-v{previous_version+1}.json'
    proof_path = ROOT / 'Donohue2017-dual-role-original-proof.json'
    if output.exists() or proof_path.exists():
        raise ValueError('completed secondary-role adjudication must not repeat')
    previous_path = ROOT.parent / f'release-delivery-checklist-v{previous_version}.json'
    previous = roles.pipeline.read_json_file(previous_path)
    initial = bindings()
    if initial != previous['current_release_bindings']:
        raise ValueError('preferred releases advanced before secondary-role review')
    release = roles.registry.load_preferred_release(season)
    package = roles.pipeline.read_json_file(release.package_path)
    player = next(p for p in package['players'] if p['carrier_id'] == carrier)
    data = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entry = next(e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id == carrier)
    payload = entry.decode_payload(data)
    native = roles.roster.native_player(payload, carrier)
    end = native['name_end']
    native_date = datetime(int.from_bytes(bytes(v ^ 0x61 for v in payload[end+14:end+16]), 'little'),
        payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).date().isoformat()
    if (native_date != player['facts']['birth_date'] or
            roles.roster.normalise(native['name']) != roles.roster.normalise(player['name'])):
        raise ValueError('actual native person differs from declared actor')
    fifa_path = roles.fifa.identity.old.FIFA
    fifa_sha = roles.registry.sha256_file(fifa_path)
    fifa_row = roles.fifa.match(player, season, roles.fifa.index(fifa_sha))
    if fifa_row is None:
        raise ValueError('no unambiguous exact-target-edition original FIFA person')
    captures, source_bindings = roles.roster.load_sources(season)
    verifier = roles.roster.SourceVerifier(season)
    annuals, originals = [], []
    for capture in captures:
        rows = [r for r in capture['players'] if r.get('birth_date') == native_date
                and roles.roster.normalise(r['name']) in roles.annual_person_names(player, fifa_row)]
        if not rows:
            continue
        if len(rows) != 1:
            raise ValueError('multiple annual exact-person rows in one capture')
        proof = verifier.verify(capture)
        if proof['status'] != 'raw-source-reparsed':
            raise ValueError('matching annual original did not independently reparse')
        annuals += rows
        originals.append(dict(club=capture['club_name'], player=rows[0], original=proof))
    verdict = confirm(player, native, fifa_row, annuals)
    finding_id = f'country-source-position-{season}-{carrier}'
    findings = [r for r in previous['additional_confirmed_findings'] if r['id'] == finding_id]
    if len(findings) != 1 or findings[0]['state'] != 'open-dated-annual-broad-position-conflict':
        raise ValueError('no unique still-open frozen position followup')
    roles.pipeline.assert_tree_matches_inventory(release.game_path,
        roles.pipeline.read_json_file(release.inventory_path))
    if bindings() != initial:
        raise ValueError('preferred releases changed during source adjudication')
    def bind(path):
        return dict(path=roles.registry.relative_workspace_path(path), sha256=roles.registry.sha256_file(path))
    ROOT.mkdir(parents=True, exist_ok=True)
    retained(proof_path, dict(utc=datetime.now(UTC).isoformat(), season=season, carrier_id=carrier,
        release_id=release.release_id, release_manifest_sha256=release.manifest_sha256,
        native=native, native_birth_date=native_date, original_FIFA=fifa_row,
        original_FIFA_file=bind(fifa_path), original_annuals=originals,
        source_bindings=source_bindings, verdict=verdict,
        implementation=[bind(Path(__file__)), bind(Path(roles.__file__))],
        native_writes=0, preferred_writes=0, cross_club_cases_closed=0,
        machine='joe-Vostro-3350', source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))
    result = copy.deepcopy(previous)
    for finding in result['additional_confirmed_findings']:
        if finding['id'] == finding_id:
            finding.update(state='resolved-legitimate-period-secondary-position',
                correction_evidence=bind(proof_path), native_fix_required=False)
    result['delivered_evidence'].append(bind(proof_path))
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=bind(previous_path),
                  fresh_runtime_runs_this_checklist=[], all_required_work_complete=False)
    roles.pipeline.write_canonical_json(output, result)
    print(dict(legitimate_secondary_role_cases_closed=1, native_writes=0, cross_club_cases_closed=0), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-version', type=int, required=True)
    main(parser.parse_args().previous_version)
