"""Source-admit the visible2017 followups without altering any default/game."""
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_exact_primary_position_delta_v1 as positions
from scripts import season_number_label_names_v2 as names
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/2017-visible-followups-20261017'
BASE='sourced-resolved-period-country-20261017-r130a'


def main():
    if (ROOT/'source-admission.json').exists():raise ValueError('completed visible-facts admission must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    base=registry.load_registered_release('2017-18',BASE)
    rows=[]
    for carrier in (10065,10683,18201):
        try:
            plan=positions.prepare(base,[carrier])
            path=ROOT/(str(carrier)+'-position-plan.json');retained(path,plan)
            row=dict(carrier_id=carrier,status='original-annual-and-exact-FIFA-position-admitted',
                source_plan=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
                primary_position=plan['updates'][0]['primary_position'],fine_roles=plan['updates'][0]['fine_roles'])
        except ValueError as exc:
            row=dict(carrier_id=carrier,status='not-admitted-no-native-change',reason=str(exc))
        rows.append(row)
        print(row,flush=True)
    plan=names.prepare(base);path=ROOT/'numeric-name-plan.json';retained(path,plan)
    retained(ROOT/'source-admission.json',dict(season='2017-18',release_id=BASE,
        manifest_sha256=base.manifest_sha256,position_rows=rows,
        source_admitted_numeric_names=len(plan['updates']),name_unresolved=len(plan['unresolved']),
        numeric_name_plan=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        native_writes=0,preferred_writes=0,not_game_delivery=True))
    print(dict(source_admitted_names=len(plan['updates']),unresolved_names=len(plan['unresolved']),native_writes=0),flush=True)


if __name__=='__main__':main()
