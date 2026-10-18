"""Distinguish the current Kata from Hein; no historical owner/fact update."""
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_published_person_identity_v1 as people
from scripts import season_historical_transfer_review_v1 as identities
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.capture_source_bound_people_v1 import capture_ids
from scripts.arsenal_2021_opening_transaction_source_v1 import arsenal,bound
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    base=registry.load_registered_release('2021-22','sourced-year-bound-managers-20261016-r110a')
    package=pipeline.read_json_file(base.package_path)
    player=next(p for p in package['players'] if p['carrier_id']==19780)
    jug=base.game_path/'DBDAT/JUG98030.FDI'
    native=facts.native_facts(jug.read_bytes(),19780)
    if (roster.normalise(player.get('source_name') or player['name']),native['birth_date'])!=('mihalykata','2002-04-13'):
        raise ValueError('literal current birthday neighbour changed')
    query=arsenal.ROOT/'kata-identity-query-input.json'
    retained(query,dict(purpose='Identity exclusion only; no opening-owner, present club or secondary-fact claim',
        candidate_discovery='Canonical public profile search; untrusted until original API name and DOB match',
        candidate_profile_url='https://www.transfermarkt.co.uk/mihaly-kata/profil/spieler/543774',
        candidate_profile_id=543774,source_release=base.release_id,carrier_id=19780,
        source_name=player['source_name'],native=native,
        native_JUG_sha256=registry.sha256_file(jug),package_sha256=registry.sha256_file(base.package_path)))
    output=arsenal.ROOT/'kata-original-person-identity.json'
    if output.exists():document=pipeline.read_json_file(output)
    else:document=capture_ids([543774],arsenal.ROOT/'identity-exclusion-cache',output,[bound(query)])
    parsed,_=people.merge({},document)
    person=identities.unique_person(player,parsed)
    if person is None or person['source_player_id']!=543774 or person['birth_date']!=native['birth_date']:
        raise ValueError('original source does not positively identify the existing Kata')
    retained(arsenal.ROOT/'kata-identity-exclusion-proof.json',dict(carrier_id=19780,
        native_birth_date=native['birth_date'],person=person,original_identity=bound(output),
        query=bound(query),distinct_from_Hein_source_id=493513,native_writes=0))
    print(dict(identified_native_carrier=19780,original_person=543774,distinct_from_Hein=True,native_writes=0),flush=True)


if __name__=='__main__':main()
