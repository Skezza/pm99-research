"""Recheck the old Eastleigh alternatives against actual current club owners.

Annual name/DOB coverage is entity evidence only, not August squad approval.
No regeneration, edits, new source downloads or duplicate-case closures.
"""
from datetime import UTC,datetime
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts import season_historical_roster_audit_v1 as roster
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/whole-club-next-current-v1'


def main():
    path=ROOT/'current-Eastleigh-alternatives.json'
    if path.exists():raise ValueError('completed current owner inspection must not repeat')
    base=registry.load_preferred_release('2014-15')
    packages=layers.package_layers(base)
    clubs=[c for _,p,_ in packages for c in p['clubs']]
    players={p['id']:p for _,package,_ in packages for p in package['players']}
    captures,_=roster.load_sources(base.season);verifier=roster.SourceVerifier(base.season)
    rows=[]
    for carrier in (3317,3322):
        club=next(c for c in clubs if c['carrier_id']==carrier)
        duplicate=[c for c in clubs if c['carrier_id']!=carrier and whole.club_keys(club['name'],club.get('full_name','')) &
            whole.club_keys(c['name'],c.get('full_name',''))]
        annual=[c for c in captures if c['source_path'].endswith('.txt') and roster.source_group(c['country_catalog'])=='england'
            and whole.club_keys(club['name']) & whole.club_keys(c['club_name'])]
        coverage=[]
        for source in annual:
            proof=verifier.verify(source)
            if proof['status']!='raw-source-reparsed':raise ValueError('current club annual did not independently replay')
            keys={(roster.normalise(p['name']),p.get('birth_date')) for p in source['players']}
            for candidate in [club]+duplicate:
                members=[players[pid] for pid in candidate['roster_player_ids']]
                matched=[p['carrier_id'] for p in members if roster.person_identity_key(p) in keys]
                coverage.append(dict(carrier_id=candidate['carrier_id'],club=candidate['name'],roster_count=len(members),
                    exact_full_source_name_DOB_matches=matched,exact_matches=len(matched),annual_original=proof,
                    full_original_annual_entity_match=(len(matched)==len(members)),opening_membership_approved=False))
        rows.append(dict(carrier_id=carrier,current_club=club['name'],capacity=len(club['roster_player_ids']),
            other_current_duplicate_labels=[dict(carrier_id=c['carrier_id'],name=c['name']) for c in duplicate],
            target_Eastleigh_already_represented=any(whole.club_keys('Eastleigh') & whole.club_keys(c['name'],c.get('full_name','')) for c in clubs),
            annual_entity_coverage=coverage,
            disposition='current-duplicate-label-needs-positive-complete-source-replacement' if duplicate else
                'not-a-current-duplicate-label-do-not-relabel-from-old-proposal; roster-review-separate'))
    ROOT.mkdir(parents=True,exist_ok=True)
    retained(path,dict(utc=datetime.now(UTC).isoformat(),machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',season=base.season,release_id=base.release_id,
        manifest_sha256=base.manifest_sha256,package_sha256=registry.sha256_file(base.package_path),rows=rows,
        native_writes=0,recipe_writes=0,cases_closed=0,original82_and_frozen2797_unchanged=True))
    print(dict(current_candidates=len(rows),current_duplicate_label_candidates=sum(bool(r['other_current_duplicate_labels']) for r in rows),
        native_writes=0,cases_closed=0),flush=True)


if __name__=='__main__':main()
