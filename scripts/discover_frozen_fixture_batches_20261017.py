"""Find source-replay candidates for the reusable same-day fixture repair.

Discovery does not authorise corrections. Original raw fixtures and all native
preimages must still pass the source adapter before any game can be compiled.
No network, regeneration or new historical facts are needed for this scan.
"""
from collections import Counter
from datetime import UTC,datetime
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_frozen_fixture_reserve_v1 as source
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_historical_transfer_review_v1 as people
from scripts import season_within_club_reserve_repair_v1 as native
from scripts import season_package_compiler_v2 as compiler
from scripts.backfill_exact_opening_club_aliases_v1 import unique_capture
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/frozen-fixture-next-batches-v1'


def main():
    if (ROOT/'discovery.json').exists():raise ValueError('completed bound discovery must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    ledger=registry.ROOT/'.local/consolidated-audit-20261009/release-delivery-checklist-v57.json'
    previous=pipeline.read_json_file(ledger);closed={r['case_id'] for r in previous['cross_club_dispositions']}
    frozen_path=registry.ROOT/previous['cross_club_case_file'];frozen=pipeline.read_json_file(frozen_path)
    pin=registry.ROOT/'.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json'
    index,_,snapshot=context.load_snapshot(registry.ROOT/'.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb',pin)
    results=[]
    for group in frozen['seasons']:
        season=group['season'];base=registry.load_preferred_release(season)
        saved=ROOT/(season+'.json')
        if saved.exists():
            row=pipeline.read_json_file(saved)
            if (row['release_id'],row['manifest_sha256'],row['package_sha256'])!=(
                    base.release_id,base.manifest_sha256,registry.sha256_file(base.package_path)):
                raise ValueError('saved source discovery baseline advanced; preserve it and use a new root')
            results.append(row);print(dict(season=season,completed_discovery_reused=True),flush=True);continue
        main=next(pkg for label,pkg,_ in layers.package_layers(base) if label=='main')
        all_players=[p for _,pkg,_ in layers.package_layers(base) for p in pkg['players']]
        actors={p['carrier_id']:p for p in main['players']};clubs={c['id']:c for c in main['clubs']}
        global_names={source.identity(p)[0] for p in all_players};represented_ids=set()
        for actor in all_players:
            key=source.identity(actor)
            found=people.unique_person(dict(name=source.heading_name(actor.get('source_name') or actor['name']),facts=dict(birth_date=key[1])),index)
            if found is not None:represented_ids.add(found['source_player_id'])
        capture_path=registry.ROOT/f'.local/transfermarkt-opening-plans-current-v1/{season}/opening-lineups.json'
        if not capture_path.is_file():
            row=dict(season=season,release_id=base.release_id,manifest_sha256=base.manifest_sha256,
                package_sha256=registry.sha256_file(base.package_path),candidates=[],
                diagnostic_reasons={'separate-legacy-opening-source-route-needed':len(group['candidates'])},
                raw_source_approval=False,native_writes=0)
            retained(saved,row);results.append(row)
            print(dict(season=season,source_route='separate-legacy-opening-source-route-needed'),flush=True);continue
        capture=pipeline.read_json_file(capture_path)
        captures={};annuals={};candidates=[];reasons=Counter();allocated=set()
        jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
        def original_capture(club):
            if club['id'] not in captures:captures[club['id']]=unique_capture(club,capture['clubs'])
            return captures[club['id']]
        for case in group['candidates']:
            case_id=pipeline.canonical_json_sha256(dict(season=season,case=case))
            if case_id in closed:reasons['already-disposed']+=1;continue
            if case['identity'][0]!='published-person' or len(case['players'])!=2:
                reasons['needs-different-or-multi-owner-source-route']+=1;continue
            ids=[p['carrier_id'] for p in case['players']]
            if any(id not in actors for id in ids):reasons['not-in-main-layer']+=1;continue
            pair=[actors[id] for id in ids]
            if source.identity(pair[0])!=source.identity(pair[1]):reasons['current-identity-or-birthday-disagreement']+=1;continue
            key=source.identity(pair[0]);canonical=source.heading_name(pair[0].get('source_name') or pair[0]['name'])
            published=people.unique_person(dict(name=canonical,facts=dict(birth_date=key[1])),index)
            if published is None or published['source_player_id']!=case['identity'][1]:
                reasons['original-publisher-identity-unavailable-in-pin']+=1;continue
            matches=[original_capture(clubs[p['club_id']]) for p in pair]
            if any(r is None for r in matches):reasons['needs-other-original-fixture-provider']+=1;continue
            if matches[0]['first_league_fixture_date']!=matches[1]['first_league_fixture_date'] or not str(matches[0]['first_league_fixture_date']).startswith(season[:4]+'-08-'):
                reasons['needs-dated-transfer-or-different-fixture-route']+=1;continue
            pid=case['identity'][1]
            positive=[i for i,r in enumerate(matches) if any(str(p['source_player_id'])==str(pid) for p in r['starting_xi'])]
            if len(positive)!=1:reasons['not-one-positive-retained-XI']+=1;continue
            keep_index=positive[0];target_index=1-keep_index
            target=pair[target_index];keep=pair[keep_index];match=matches[target_index]
            if any(str(p['source_player_id'])==str(pid) for f in ('starting_xi','substitutes') for p in match[f]):
                reasons['published-membership-conflict']+=1;continue
            fields=native.native_facts(jug,target['carrier_id'])
            if fields['startup_order']<=11 or fields['position']=='G':reasons['native-starter-or-keeper-not-this-route']+=1;continue
            club=clubs[target['club_id']]
            try:
                if club['id'] not in annuals:annuals[club['id']]=native.annual_capture(season,club)
                annual,_=annuals[club['id']]
            except ValueError:reasons['needs-other-period-biography']+=1;continue
            possible=[]
            for reserve in sorted(match['substitutes'],key=lambda p:int(p['source_player_id'])):
                rid=int(reserve['source_player_id']);name=reserve['display_name'];name_key=roster.normalise(name)
                if name_key in global_names or rid in represented_ids or rid in allocated:continue
                rows=[p for p in annual['players'] if roster.normalise(p['name'])==name_key and p.get('birth_date') and p.get('position') in ('D','M','F')]
                if len(rows)!=1:continue
                # The full published name must pass the actual existing native
                # writer. No shortened-name guess or slot-recovery waiver.
                payload=entries[target['carrier_id']].decode_payload(jug)
                try:
                    old=compiler._player_name(payload,record_id=target['carrier_id'])
                    new=compiler._pm99_text(name,label='candidate published bench name')
                    compiler._patch_indexed_player_variable_name_payload(payload,old,new)
                except (ValueError,RuntimeError):continue
                possible.append((rid,name))
            if not possible:reasons['no-unused-full-name-fitting-original-bench-reserve']+=1;continue
            rid,name=possible[0];allocated.add(rid)
            candidates.append(dict(source_person_id=pid,displaced_carrier=target['carrier_id'],
                retained_carrier=keep['carrier_id'],replacement_name=name,replacement_source_person_id=rid,
                frozen_case_id=case_id,displaced_club=club['name'],retained_club=clubs[keep['club_id']]['name']))
        result=dict(season=season,release_id=base.release_id,manifest_sha256=base.manifest_sha256,
            package_sha256=registry.sha256_file(base.package_path),source_capture=source.binding(capture_path),
            candidates=candidates,diagnostic_reasons=dict(reasons),raw_source_approval=False,native_writes=0)
        results.append(result)
        retained(saved,result)
        print(dict(season=season,potential_original_fixture_repairs=len(candidates)),flush=True)
    retained(ROOT/'discovery.json',dict(utc=datetime.now(UTC).isoformat(),
        checklist=source.binding(ledger),frozen_cases=source.binding(frozen_path),snapshot=snapshot,seasons=results,
        potential_repairs=sum(len(r['candidates']) for r in results),native_writes=0,case_closures=0,
        next='Prepare selected per-season original source plans; diagnostics alone cannot publish.',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',machine='joe-Vostro-3350'))


if __name__=='__main__':main()
