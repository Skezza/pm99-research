"""Retire a factory fallback superseded by a positive dated squad identity.

This is an explicit source-priority resolution, not a DOB-based merge and not
proof that a game's original inaccurate biography constitutes a second person.
Only an untouched whole-record fallback and one unique independently published
numeric target-season person qualify. Both source/name ambiguity and any edited
fallback fail closed. The complete dated XI is repaired separately before release.
"""
import hashlib
from datetime import date

from app.fdi_indexed import IndexedFDIFile
from scripts import review_profile_addition_duplicate_assignments_v1 as source
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

SCHEMA = 'pm99-original-positive-squad-person-supersedes-pinned-factory-fallthrough-review-v1'
FACTORY_JUG_SHA256 = '95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844'


def payload(raw, carrier):
    entries = [e for e in IndexedFDIFile.from_bytes(raw).entries if e.record_id == carrier]
    if len(entries) != 1:
        raise ValueError('ambiguous factory/native carrier')
    return entries[0].decode_payload(raw)


def shared_fallback_membership(package, eq, person, target):
    """Describe removal of one link, never deletion of a shared global person."""
    owners = source.ownership.native_owners(eq).get(person['carrier_id'], set())
    declared = [c for c in package['clubs'] if person['id'] in c['roster_player_ids']]
    if (person.get('policy') != 'preserve-existing-mode1'
            or {c['carrier_id'] for c in declared} != owners or target not in owners
            or len(owners) != 2):
        raise ValueError('shared retirement requires exact two-owner whole-record fallback')
    for club in declared:
        _, _, rows = source.native.roster_rows(eq, club['carrier_id'])
        if rows.count((person['carrier_id'], 0)) != 1:
            raise ValueError('shared native roster link is hidden or repeated')
        if (person['club_id'] != club['id']
                and person['id'] not in club.get('shared_preserve_player_ids', [])):
            raise ValueError('shared recipe owner declaration differs')
    survivor = next(c for c in declared if c['carrier_id'] != target)
    return dict(player=person, native_owners_before=sorted(owners),
                surviving_club_id=survivor['id'], surviving_club_before=survivor,
                scope='Remove target roster link only; preserve global player, assets and surviving native club. Structural owner rebind is NOT historical approval of surviving fallback membership.')


def shared_other_club_retirements(release, package, club, cap, root, lineup,
                                 witness, jug, eq, factory, profile_root, receipt):
    """One explicit published-name alias, not a fuzzy cross-club deletion rule.

    Dabo's untouched factory spelling omits the final e. His literal birthday,
    numeric opening bench identity and reparsed Atalanta annual row must all
    agree. This narrow original-date witness is one day before Venezia's opener.
    """
    owners = source.ownership.native_owners(eq)
    _, _, rows = source.native.roster_rows(eq, club['carrier_id'])
    people = {p['carrier_id']: p for p in package['players']}
    result = []
    for carrier, flag in rows:
        if len(owners.get(carrier, set())) <= 1 or carrier == 4092:
            continue
        person = people[carrier]
        actual = source.facts.native_facts(jug, carrier)
        if (release.season != '2001-02' or club['carrier_id'] != 221
                or carrier != 19511 or person['name'] != 'Ousman DABO'
                or actual['birth_date'] != '1977-02-08'
                or payload(jug, carrier) != payload(factory, carrier)):
            raise ValueError('unreviewed shared reserve cannot be retired')
        membership = shared_fallback_membership(package, eq, person, club['carrier_id'])
        other = membership['surviving_club_before']
        if other['carrier_id'] != 213 or other['name'] != 'Atalanta':
            raise ValueError('Dabo surviving club identity differs')
        pre = pipeline.read_json_file(root / 'opening-squad-preallocation.json')
        other_cap, other_annual = source.bound_annual_capture(release, other, pre, root)
        annual_people = [p for p in other_cap['players']
                         if p['name'] == 'Ousmane Dabo' and p['birth_date'] == '1977-02-08']
        if len(annual_people) != 1 or any(source.identity.key(p['name']).endswith('dabo')
                                         for p in cap['players']):
            raise ValueError('Dabo positive other annual identity/target annual contradiction differs')
        matches = [c for c in lineup['clubs'] if all(c['source_selector'][k] == other_cap[k]
                   for k in ('club_name', 'country_catalog', 'competition_catalog'))]
        if len(matches) != 1:
            raise ValueError('Dabo other original fixture ambiguous')
        other_witness = source.opening.verify_opening(matches[0], lineup, root / 'cache')
        if ((date.fromisoformat(witness['date']) - date.fromisoformat(other_witness['date'])).days != 1
                or other_witness['substitutes'].get('3904') != 'Ousmane Dabo'):
            raise ValueError('Dabo original other bench/opening-day interval differs')
        url = 'https://www.transfermarkt.co.uk/ousmane-dabo/profil/spieler/3904'
        raw, proof = source.opening.verified_page(profile_root, receipt['cache_files'], url)
        profile = source._profile_facts(raw, player={'source_player_id': '3904'})
        if (profile['published_full_name'] != 'Ousmane Dabo'
                or profile['published_birth_date'] != actual['birth_date']
                or profile['published_profile_position'] != 'Defensive Midfield'
                or actual['position'] != 'M'):
            raise ValueError('Dabo original numeric full profile differs')
        result.append(dict(membership, original_annual_source=other_annual,
            original_annual_player=annual_people[0], original_other_fixture=other_witness,
            original_profile=proof, profile=profile,
            published_name_alias={'native': 'Ousman DABO', 'published': 'Ousmane Dabo'},
            source_grade='positive-other-opening-bench-and-annual-plus-exact-birthday-factory-alias; target annual exclusion corroborates, never sole authority'))
    return result


def prepare(release, case, profile_root, profile_receipt):
    if case['season'] != release.season:
        raise ValueError('fallthrough case season differs')
    package = pipeline.read_json_file(release.package_path)
    club = next(c for c in package['clubs'] if c['id'] == case['club_id'])
    people = [p for p in package['players'] if p['carrier_id'] in {x['carrier_id'] for x in case['players']}]
    fallback = [p for p in people if p.get('policy') == 'preserve-existing-mode1']
    authored = [p for p in people if p.get('policy') != 'preserve-existing-mode1']
    if (len(people) != 2 or len(fallback) != 1 or len(authored) != 1
            or any(p['club_id'] != club['id'] for p in people)):
        raise ValueError('one exclusive whole-record fallback plus one target person required')
    bad, keep = fallback[0], authored[0]
    if (bad['proof'] != {'artifact_id':'world-mode1-runtime-contract','grade':'static-contract'}
            or bad['person_id'] != 'person-' + str(bad['carrier_id'])
            or any(v != {'policy':'preserve-existing-mode1'} for v in bad['facts'].values())):
        raise ValueError('fallback is not the unqualified original whole-record declaration')
    root = registry.ROOT / '.local/transfermarkt-opening-plans-current-v1' / release.season
    pre_path = root / 'opening-squad-preallocation.json'
    if [a['sha256'] for a in package['artifacts'] if a['id']=='opening-squad-preallocation-'+release.season] != [registry.sha256_file(pre_path)]:
        raise ValueError('fallthrough target allocation source changed')
    pre = pipeline.read_json_file(pre_path)
    cap, annual = source.bound_annual_capture(release, club, pre, root)
    name = source.identity.key(keep.get('source_name') or keep['name'])
    if source.identity.key(bad['name']) != name:
        raise ValueError('fallback complete native given/family name differs')
    annual_people = [p for p in cap['players'] if source.identity.key(p['name']) == name]
    if len(annual_people) != 1 or annual_people[0]['birth_date'] != keep['facts']['birth_date']:
        raise ValueError('dated annual roster has no unique same full-name/literal-DOB target identity')
    projected = [c for c in pre['source_clubs'] if all(c['selector'][k]==cap[k]
        for k in ('club_name','country_catalog','competition_catalog'))]
    if len(projected) != 1:
        raise ValueError('fallthrough target projection ambiguous')
    assigned = [p for p in projected[0]['players'] if 'person-source-'+p['source_row_sha256']==keep['person_id']]
    if len(assigned) != 1 or assigned[0]['facts'] != annual_people[0]:
        raise ValueError('target person is not the exact original annual allocation')
    lineup_path = root / 'opening-lineups.json'; lineup=pipeline.read_json_file(lineup_path)
    matches = [c for c in lineup['clubs'] if all(c['source_selector'][k]==cap[k]
        for k in ('club_name','country_catalog','competition_catalog'))]
    if len(matches)!=1:
        raise ValueError('fallthrough original first fixture ambiguous')
    witness=source.opening.verify_opening(matches[0],lineup,root/'cache')
    if not projected[0]['opening_xi_complete'] or projected[0]['opening_fixture_date']!=witness['date']:
        raise ValueError('complete same dated original XI required')
    raw_match,_=source.opening.verified_page(root/'cache',lineup['source']['cache_files'],witness['source_url'])
    members={**witness['starting_xi'],**witness['substitutes']}
    candidates=[p for p in matches[0]['starting_xi']+matches[0]['substitutes']
                if source.identity.key(p['source_slug'])==name]
    if len(candidates)!=1 or candidates[0]['source_player_id'] not in members:
        raise ValueError('full-name target must be positively present on dated first match sheet')
    person=candidates[0];id=person['source_player_id']
    url='https://www.transfermarkt.co.uk/'+person['source_slug']+'/profil/spieler/'+id
    receipt=pipeline.read_json_file(profile_receipt)
    raw,proof=source.opening.verified_page(profile_root,receipt['cache_files'],url)
    profile=source._profile_facts(raw,player={'source_player_id':id})
    if (source.identity.key(profile['published_full_name'])!=name
            or profile['published_birth_date']!=keep['facts']['birth_date']):
        raise ValueError('original numeric profile does not confirm target full identity')
    annual_path=registry.ROOT/annual['local_path']
    if annual['local_path'].startswith('.local/external-sources/cache.footballsquads/') and cap['source_path'].endswith('.txt'):
        # FootballSquads has no numeric player IDs. The independently reparsed
        # unique complete name AND literal DOB must agree with the numeric
        # original first-match/profile identity; do not invent an annual ID.
        numeric=dict(policy='original-FootballSquads-unique-full-name-literal-DOB-plus-independent-numeric-first-match-profile',
            annual_player=annual_people[0], numeric_first_match_player_id=id,
            original_annual=annual, annual_numeric_id_claimed=False)
    else:
        numeric=source.annual_numeric_identity(annual_path.read_bytes(),profile['published_full_name'],id)
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    factory_path=registry.ROOT/'.local/season-pipeline-v2/pm99-base-clean/DBDAT/JUG98030.FDI'
    factory=factory_path.read_bytes()
    if hashlib.sha256(factory).hexdigest()!=FACTORY_JUG_SHA256:
        raise ValueError('independently pinned factory player database differs')
    if payload(jug,bad['carrier_id'])!=payload(factory,bad['carrier_id']):
        raise ValueError('fallback payload was edited or is not the original factory input')
    owners=source.ownership.native_owners(eq);_,_,rows=source.native.roster_rows(eq,club['carrier_id'])
    before={str(p['carrier_id']):source.facts.native_facts(jug,p['carrier_id']) for p in people}
    if (before[str(keep['carrier_id'])]['birth_date']!=profile['published_birth_date']
            or owners.get(keep['carrier_id'])!={club['carrier_id']}
            or any(rows.count((p['carrier_id'],0))!=1 for p in people)):
        raise ValueError('exclusive target native identity/ownership differs')
    shared_removed = (shared_fallback_membership(package, eq, bad, club['carrier_id'])
                      if owners.get(bad['carrier_id']) != {club['carrier_id']} else None)
    extra = shared_other_club_retirements(release, package, club, cap, root, lineup,
        witness, jug, eq, factory, profile_root, receipt)
    result = dict(schema=SCHEMA,case_id=case['id'],season=release.season,release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),jug_sha256=hashlib.sha256(jug).hexdigest(),
        eq_sha256=hashlib.sha256(eq).hexdigest(),club_id=club['id'],club_carrier_id=club['carrier_id'],
        source_bindings=[source.binding(pre_path),source.binding(lineup_path),source.binding(profile_receipt),source.binding(factory_path)],
        original_annual_source=annual,original_profile=proof,original_annual_numeric_identity=numeric,
        first_fixture=witness,retained_source_player_id=id,
        retained_positive_fixture_surface='starting-XI' if id in witness['starting_xi'] else 'published-bench',
        retained_player=keep,removed_player=bad,native_before=before,native_roster_before=[list(x) for x in rows],
        duplicate_input_assignment_proved=True,removed_is_current_native_starter=before[str(bad['carrier_id'])]['startup_order']<=11,
        review_grade='explicit-source-priority-over-unqualified-factory-fallback',native_writes=0,
        scope='Retire only the untouched, unsourced same-full-name factory fallthrough in favour of the unique original numeric target-season annual and first-match person. Not a same-DOB merge or full historical approval of remaining fallback reserves.')
    if shared_removed is not None:
        result['shared_removed_membership'] = shared_removed
    if extra:
        result['additional_shared_membership_retirements'] = extra
    return result
