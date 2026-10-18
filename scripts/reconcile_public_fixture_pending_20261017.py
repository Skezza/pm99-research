"""Carry discovery past already built changes without duplicating reserves.

Reuse registered source-complete parents, not another regeneration. A reserve
already introduced by a pending game cannot be added to another native slot.
"""
import copy
from datetime import UTC,datetime
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_frozen_fixture_reserve_v2 as source
from scripts.build_discovered_fixture_batches_20261017 import ROOT as PRIOR,RELEASE as PARENT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=PRIOR.parent/'frozen-fixture-next-batches-v2'


def reconcile():
    output=ROOT/'reconciled-discovery.json'
    if output.exists():raise ValueError('completed source reconciliation must not repeat')
    original=ROOT/'discovery.json';result=copy.deepcopy(pipeline.read_json_file(original));decisions=[]
    for row in result['seasons']:
        if not row['candidates']:continue
        season=row['season'];proof_path=PRIOR/season/'complete-SOURCE-replay.json'
        if not proof_path.exists():raise ValueError('expected pending source-complete parent is not proved')
        proof=pipeline.read_json_file(proof_path)
        if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:
            raise ValueError('pending parent lacks whole SOURCE equality')
        old=registry.load_registered_release(season,row['release_id']);parent=registry.load_registered_release(season,PARENT)
        before=pipeline.read_json_file(old.package_path);actual=pipeline.read_json_file(parent.package_path)
        pipeline.assert_tree_matches_inventory(parent.game_path,pipeline.read_json_file(parent.inventory_path))
        old_players={p['carrier_id']:p for p in before['players']};new_players={p['carrier_id']:p for p in actual['players']}
        represented={source.identity(p)[0] for p in actual['players']}
        before_jug=(old.game_path/'DBDAT/JUG98030.FDI').read_bytes();after_jug=(parent.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        before_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(before_jug).entries}
        after_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(after_jug).entries}
        accepted=[]
        for candidate in row['candidates']:
            if source.roster.normalise(candidate['replacement_name']) in represented:
                decisions.append(dict(season=season,candidate=candidate,status='reserve-already-introduced-by-source-complete-parent-do-not-duplicate',
                    required_next='Find another positively dated original opening reserve, or a complete club transaction; never clone this reserve again.'))
                continue
            for carrier in (candidate['displaced_carrier'],candidate['retained_carrier']):
                if (old_players[carrier]!=new_players[carrier] or before_entries[carrier].decode_payload(before_jug)!=
                        after_entries[carrier].decode_payload(after_jug)):
                    raise ValueError('selected source-disposition target changed in pending parent')
            accepted.append(candidate)
            decisions.append(dict(season=season,candidate=candidate,status='unchanged-selected-actors-rebased-to-source-complete-pending-parent',
                parent=parent.release_id,whole_SOURCE=source.binding(proof_path)))
        row.update(candidates=accepted,release_id=parent.release_id,manifest_sha256=parent.manifest_sha256,
            package_sha256=registry.sha256_file(parent.package_path),
            source_rebase=dict(previous_release_id=old.release_id,current_registered_source_parent=parent.release_id,
                selected_old_native_and_recipe_actors_identical=True,unaffected_seasons_regenerated=0))
    result.update(utc=datetime.now(UTC).isoformat(),original_discovery=source.binding(original),
        reconciliation=decisions,potential_repairs=sum(len(r['candidates']) for r in result['seasons']),
        native_writes=0,case_closures=0)
    retained(output,result)
    print(dict(source_candidates_after_pending_reconciliation=result['potential_repairs'],
        duplicate_reserve_proposal_blocked=sum(r['status'].startswith('reserve-already') for r in decisions),native_writes=0),flush=True)


if __name__=='__main__':reconcile()
