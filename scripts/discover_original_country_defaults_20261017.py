"""Find exact-DOB period country conflicts for the existing one-byte writer.

No native writes or case closures. A source-backed country proposal requires a
unique replayed original biography plus unanimous independently reparsed dated
annual rows. All generated proposals still require the existing typed adapter,
actual native readback, whole SOURCE and runner evidence before promotion.
"""
from collections import defaultdict
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_original_secondary_facts_v1 as repair
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_player_facts_audit_v1 as facts
from scripts import season_published_person_identity_v1 as biographies
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT/'.local/consolidated-audit-20261009/original-country-defaults-20261017-v1'
PEOPLE = registry.ROOT/'.local/duplicate-ownership-v3/published-person-identities-r2.json'


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    if (ROOT/'discovery.json').exists():
        raise ValueError('completed country discovery must not repeat')
    doc = pipeline.read_json_file(PEOPLE)
    biographies.merge({}, doc)
    people = defaultdict(list)
    for batch in doc['batches']:
        for person in batch['people']:
            people[roster.normalise(person['name'])].append(person)
    results = []
    for season in registry.supported_seasons():
        saved = ROOT/(season+'.json')
        if saved.exists():
            results.append(pipeline.read_json_file(saved))
            continue
        release = registry.load_preferred_release(season)
        package = pipeline.read_json_file(release.package_path)
        targets = {}
        for player in package['players']:
            if player.get('policy') == 'preserve-existing-mode1':
                continue
            fallbacks = [f for f in player.get('fact_fallbacks', []) if f['field']=='nationality'
                         and f.get('method')=='deterministic-default']
            if len(fallbacks) != 1:
                continue
            name = repair.original.names.undecorated(player.get('source_name') or player['name'])
            candidates = people.get(roster.normalise(name), [])
            if (len(candidates)!=1 or candidates[0]['birth_date']!=player['facts'].get('birth_date')
                    or len(name.split())<2 or any(len(word.rstrip('.'))==1 for word in name.split())):
                continue
            targets[player['carrier_id']] = (player, candidates[0])
        sources, bindings = roster.load_sources(season)
        annuals = defaultdict(list)
        verifier = roster.SourceVerifier(season)
        needed = {(roster.normalise(p['name']),p['birth_date']) for _,p in targets.values()}
        for source in sources:
            hits = [p for p in source['players'] if (roster.normalise(p['name']),p.get('birth_date')) in needed]
            if not hits:
                continue
            proof = verifier.verify(source)
            for fact in hits:
                annuals[roster.normalise(fact['name']),fact.get('birth_date')].append(
                    dict(player=fact, source_club=source['club_name'], original=proof))
        candidates = []
        for carrier,(player,person) in sorted(targets.items()):
            witnesses = annuals.get((roster.normalise(person['name']),person['birth_date']),[])
            if not witnesses or any(w['original']['status']!='raw-source-reparsed' for w in witnesses):
                continue
            values = {facts.country(label) for w in witnesses
                      for label in (w['player'].get('nationalities') or [w['player'].get('nationality')])}
            if len(values)!=1 or None in values or values=={facts.country(player['facts'].get('nationality'))}:
                continue
            candidates.append(dict(carrier_id=carrier,name=player['name'],birth_date=person['birth_date'],
                before_country=player['facts']['nationality'],source_country=next(iter(values)),
                source_person_id=person['source_player_id'],original_annuals=witnesses,
                native_write_authorised=False,opening_ownership_approved=False))
        result=dict(season=season,release_id=release.release_id,manifest_sha256=release.manifest_sha256,
            package_sha256=registry.sha256_file(release.package_path),source_bindings=bindings,
            candidates=candidates,targets={str(r['carrier_id']):['nationality'] for r in candidates},
            main_layer_only=True,native_writes=0,case_closures=0)
        retained(saved,result);results.append(result)
        print(dict(season=season,period_country_candidates=len(candidates)),flush=True)
    retained(ROOT/'discovery.json',dict(utc=datetime.now(UTC).isoformat(),seasons=results,
        original_people=dict(path=registry.relative_workspace_path(PEOPLE),sha256=registry.sha256_file(PEOPLE)),
        candidate_count=sum(len(r['candidates']) for r in results),native_writes=0,case_closures=0,
        excludes_optional_missing_facts=True,exact_adapter_admission_still_required=True,
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))


if __name__=='__main__':
    main()
