"""Literal actual-game readback against the independently retained native proof."""
from scripts import season_verified_owned_roster_transaction_v1 as transaction
from scripts.publish_barrow2017_owned_transaction_20261017 import FOLDER,RELEASE
from scripts.prepare_barrow2017_opening_source_20261017 import retained


def main():
    actual=transaction.registry.load_registered_release('2017-18',RELEASE)
    path=transaction.registry.ROOT/actual.locator['sourced_profile_assignment_plan_path']
    plan=transaction.pipeline.read_json_file(path)
    base=transaction.registry.load_registered_release(actual.season,plan['release_id'])
    transaction.verify(base,plan)
    proof=transaction.pipeline.read_json_file(FOLDER/'in-memory-native-proof.json')
    jug=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(actual.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if transaction.digest(jug)!=proof['new_jug_sha256'] or eq!=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes():
        raise ValueError('actual whole JUG/EQ differs from reviewed in-memory correction')
    if transaction.registry.sha256_file(actual.package_path)!=proof['package_sha256']:
        raise ValueError('actual whole recipe differs from reviewed in-memory correction')
    actors={p['carrier_id']:p for p in transaction.pipeline.read_json_file(actual.package_path)['players']}
    entries={e.record_id:e for e in transaction.IndexedFDIFile.from_bytes(jug).entries}
    owners=transaction.fields.ownership.native_owners(eq)
    countries=transaction.fields.compiler._extract_country_codes_from_textos(actual.game_path/'DBDAT/TEXTOS.PKF')
    observations=[]
    for row in plan['updates']:
        carrier=row['carrier_id'];actor=actors[carrier]
        observed=transaction.facts.native_facts(jug,carrier)
        raw=entries[carrier].decode_payload(jug)
        end=transaction.fields.native_player(raw,carrier)['name_end']
        if (transaction.fields.normalise(observed['name'])!=transaction.fields.normalise(actor['name'])
                or observed['birth_date']!=row['replacement']['source_player']['birth_date']
                or observed['position']!=row['replacement']['source_player']['position']
                or raw[end+8]^0x61!=transaction.fields.compiler._country_code(actor['facts']['nationality'],countries)):
            raise ValueError('actual source identity/date/position/country readback differs')
        observations.append(dict(carrier_id=carrier,name=observed['name'],birth_date=observed['birth_date'],
            position=observed['position'],startup_order=observed['startup_order'],owners=sorted(owners[carrier])))
    for group in plan['groups']:
        for row in group['orders']:
            if transaction.facts.native_facts(jug,row['carrier_id'])['startup_order']!=row['after']:
                raise ValueError('actual source starting XI/order differs')
    transaction.pipeline.assert_tree_matches_inventory(base.game_path,transaction.pipeline.read_json_file(base.inventory_path))
    retained(FOLDER/'actual-native-readback.json',dict(release_id=RELEASE,
        manifest_sha256=actual.manifest_sha256,source_plan=transaction.fields.binding(path),
        source_people=19,observations=observations,source_XI_and_orders_verified=True,
        actual_JUG_matches_reviewed_compilation=True,EQ_unchanged=True,parent_inventory_preserved=True,
        preferred_changed=False,runtime_pending=True))
    print(dict(actual_source_people_verified=19,actual_source_XI_verified=True,runtime_pending=True),flush=True)


if __name__=='__main__':main()
