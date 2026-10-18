"""Build the admitted versioned country corrections without changing defaults.

One bounded worker keeps transient disk use low while r127 still builds. Every
year uses its complete r127/r128 parent; no unaffected game is regenerated.
Source refusals and source-complete-but-not-delivered parents stay explicit.
"""
import argparse
from datetime import UTC,datetime
from pathlib import Path
import time

from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_original_country_policy_v2 as source
from scripts import build_original_country_defaults_20261017 as initial
from scripts import build_original_country_policy_v2_20261017 as builder
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=initial.ROOT.parent/'country-policy-v2-cohort-20261017'
DISCOVERY=initial.ROOT.parent/'original-country-policy-v2-discovery-20261017/discovery.json'
EARLY_ROOT=builder.ROOT
EARLY_RELEASE=builder.RELEASE
RELEASE='sourced-original-country-policy-cohort-20261017-r129a'
REPLAY='replayed-original-country-policy-cohort-20261017-r129b'


def main(initial_builder_pid):
    if ROOT.exists():
        raise ValueError('existing country policy cohort requires inspection, never blind rerun')
    ROOT.mkdir()
    discovery=pipeline.read_json_file(DISCOVERY)
    rows=[r for r in discovery['seasons'] if r['admitted']]
    initial_rows={r['season']:r for r in pipeline.read_json_file(initial.discovery.ROOT/'discovery.json')['seasons']}
    retained(ROOT/'batch-input.json',dict(discovery=dict(path=registry.relative_workspace_path(DISCOVERY),
        sha256=registry.sha256_file(DISCOVERY)),rows=rows,preferred_writes=0,script_workers=1))
    # The reusable explicit exporter lives in this process only; old r128 jobs
    # and immutable SOURCE policies are unaffected by this output namespace.
    builder.ROOT=ROOT;builder.RELEASE=RELEASE;builder.REPLAY=REPLAY
    results=[]
    for row in rows:
        season=row['season'];folder=ROOT/season;folder.mkdir()
        if initial_rows[season]['candidates']:
            proof=initial.ROOT/season/'complete-SOURCE-replay.json'
            while not proof.exists():
                if any((proof.parent/name).exists() for name in ('source-gap.json','build-failure.json')):
                    raise ValueError('initial country parent has a retained failure; inspect before rebasing')
                try:
                    command=Path(f'/proc/{initial_builder_pid}/cmdline').read_bytes()
                except FileNotFoundError as exc:
                    raise ValueError('initial country builder stopped without SOURCE proof; do not rebuild it') from exc
                if b'scripts.build_original_country_defaults_20261017' not in command:
                    raise ValueError('initial country builder PID identity changed')
                time.sleep(10)
            base=registry.load_registered_release(season,initial.RELEASE)
        else:
            base=registry.load_preferred_release(season)
        if (EARLY_ROOT/season/'complete-SOURCE-replay.json').exists():
            base=registry.load_registered_release(season,EARLY_RELEASE)
        actors={p['carrier_id']:p for p in pipeline.read_json_file(base.package_path)['players']}
        admission=pipeline.read_json_file(registry.ROOT/row['admission']['path'])
        if registry.sha256_file(registry.ROOT/row['admission']['path'])!=row['admission']['sha256']:
            raise ValueError('bound source-admission document changed')
        original={r['carrier_id']:r for r in admission['updates']}
        selected=[r['carrier_id'] for r in row['admitted']]
        for carrier in selected:
            before=original[carrier]['before_player'];current=actors[carrier]
            if (source.original.audit.normalise(current.get('source_name') or current['name'])!=
                    source.original.audit.normalise(before.get('source_name') or before['name'])
                    or current['facts']['birth_date']!=before['facts']['birth_date']):
                raise ValueError('country policy admission identity changed across its selected parent')
        fresh=source.prepare(base,builder.PEOPLE,{str(n):['nationality'] for n in selected})
        retained(folder/'source-reconciliation.json',fresh)
        admitted=[r['carrier_id'] for r in fresh['updates']]
        if not admitted:
            result=dict(season=season,status='no-new-game-already-correct-or-unresolved',source_parent=base.release_id,
                unresolved=fresh['unresolved'],preferred_changed=False,source_complete_parent_not_delivery=True)
        else:
            try:
                builder.build(season,base.release_id,admitted)
                result=dict(season=season,status='actual-native-and-whole-SOURCE-complete',
                    source_parent=base.release_id,countries_corrected=len(admitted),unresolved=fresh['unresolved'],
                    preferred_changed=False,runtime_pending=True,
                    may_require_country_only_ancestor_delivery=True)
            except Exception as exc:
                result=dict(season=season,status='stopped-inspect-partial-state',
                    error=type(exc).__name__+': '+str(exc),automatic_rerun=False)
                retained(folder/'build-failure.json',result)
        retained(folder/'cohort-result.json',result);results.append(result);print(result,flush=True)
    retained(ROOT/'batch-summary.json',dict(utc=datetime.now(UTC).isoformat(),rows=results,
        preferred_changed=False,unaffected_seasons_regenerated=0,cross_club_cases_closed=0,
        global_historical_RC=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial-builder-pid',type=int,required=True)
    main(parser.parse_args().initial_builder_pid)
