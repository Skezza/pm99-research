"""Read-only real two-edge rehearsal; never publish or regenerate a game."""
import hashlib
from scripts import season_release_registry_v1 as registry
from scripts import verify_country_only_ancestry_v1 as ancestry
from scripts.checkpoint_original_country_batch_v1 import check_country_code
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    root=registry.ROOT/'.local/consolidated-audit-20261009'
    output=root/'country-only-ancestry-20261017/real-two-edge-rehearsal.json'
    if output.exists():
        raise ValueError('completed read-only ancestry rehearsal must not repeat')
    output.parent.mkdir(parents=True,exist_ok=True)
    before=registry.CATALOG_PATH.read_bytes()
    base=registry.load_registered_release('2009-10','sourced-remaining-manager-tenures-20261016-r116a')
    actual=registry.load_registered_release('2009-10','sourced-original-country-policy-v2-20261017-r128a')
    edges=[ancestry.Edge('sourced-original-period-country-defaults-20261017-r127a',
        'replayed-original-period-country-defaults-20261017-r127b',
        root/'original-country-default-delivery-20261017-v1/2009-10'),
        ancestry.Edge(actual.release_id,'replayed-original-country-policy-v2-20261017-r128b',
        root/'original-country-policy-v2-delivery-20261017/2009-10')]
    updates,origins,proof=ancestry.verify(actual,base,edges)
    codes=ancestry.v2.compiler._extract_country_codes_from_textos(actual.game_path/'DBDAT/TEXTOS.PKF')
    proof['final_semantic_countries']=[dict(carrier_id=row['carrier_id'],
        nationality=row['nationality'],native_label=check_country_code(row,codes),
        source_plan=origins[row['carrier_id']]) for row in updates]
    after=registry.CATALOG_PATH.read_bytes()
    # This rehearsal uses explicitly retained releases, not mutable defaults.
    # A separate season's successful publication must not discard its proof.
    # The ACTUAL publication gate still requires all26 bindings unchanged.
    proof.update(before_catalog_sha256=hashlib.sha256(before).hexdigest(),
        after_catalog_sha256=hashlib.sha256(after).hexdigest(),
        preferred_catalog_unchanged_during_rehearsal=after==before,
        concurrent_external_default_advance_observed=after!=before)
    proof.update(rehearsal_only=True,preferred_writes=0,regenerated_seasons=0,
        does_not_approve_new_runtime_or_global_rosters=True)
    retained(output,proof)
    print(dict(real_SOURCE_edges_verified=len(proof['edges']),countries=len(updates),preferred_writes=0),flush=True)


if __name__=='__main__':main()
