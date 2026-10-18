"""Resolve the original Jimmy case only after actual positive owner correction."""
from scripts import season_verified_owned_roster_transaction_v1 as transaction
from scripts.publish_barrow2017_owned_transaction_20261017 import FOLDER,RELEASE
from scripts.prepare_barrow2017_opening_source_20261017 import ROOT,retained

CASE='a4003189b0b9eff91be12edd137f76d3d1e4627d56eaade807cb1d9ebb6a4ee7'


def main():
    release=transaction.registry.load_registered_release('2017-18',RELEASE)
    plan=transaction.pipeline.read_json_file(transaction.registry.ROOT/release.locator['sourced_profile_assignment_plan_path'])
    base=transaction.registry.load_registered_release('2017-18',plan['release_id'])
    inventory=ROOT/'luna-closeout-20261017/fixed-current-candidate-inventory.json'
    frozen=next(r for r in transaction.pipeline.read_json_file(inventory)['rows'] if r['case_id']==CASE)
    if frozen['season']!='2017-18' or {r['original']['carrier_id'] for r in frozen['observations']}!={9592,11214}:
        raise ValueError('frozen Jimmy case identity/carrier binding differs')
    package=transaction.pipeline.read_json_file(release.package_path)
    actors={p['carrier_id']:p for p in package['players']}
    clubs={c['id']:c for c in package['clubs']}
    matches=[p for p in actors.values() if transaction.identity(p)==('jimmydunne','1997-10-19')]
    if len(matches)!=1 or matches[0]['carrier_id']!=10989 or clubs[matches[0]['club_id']]['name']!='Barrow':
        raise ValueError('Jimmy is not unique at the positive opening owner')
    starter=next(r for r in plan['groups'][0]['source']['desired'] if r['source_person']['provider_player_id']==104226)
    if starter['membership']!='starting_xi' or starter['source_player']['birth_date']!='1997-10-19':
        raise ValueError('positive original first-XI identity missing')
    before=transaction.pipeline.read_json_file(base.package_path)
    retained_actor=next(p for p in before['players'] if p['carrier_id']==11214)
    if actors[11214]!=retained_actor or actors[11214]['source_name']!='Alex Lynch':
        raise ValueError('completed Chester correction changed')
    old=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    new=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    def payload(data):
        entry=next(e for e in transaction.IndexedFDIFile.from_bytes(data).entries if e.record_id==11214)
        return entry.decode_payload(data)
    if payload(old)!=payload(new):raise ValueError('prior corrected Lynch native bytes changed')
    if actors[9592]['source_name']!='Tyler Hornby-Forbes':raise ValueError('wrong Accrington copy not replaced')
    retained(FOLDER/'independent-frozen-case-proof.json',dict(manifest_sha256=release.manifest_sha256,
        case_id=CASE,season='2017-18',source_inventory=transaction.fields.binding(inventory),
        state='confirmed-fault-repaired-current-game',positive_opening_owner='Barrow',
        original_opening_date='2017-08-05',original_game_id=753821,new_correct_carrier=10989,
        replacement_carrier=9592,replacement='Tyler Hornby-Forbes',
        previous_Lynch_correction_exactly_preserved=True,original_cross_club_baseline_unchanged=True,
        runtime_pending=True))
    print(dict(exact_frozen_cases_corrected=1,runtime_pending=True),flush=True)


if __name__=='__main__':main()
