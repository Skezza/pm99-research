"""Bind this reviewed batch to the reusable atomic owned-roster transaction."""
from scripts.prepare_barrow2017_opening_source_20261017 import ROOT,FOLDER,source,retained
from scripts import season_verified_owned_roster_transaction_v1 as transaction


def main():
    cache=ROOT/'luna-closeout-20261017/accrington-tyler-provenance-20261017/cache'
    group=dict(club_name='Accrington',provider_team_id=42,competition='Football League Two',
        expected_opening_game_id=749360,schedule=source(cache/'team/42.html'),
        match=source(cache/'match/749360.html'),profiles={'78693':source(cache/'player/78693.html')})
    retained(FOLDER/'outside-opening-source-input.json',group)
    base=transaction.registry.load_preferred_release('2017-18')
    if base.release_id!='sourced-alias-primary-positions-20261017-r133a':
        raise ValueError('reviewed baseline changed')
    request=dict(schema=transaction.INPUT_SCHEMA,season=base.season,release_id=base.release_id,
        groups=[dict(club_carrier_id=3312,mode='complete-opening-squad',
                     source_input=transaction.fields.binding(FOLDER/'opening-source-input.json')),
                dict(club_carrier_id=324,mode='displaced-opening-reserves',
                     source_input=transaction.fields.binding(FOLDER/'outside-opening-source-input.json'),
                     replacements=[dict(carrier_id=9592,provider_player_id=78693)])])
    path=FOLDER/'owned-roster-source-input.json';retained(path,request)
    plan=transaction.prepare(base,path)
    transaction.verify(base,plan)
    retained(FOLDER/transaction.filename(plan),plan)
    package=transaction.bind(transaction.pipeline.read_json_file(base.package_path),plan)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after,after_eq=transaction.apply(before,eq,plan)
    if transaction.apply(after,after_eq,plan)!=(after,after_eq):raise ValueError('native transaction not idempotent')
    retained(FOLDER/'in-memory-native-proof.json',dict(transaction_id=plan['transaction_id'],
        source_people=len(plan['updates']),new_jug_sha256=transaction.digest(after),eq_unchanged=after_eq==eq,
        package_sha256=transaction.digest(transaction.packages.canonical_json_bytes(package)),
        complete_owned_orders=plan['groups'][0]['orders'],idempotent=True,
        native_files_written=0,release_published=False))
    print(dict(transaction_id=plan['transaction_id'],source_people=len(plan['updates']),
               native_in_memory_pass=True,native_files_written=0,release_published=False),flush=True)


if __name__=='__main__':main()
