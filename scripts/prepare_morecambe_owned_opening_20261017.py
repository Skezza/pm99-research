"""Source-bound, same-carrier Morecambe opening repair; never clone its squad.

Prepare an immutable transaction, not a preferred-release switch. Retained
people keep their carriers, names, skills and portraits. Only unpublished
birthdays, conflicting broad/fine roles and complete opening orders change.
Ryan Black's unsourced opening slot becomes the published goalkeeper Mark
Smith. No claim that Black never played for Morecambe is made.
"""
import copy
from datetime import date
from pathlib import Path
from statistics import median

from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_external_soccerbase_birthday_v2 as birthdays
from scripts import season_original_secondary_bench_role_v1 as bench_roles
from scripts import season_original_soccerbase_reserves_v1 as reserves
from scripts import prepare_duplicate_club_disposition_v1 as source
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_rating_calibration_v3 as ratings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_woking_owned_opening_20261011 import skills

ROOT = registry.ROOT/'.local/consolidated-audit-20261009/morecambe2000-source-closure-20261017'
SCHEMA = 'pm99-source-bound-Morecambe2000-fixed-person-opening-assignment-v1'
BASE = 'sourced-original-carrier-label-20261017-r134a'
CENTRAL = {'G': 0, 'D': 4, 'M': 9, 'F': 12}
ROLE_CLASSES = {'G': {0}, 'D': {1,2,3,4,5}, 'M': {6,7,9,10,14}, 'F': {8,11,12,13,15,16}}


def bind(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def decide(package, desired, native, owners):
    """Pure fixed-person decision; missing/contradictory identities refuse."""
    club = next(c for c in package['clubs'] if c['carrier_id'] == 3312)
    current = [p for p in package['players'] if p['club_id'] == club['id']]
    if club['name'] != 'Morecambe' or {p['carrier_id'] for p in current} != set(range(10986,11004)):
        raise ValueError('requires restored original Morecambe and exactly eighteen existing carriers')
    if len(desired) != 18 or len({p['source_person']['source_player_id'] for p in desired}) != 18:
        raise ValueError('requires eighteen distinct positive opening identities')
    if [p['membership'] for p in desired[:11]] != ['starting_xi']*11 or any(
            p['membership'] == 'starting_xi' for p in desired[11:]):
        raise ValueError('requires complete ordered original eleven, not a reserve approximation')
    if desired[0]['source_player']['position'] != 'G' or sum(
            p['source_player']['position']=='G' for p in desired[:11]) != 1:
        raise ValueError('published opening keeper must be first and unique')
    names = {}
    for p in current:
        key = roster.normalise(p.get('source_name') or p['name'])
        if key in names:
            raise ValueError('ambiguous existing same-name Morecambe people')
        names[key] = p
    rows = []
    for order, wanted in enumerate(desired, 1):
        facts = wanted['source_player']; key = roster.normalise(facts['name'])
        if not isinstance(facts['birth_date'], str) or facts['position'] not in CENTRAL:
            raise ValueError('unresolved opening birthday or broad position')
        existing = names.get(key)
        changed_person = existing is None
        if changed_person:
            if (facts['name'], facts['birth_date'], facts['position'], order) != ('Mark Smith','1973-01-02','G',1):
                raise ValueError('only sourced missing opening Mark Smith may replace an identity')
            existing = next(p for p in current if p['carrier_id'] == 11002)
            if roster.normalise(existing.get('source_name') or existing['name']) != 'ryanblack':
                raise ValueError('the explicitly reviewed unsourced reserve slot changed')
        else:
            before = existing['facts']['birth_date']
            if isinstance(before, str) and before != facts['birth_date']:
                raise ValueError('positive opening source conflicts with a known resident birthday')
        carrier = existing['carrier_id']; actual = native[carrier]
        if owners.get(carrier) != {3312} or roster.normalise(actual['name']) != roster.normalise(existing['name']):
            raise ValueError('resident native name or exclusive club ownership differs')
        outside = [p for p in package['players'] if p['club_id'] != club['id'] and
            roster.normalise(p.get('source_name') or p['name']) == key and
            (not isinstance(p['facts'].get('birth_date'),str) or p['facts']['birth_date'] == facts['birth_date'])]
        if outside:
            raise ValueError('another club already represents this opening person; paired repair required')
        broad = facts['position']
        # Retain a compatible native specialist; otherwise make the fallback
        # explicitly editorial and central, never a claimed exact match role.
        fine = actual['roles'][:]
        if changed_person or fine[0] not in ROLE_CLASSES[broad]:
            fine = [CENTRAL[broad]]
        else:
            fine = [r for r in fine if r != 98]
        rows.append(dict(carrier_id=carrier, player_id=existing['id'], before=existing,
            replacement=wanted, opening_order=order, identity_changed=changed_person,
            birth_date=facts['birth_date'], primary_position=broad, fine_roles=fine,
            fine_role_basis=('explicit-editorial-central-fallback-for-source-broad-role'
                if changed_person or actual['roles'][0] not in ROLE_CLASSES[broad]
                else 'retained-compatible-native-fine-role-not-independent-specialism-proof')))
    if {r['carrier_id'] for r in rows} != set(range(10986,11004)):
        raise ValueError('opening assignment must use every existing carrier exactly once')
    return rows


def prepare(base):
    if base.season != '2000-01' or base.release_id != BASE:
        raise ValueError('Morecambe proposal requires exact restored-label parent')
    package = pipeline.read_json_file(base.package_path)
    doc = pipeline.read_json_file(ROOT/'original-opening-equivalence.json')
    actual = replay.replay_club(base.season, doc['selected_capture'], {}, True, allow_missing_birth_date=True)
    if actual != doc['actual']:
        raise ValueError('original Morecambe opening fixture/biographies no longer reproduce')
    review = pipeline.read_json_file(ROOT/'provider-identity-and-bench-role-review-v2.json')
    desired = source.matchday_people(actual, dict(players=[]),
        identity_resolutions={r['source_provider_person_id']:r for r in review['resolutions']},
        role_resolutions={r['source_provider_person_id']:r for r in review['bench_role_resolutions']})
    pool = pipeline.read_json_file(ROOT/'positive-capacity18-original-squad.json')
    if pool['desired_people'][:16] != desired:
        raise ValueError('complete opening sixteen differs from independently replayed source admission')
    for person in pool['desired_people'][16:]:
        desired.append(reserves.verify_reserve(person, actual))
    if [p['source_player']['name'] for p in desired[16:]] != ['Jamie Murphy','Garry Thompson']:
        raise ValueError('positive opening capacity reserves changed')
    source.validate_opening_birth_dates(desired,actual['fixture']['date'])
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    native={e.record_id:roster.native_player(e.decode_payload(jug),e.record_id)
        for e in IndexedFDIFile.from_bytes(jug).entries if 10986 <= e.record_id <= 11003}
    rows=decide(package,desired,native,ownership.native_owners(eq))
    for row in rows:
        if skills(jug,row['carrier_id']) != row['before']['ratings']['values']:
            raise ValueError('existing resident native ten skills already differ from recipe')
    # Only the genuinely new keeper receives generated skills. Preserve all
    # seventeen existing people, including those whose missing DOB is filled.
    keeper=next(r for r in rows if r['identity_changed'])
    strength=round(median(r['before']['ratings']['values']['quality'] for r in rows))
    player=dict(keeper['before'],name='Mark Smith',source_name='Mark Smith',
        facts=dict(keeper['before']['facts'],birth_date=keeper['birth_date'],primary_position='G'))
    keeper['new_person_ratings']=ratings.editorial(player,strength,'starting_xi',date(2000,8,1))
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'),rows=rows,
        original_fixture=actual['fixture'],original_sources=actual['raw_sources'],
        input_bindings=[bind(ROOT/name) for name in ('original-opening-equivalence.json',
            'provider-identity-and-bench-role-review-v2.json','positive-capacity18-original-squad.json')],
        implementation_inputs=[bind(Path(m.__file__)) for m in (source,replay,birthdays,bench_roles,reserves,ratings)] + [bind(Path(__file__))],
        opening_eleven=11,source_bench=5,positive_dated_reserves=2,
        identity_changes=1,retained_people_with_all_ten_native_skills_preserved=17,
        correct_known_birthdays_overwritten=0,portrait_clear_carriers=[11002],
        scope='Exact existing Morecambe3312 cohort. Original XI/bench plus two dated reserves; one new keeper, three missing birthdays, source-broad/compatible fine-role reconciliation, startup/EQ order. Preserve seventeen identities/carriers/names/ratings/portraits, manager/ground/kits/opaque tactics and all other clubs. Native delivery and runtime approval still required.')


if __name__ == '__main__':
    output=ROOT/'same-carrier-opening-assignment-v2.json'
    if output.exists():
        raise ValueError('existing Morecambe assignment must be inspected, not overwritten')
    base=registry.load_registered_release('2000-01',BASE)
    plan=prepare(base);retained(output,plan)
    print(dict(sourced_people=18,retained_native_people=17,missing_starting_keeper_to_add=1,
        same_carrier_assignment_complete=True,native_writes=0,preferred_changed=False),flush=True)
