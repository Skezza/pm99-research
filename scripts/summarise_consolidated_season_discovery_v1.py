#!/usr/bin/env python3
"""Consolidate pinned all-season evidence into one classified delivery ledger."""
import argparse
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import consolidated_season_discovery_v1 as discovery
from scripts import season_release_registry_v1 as registry


def run(output, roster_store):
    snapshot = json.loads((output / 'snapshot.json').read_text())
    assert discovery.bindings() == snapshot['rows'], 'Release bindings drifted'
    qa = []
    evidence = []
    for row in snapshot['rows']:
        path = output / 'quality' / row['season'] / 'qa-report.json'
        report = json.loads(path.read_text())
        assert report['inputs']['package_sha256'] == row['package_sha256']
        qa.append(report)
        evidence.append({'path': str(path), 'sha256': registry.sha256_file(path)})
    cross = json.loads((output / 'cross-club-identities-enriched.json').read_text())
    within = json.loads((output / 'within-club-and-date-triage.json').read_text())
    photos = json.loads((output / 'portrait-coverage.json').read_text())
    rosters = json.loads((roster_store / 'roster-summary.json').read_text())
    for document in (cross, photos):
        by_season = {r['season']:r for r in document['seasons']}
        assert set(by_season) == {r['season'] for r in snapshot['rows']}
        for row in snapshot['rows']:
            assert by_season[row['season']]['release_id'] == row['release_id']
    assert json.loads((roster_store / 'snapshot.json').read_text())['rows'] == snapshot['rows']
    count = lambda check, field: sum(r['checks'][check].get(field, 0) for r in qa)
    issues = [
        {'id':'roster-duplicates', 'priority':1, 'classification':'review-candidates',
         'cross_club_groups':cross['cross_club_candidate_groups'],
         'within_club_groups':within['candidate_group_count'],
         'within_club_policy':within['policy'],
         'literal_DOB_within_club_groups':rosters['totals']['within_club_candidate_groups'],
         'acceptance':'Every candidate has a dated club/squad disposition or documented legitimate exception; no arbitrary deletion.'},
        {'id':'birthdays', 'priority':2, 'classification':'confirmed-recipe-native-disagreement-not-source-verdict',
         'count':count('compiled_birth_dates','failure_count'),
         'acceptance':'Source-supported identity/date, exact native readback, representative in-game age, unrelated bytes unchanged.'},
        {'id':'positions-and-opening-squads', 'priority':3, 'classification':'mixed-unverified-inputs-and-detected-contradictions',
         'native_source_summary':rosters['totals'],
         'inherited_role_declarations':count('compiled_fine_roles','unresolved_role_count'),
         'inherited_broad_role_conflicts':count('compiled_fine_roles','inherited_conflict_count'),
         'english_tactical_fact_warnings':count('tactics_deployment_review','warning_count'),
         'acceptance':'Opening XI and capacity-fitting August squad checked against dated sources; broad/fine/native roles and tactical deployment reconciled.'},
        {'id':'managers', 'priority':4, 'classification':'missing-independent-target-season-proof-not-proven-wrong-name',
         'foreign_club_season_source_gaps':count('manager_sources','provisional_foreign_manager_count'),
         'acceptance':'Dated opening-season manager evidence plus native owner/name readback; carry-forward proven continuities, not wholesale rewriting.'},
        {'id':'ratings', 'priority':5, 'classification':'editorial-review-candidates',
         'suspicious_distribution_club_seasons':count('recipe','distribution_warning_count'),
         'semantic_failures':count('recipe','rating_failure_count'),
         'acceptance':'Versioned position-aware calibration with bounded changes, club strength differentiation and outfield handling guard retained.'},
        {'id':'kits', 'priority':6, 'classification':'two-confirmed-inherited-kit-defects-plus-incomplete-global-visual-coverage',
         'confirmed_targets':['Palermo2005/06','Atalanta2006/07'],
         'format_or_receipt_failures':count('kits','byte_or_format_failure_count'),
         'season_reports_without_visual_approval':sum(r['checks']['kits']['visual_review_missing'] for r in qa),
         'acceptance':'Target-season designs and native palette/format checked at each used size; genuine team-selection and team-rating runner views. Legacy approval-reader gaps distinguished from absent screenshots.'},
        {'id':'secondary-facts-and-nationalities', 'priority':7, 'classification':'optional-gaps-and-accepted-native-capacity-limit',
         'missing_fact_fields':dict(sum((collections.Counter(r['checks']['recipe']['missing_secondary_fact_counts']) for r in qa),collections.Counter())),
         'unsupported_country_occurrences':count('compiled_nationalities','unrepresentable_nationality_count'),
         'acceptance':'Wrong source-backed facts corrected; genuinely unavailable facts and unsupported XXX countries explicitly retained, not blockers.'},
        {'id':'photos', 'priority':8, 'classification':'optional-coverage-gaps-identity-and-era-not-globally-verified',
         'coverage':photos['totals'],
         'acceptance':'Present photos identity/era/crop verified; missing photos explicit and allowed; no blank or wrong-person portrait counted as success.'},
        {'id':'rebuild-and-runtime-regression', 'priority':9, 'classification':'strict-clean-rebuild-blocked-by-roster-candidates-not-a-new-runtime-crash',
         'strict_quality_failed_seasons':sum(r['result']!='pass' for r in qa),
         'runtime_proof_failures':sum(not r['checks']['runtime']['passed'] for r in qa),
         'acceptance':'Repair batches retain known-good bytes, deterministic replay, current bindings and no recurrent cleared issues. Final targeted runner sweep, not repeated all-game generation.'},
    ]
    ledger = {'schema':'pm99-consolidated-discovery-ledger-v1', 'snapshot':snapshot,
        'automated_inventory_complete':True, 'independent_historical_verification_complete':False,
        'counts_are_club_or_player_season_occurrences_not_unique_people':True,
        'issues':issues, 'quality_evidence':evidence,
        'roster_summary':rosters,
        'detailed_roster_evidence_store':str(roster_store),
        'detailed_roster_store_is_volatile_RAM':str(roster_store).startswith('/run/user/'),
        'remaining_discovery':['Adjudicate duplicate and source conflicts; full-season sources cannot alone certify August ownership.',
             'Global historical kit/photo visual identity review remains unperformed; no fresh runner screenshots generated by this audit.',
             'Resolve validator/evidence-reader blind spots separately from game defects.'],
        'delivery_rule':'Freeze this ledger, append dispositions/verified fixes, never reset counts or claim candidate disappearance is historical proof.'}
    discovery.write_new(output / 'issue-ledger.json', ledger)
    discovery.write_new(output / 'roster-summary.json', rosters)
    print(json.dumps({'issue_families':len(issues),'cross_club_candidates':issues[0]['cross_club_groups'],
                     'within_club_candidates':issues[0]['within_club_groups'],
                     'birthdays':issues[1]['count'],'historical_approval':False}))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--roster-store', type=Path, required=True)
    a=p.parse_args();run(a.output,a.roster_store)
