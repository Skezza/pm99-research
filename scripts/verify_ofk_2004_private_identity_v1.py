"""Verify complete foreign source replacement against the pinned identity graph."""
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_published_person_identity_v1 as people
from scripts.verify_paired_club_identity_v1 import groups
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_duplicate_ownership_plan_v1 as planner


def verify(candidate, output, proposal_path):
    if output.exists(): raise ValueError('foreign identity evidence is immutable')
    receipt = pipeline.read_json_file(candidate / 'candidate-receipt.json')
    if registry.sha256_file(proposal_path) != receipt['source_proposal_sha256']:
        raise ValueError('private foreign source proposal changed')
    proposal = pipeline.read_json_file(proposal_path)
    baseline = registry.load_registered_release(proposal['season'], receipt['baseline_release_id'])
    before = pipeline.read_json_file(baseline.package_path)
    after = pipeline.read_json_file(candidate / 'season-package.json')
    index, snapshot = identities.load_identity_snapshot()
    tachira=proposal.get('schema_version') in ('pm99-private-original-tachira2014-verified-inputs-v1','pm99-private-original-tachira2015-verified-inputs-v1','pm99-private-original-jedinstvo2005-verified-inputs-v1','pm99-private-original-borac2003-verified-inputs-v1','pm99-private-original-italchacao2001-verified-inputs-v1','pm99-private-original-hajduk2002-verified-inputs-v1','pm99-private-original-monagas2003-verified-inputs-v1','pm99-private-original-monagas2002-verified-inputs-v1','pm99-private-original-sartid2000-verified-inputs-v1','pm99-private-original-estudiantes2000-verified-inputs-v1','pm99-private-original-mladost2001-verified-inputs-v1')
    input_path = (registry.ROOT / proposal['biography_input']['path'] if tachira
                  else source.AUDIT / 'ofk-2004-original-person-identities-v1.json')
    index, merge = people.merge(index, pipeline.read_json_file(input_path))
    if merge['refused']:
        raise ValueError('foreign biographies conflict with pinned publisher identities')
    old, new = groups(before, index), groups(after, index)
    if tachira:
        merged_before, merged_after = {}, {}
        for _, layer, path in planner.package_layers(baseline):
            merged_before.update({p['carrier_id']:p for p in layer['players']})
            chosen = after if path == baseline.package_path else layer
            merged_after.update({p['carrier_id']:p for p in chosen['players']})
        old = groups({'players':list(merged_before.values())}, index)
        new = groups({'players':list(merged_after.values())}, index)
    corrected = {r['carrier_id'] for r in proposal['allocation']}
    introduced = new.keys() - old.keys()
    if introduced or any(any(id in corrected for id, _ in rows) for rows in new.values()):
        raise ValueError('foreign replacement introduces or retains cross-club identity candidates')
    players = {p['carrier_id']: p for p in after['players']}
    if any(players.get(p['carrier_id']) != p for p in before['players'] if p['carrier_id'] not in corrected):
        raise ValueError('foreign source transaction changed an unselected recipe player')
    for collection, allowed in [('clubs', {proposal['before_club']['id']}), ('managers', {proposal['before_club']['manager_id']})]:
        current = {r['id']: r for r in after[collection]}
        if set(current) != {r['id'] for r in before[collection]} or any(
                current[r['id']] != r for r in before[collection] if r['id'] not in allowed):
            raise ValueError('foreign source transaction changed another club/manager')
    archive = (candidate / 'game/DBDAT/MINIFOTO.PKF').read_bytes()
    cleared, _ = native.delta.no_photo_archive(archive, corrected)
    if cleared != archive or any((candidate / 'game/DBDAT/MINIFOTO' / f'J96{id:05d}.BMP').exists() for id in corrected):
        raise ValueError('foreign replacement still has a displaced player portrait')
    rows = [p for p in after['players'] if p['carrier_id'] in corrected]
    count = len(proposal['allocation'])
    if len(rows) != count or len({p['person_id'] for p in rows}) != count:
        raise ValueError('foreign native source roster repeats canonical people')
    proof = dict(schema_version='pm99-foreign-independent-identity-difference-v1', season=proposal['season'],
        candidate_receipt_sha256=registry.sha256_file(candidate / 'candidate-receipt.json'),
        package_sha256=registry.sha256_file(candidate / 'season-package.json'),
        source_proposal_sha256=registry.sha256_file(proposal_path), identity_snapshot=snapshot,
        source_person_input=dict(path=registry.relative_workspace_path(input_path), sha256=registry.sha256_file(input_path)),
        before_cross_club_candidate_groups=len(old), after_cross_club_candidate_groups=len(new),
        introduced_candidate_groups=0, replacement_cross_club_candidates=0,
        corrected_slots=sorted(corrected), unselected_recipe_people_clubs_managers_identical=True,
        stale_portraits_cleared=True, source_persons_unique=True, registered=False,
        source_conflicts_and_secondary_facts_not_globally_approved=True)
    pipeline.write_canonical_json(output, proof)
    return proof


if __name__ == '__main__':
    verify(source.AUDIT / 'ofk-2004-private-game-v2', source.AUDIT / 'ofk-2004-independent-identity-v2.json',
        source.AUDIT / 'ofk-2004-fixed18-private-allocation-v2.json')
