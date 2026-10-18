"""Close two already-delivered cross-club cases without rebuilding any game.

Requires existing source/native/SOURCE/runtime delivery evidence plus independent
current global identity, native ownership and dated retained first-XI readback.
"""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.season_historical_roster_audit_v1 import normalise
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.checkpoint_frozen_fixture_reserve_v1 import next_count

ROOT = registry.ROOT / '.local/consolidated-audit-20261009'
CASES = ((27064, 10996, 'Richard Brodie', 'Brett Ormerod', 104412),
         (27062, 10994, 'Izak Reid', 'Glen Little', 67396))


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def main():
    previous_path = ROOT / 'release-delivery-checklist-v107.json'
    output = ROOT / 'release-delivery-checklist-v108.json'
    proof_path = ROOT / 'luna-closeout-20261017/barrow-two-current-dispositions.json'
    if output.exists() or proof_path.exists():
        raise ValueError('inspect immutable completed reconciliation instead of repeating it')
    previous = pipeline.read_json_file(previous_path)
    # A ledger-only update cannot disguise a changed preferred game.
    catalog = registry.load_catalog()
    for row in previous['current_release_bindings']:
        current = catalog[row['season']]
        if (current['release_id'], current['release_manifest_sha256']) != (
                row['release_id'], row['manifest_sha256']):
            raise ValueError('preferred bindings advanced; preserve and reconcile explicitly')
    delivery = next(c['delivery'] for c in previous['within_club_cases']
        if c.get('delivery', {}).get('release_id') == 'sourced-barrow-retained-label-manager-20261010-r65e')
    for evidence in delivery['evidence']:
        if registry.sha256_file(registry.ROOT / evidence['path']) != evidence['sha256']:
            raise ValueError('existing source/native/SOURCE/runtime evidence changed')
    for filename in ('barrow-wrexham-full-rebuild-proof-v1.json',
            'barrow-retained-opening-full-rebuild-proof-v2.json',
            'barrow-retained-label-manager-full-rebuild-proof-v2.json'):
        replay = pipeline.read_json_file(ROOT / filename)
        if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
            raise ValueError('prior full SOURCE evidence incomplete')
    base = registry.load_preferred_release('2012-13')
    package = pipeline.read_json_file(base.package_path)
    actors = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    owners = ownership.native_owners((base.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    source_path = registry.ROOT / '.local/transfermarkt-opening-plans-current-v1/2012-13/opening-lineups.json'
    sources = pipeline.read_json_file(source_path)
    captured = [c for c in sources['clubs'] if c['source_selector'].get('transfermarkt_club_id') == 3697]
    if len(captured) != 1:
        raise ValueError('retained original Morecambe fixture ambiguous')
    positive = opening.verify_opening(captured[0], sources, source_path.parent / 'cache')
    if positive['date'] != '2012-08-18':
        raise ValueError('retained first fixture date differs')
    proposal_path = ROOT / 'barrow-2012-retirement-source-v1/3312-wrexham-source.json'
    proposal = pipeline.read_json_file(proposal_path)
    frozen_path = registry.ROOT / previous['cross_club_case_file']
    frozen = next(g['candidates'] for g in pipeline.read_json_file(frozen_path)['seasons']
        if g['season'] == '2012-13')
    dispositions = []
    for keep, replace, name, new_name, person in CASES:
        candidates = [c for c in frozen if {p['carrier_id'] for p in c['players']} == {keep, replace}]
        if len(candidates) != 1 or str(person) not in positive['starting_xi']:
            raise ValueError('frozen pair or positive original retained starter differs')
        case = candidates[0]
        allocation = next(r for r in proposal['allocation'] if r['carrier_id'] == replace)
        if allocation['before_recipe']['source_name'] != name:
            raise ValueError('original displaced preimage differs')
        replacement = allocation['replacement']['source_player']
        if replacement['name'] != new_name:
            raise ValueError('positive original complete-club replacement differs')
        reads = []
        for carrier, wanted in ((keep, name), (replace, new_name)):
            matching = [p for p in package['players'] if normalise(p.get('source_name') or p['name']) == normalise(wanted)]
            if len(matching) != 1 or matching[0]['carrier_id'] != carrier:
                raise ValueError('identity still duplicated or moved outside original pair')
            actor = actors[carrier]
            club = clubs[actor['club_id']]
            native = facts.native_facts(jug, carrier)
            if (owners.get(carrier) != {club['carrier_id']}
                    or normalise(native['name']) != normalise(actor['name'])
                    or native['birth_date'] != actor['facts']['birth_date']):
                raise ValueError('actual native identity or exclusive owner differs')
            reads.append(dict(carrier_id=carrier, name=wanted, club=club['name'], native=native))
        if clubs[actors[keep]['club_id']]['carrier_id'] != 378 or clubs[actors[replace]['club_id']]['name'] != 'Wrexham':
            raise ValueError('actual retained/replacement club identity differs')
        if actors[replace]['facts']['birth_date'] != replacement['birth_date']:
            raise ValueError('current replacement birthday differs from delivered source')
        dispositions.append(dict(case_id=pipeline.canonical_json_sha256(dict(season='2012-13', case=case)),
            season='2012-13', state='confirmed-fault-repaired-current-game',
            retained_native_carrier=keep, replaced_native_carrier=replace,
            replacement=new_name, retained_owner='Morecambe', source_person_id=person,
            current_native_readback=reads, positive_original_first_XI=positive))
    remaining = next_count(previous, dispositions)
    proof = dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        current_release_id=base.release_id, current_manifest_sha256=base.manifest_sha256,
        previous_checklist=binding(previous_path), frozen_cases=binding(frozen_path),
        retained_original_fixture=binding(source_path), delivered_source_proposal=binding(proposal_path),
        existing_delivery_evidence=delivery['evidence'], dispositions=dispositions,
        regenerated_seasons=0, native_writes=0, reused_original_runtime=True,
        limitations=['No new runner capture; prior source-bound whole-club captures reused.',
            'This closes duplicate ownership only, not every secondary fact of these players.'])
    retained(proof_path, proof)
    result = copy.deepcopy(previous)
    for disposition in dispositions:
        result['cross_club_dispositions'].append(dict(disposition, delivery=binding(proof_path)))
    result.update(utc=proof['utc'], previous_checklist=binding(previous_path),
        remaining_cross_club_cases=remaining, all_required_work_complete=False,
        fresh_runtime_runs_this_checklist=[],
        next_batch='Continue source-backed ownership fixes and current-global reconciliation; Barnet2018 private native build pending.')
    result['delivered_evidence'].append(binding(proof_path))
    retained(output, result)
    print(dict(checklist=registry.relative_workspace_path(output), newly_reconciled_cases=2,
        remaining_cross_club_cases=remaining, rebuilt_games=0), flush=True)


if __name__ == '__main__':
    main()
