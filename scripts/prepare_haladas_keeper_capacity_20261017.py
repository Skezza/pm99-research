"""Prove published surname fits this exact slot's reversible native window."""
from app.fdi_indexed import IndexedFDIFile
from scripts import adjudicate_haladas_opening_keeper_20261017 as source
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    output=source.ROOT/'same-slot-published-surname-capacity-preflight.json'
    if output.exists():raise ValueError('completed native capacity proof must not be overwritten')
    base=source.registry.load_preferred_release('2000-01')
    case=source.decision(base)
    prior_path=source.registry.ROOT/'.local/historical-role-deltas-v1/2000-01/opening-same-carrier-capacity-repairs-20261006-r39a/ownership-plan-cf1b39392437.json'
    prior=source.pipeline.read_json_file(prior_path)
    bundle=prior['bindings']['same_carrier_name_capacity']
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    prepared,proof=capacity.recover_slot(jug,8507,bundle)
    entry=next(e for e in IndexedFDIFile.from_bytes(prepared).entries if e.record_id==8507)
    payload=entry.decode_payload(prepared);before=capacity.compiler._player_name(payload,record_id=8507)
    patched,_=capacity.compiler._patch_indexed_player_variable_name_payload(payload,before,'Kurucsai')
    if capacity.compiler._player_name(patched,record_id=8507).casefold()!='kurucsai':
        raise ValueError('published match surname not exactly readable after same-slot name edit')
    retained(output,dict(season=base.season,release_id=base.release_id,manifest_sha256=base.manifest_sha256,
        source_decision=case,factory_recovery_runtime_bundle=bundle,same_slot_recovery=proof,
        published_display_name='Kurucsai',surname_source='literal original2000 first-match goalkeeper',
        national_biography_identity='Kornél Kurucsai / Kurucsai Kornél /1972-01-18',
        native_writes=0,game_built=False,frozen_cases_closed=0,
        policy='Existing runtime-proven same-carrier exact shrink inverse only. No arbitrary string growth, no surname truncation, no portrait or starter-ownership waiver.'))
    print(dict(published_surname_fits_verified_same_slot=True,recovered_capacity_bytes=proof['recovery']['recovered_name_bytes'],native_writes=0),flush=True)


if __name__=='__main__':main()
