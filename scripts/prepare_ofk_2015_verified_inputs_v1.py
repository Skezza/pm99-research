"""Reparse the fixed18 source allocation plus a positive coupled Celta reserve."""
import copy
from pathlib import Path
import tempfile

from bs4 import BeautifulSoup
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import prepare_ofk_2015_source_allocation_v1 as allocation2015
from scripts import ofk_2004_original_secondary_facts_v1 as secondary
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocate
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_transfer_history_v1 as histories
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_duplicate_ownership_plan_v1 as planner


def prepare(output):
    if output.exists(): raise ValueError('verified2015 source inputs are immutable')
    path=source.AUDIT/'ofk-2015-fixed18-source-feasibility-v1.json'
    proposal=pipeline.read_json_file(path)
    with tempfile.TemporaryDirectory(prefix='pm99-ofk2015-facts-') as temporary:
        if allocation2015.prepare(Path(temporary)/'allocation.json',baseline_release_id=proposal['baseline_release_id'])!=proposal:
            raise ValueError('2015 original fixed18 allocation no longer reproduces')
    result=copy.deepcopy(proposal)
    raw,annual_binding=source.original('ofk-beograd-2015')
    facts=secondary.parse(raw,result['desired_people'],expected_year=2015,
        country_codes={'Serbia':'SRB','North Macedonia':'MKD','Armenia':'ARM'})
    wiki,wiki_binding=source.original('cancarevic-original-nationality-chronology')
    page=BeautifulSoup(wiki,'html.parser')
    paragraphs=[p.get_text(' ',strip=True) for p in page.select('p')]
    if (not any('Serbia national team' in p and '29 January 2017' in p for p in paragraphs)
            or not any('five years of living in Armenia' in p and 'Armenian citizenship' in p and 'June 2023' in p for p in paragraphs)):
        raise ValueError('Cancarevic dated nationality chronology changed')
    fact=facts[85029]
    if fact['nationality']!='ARM': raise ValueError('known later-country annual flag changed; require new review')
    fact.update(nationality='SRB',target_country_basis=wiki_binding,
        country_policy='declared-editorial-chronology-inference: Serbian before later Armenian naturalisation; not a2015 passport record',
        current_primary_annual_flag_used_as_period_fact=False)
    for row in result['desired_people']:
        fact=facts[row['source_person']['source_player_id']]
        row['source_player'].update(nationality=fact['nationality'],height_cm=fact['height_cm'])
        row['secondary_facts_status']=fact
    by_id={r['source_person']['source_player_id']:r for r in result['desired_people']}
    for row in result['allocation']:
        row['replacement']=copy.deepcopy(by_id[row['replacement']['source_person']['source_player_id']])
    review_path=source.AUDIT/'celta-2015-opening-replacement-source-review-v1.json'
    review=pipeline.read_json_file(review_path)
    history_path=source.AUDIT/'celta-2015-madinda-original-history-v1.json'
    events,_=histories.merge({},pipeline.read_json_file(history_path))
    bracket=transfer.transfer_interval(events[21297],'2015-08-01')
    if (bracket!=review['positive_ownership_bracket'] or bracket.get('status')!='recorded-entry-and-exit-bracket-fixture'
            or bracket.get('source_owner_club_id')!=940):
        raise ValueError('Madinda lacks a positive completed opening Celta bracket')
    preseason,preseason_binding=source.original('celta-2015-madinda-preseason-original')
    preseason_text=BeautifulSoup(preseason,'html.parser').get_text(' ',strip=True)
    if ('09-julio-2015' not in preseason_text or 'Los jugadores del primer equipo Nolito y Madinda' not in preseason_text):
        raise ValueError('Madinda original July first-team witness changed')
    international,international_binding=source.original('celta-2014-madinda-national-team-original')
    international_text=BeautifulSoup(international,'html.parser').get_text(' ',strip=True)
    if '11-septiembre-2014' not in international_text or 'Levy Madinda' not in international_text or 'Gabón' not in international_text:
        raise ValueError('Madinda dated national team witness changed')
    person_path=source.AUDIT/'celta-2015-madinda-original-person-v1.json'
    person_document=pipeline.read_json_file(person_path)
    people.merge({},person_document)
    person={k:copy.deepcopy(v) for k,v in person_document['batches'][0]['people'][0].items() if k!='published_name_variants'}
    if person['source_player_id']!=21297: raise ValueError('Celta original biography identifies another person')
    celta_raw,celta_binding=source.original('celta-2015-original-annual')
    extra=dict(source_person=person,source_player=dict(name=person['name'],birth_date=person['birth_date'],position='M',
        nationality='GAB',height_cm=None,weight_kg=None,shirt_number=None),
        membership='positive-original-dated-opening-reserve',
        raw_evidence=dict(status='raw-source-reparsed',local_path=celta_binding['path'],source_sha256=celta_binding['sha256']),
        source_role_basis='original-Celta-target-annual-broad-group',secondary_facts_status='weight unavailable; rounded original annual height')
    extra_fact=secondary.parse(celta_raw,[extra],expected_year=2015,expected_club_name='Celta de Vigo',country_codes={'Gabon':'GAB'})[21297]
    extra['source_player'].update(height_cm=extra_fact['height_cm'])
    extra['secondary_facts_status']=dict(**extra_fact,dated_national_team_witness=international_binding)
    release=registry.load_registered_release('2015-16',proposal['baseline_release_id'])
    package=pipeline.read_json_file(release.package_path)
    before=next(p for p in package['players'] if p['carrier_id']==5468)
    if before!=review['native_slot_to_review']['native_recipe_player']:
        raise ValueError('coupled Celta slot has changed since review')
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    # Keep both fixed capacities, rather than grow a short record or shorten
    # a published surname. Exchange the already-known Drazic carrier with the
    # larger OFK carrier independently allocated to that same sourced person.
    drazic_row=next(r for r in result['allocation'] if r['replacement']['source_person']['source_player_id']==291247)
    moved_slot=next(p for p in package['players'] if p['carrier_id']==drazic_row['carrier_id'])
    fitted=allocate.allocate(jug,[moved_slot],[extra],display.claims(person_path),
        published_families=families.claims(person_path,[21297]))
    ofk_person_path=source.AUDIT/'ofk-2015-original-person-identities-v1.json'
    transferred=allocate.allocate(jug,[before],[drazic_row['replacement']],display.claims(ofk_person_path),
        published_families=families.claims(ofk_person_path,[291247]))
    index,_=identities.load_identity_snapshot();index,_=people.merge(index,person_document)
    collisions=[p['carrier_id'] for _,pack,_ in planner.package_layers(release) for p in pack['players']
        if identities.key(p,index)==('published-person',21297)]
    if collisions: raise ValueError('positive Celta replacement already has a recipe owner')
    report,report_binding=source.original('ofk-first-fixture-2015-2598829')
    match=BeautifulSoup(report,'html.parser')
    if match.select_one('.sb-datum a[href$="/datum/2015-07-19"]') is None:
        raise ValueError('2015 dated coach/ground match changed')
    grounds=match.select('a[href="/stadion/stadion/verein/37/saison_id/2015"]')
    sections=[box for box in match.select('.large-6.columns')
        if box.select_one('.aufstellung-unterueberschrift-mannschaft a.sb-vereinslink[href="/ofk-belgrad/startseite/verein/53/saison_id/2015"]')]
    coaches=[a for box in sections for a in box.select('a[href="/vladimir-petrovic/profil/trainer/5229"]')]
    if len(grounds)!=1 or grounds[0].get_text(' ',strip=True)!='Stadion Milos Obilic' or len(coaches)!=1 or coaches[0].get_text(' ',strip=True)!='Vladimir Petrovic':
        raise ValueError('2015 original dated OFK coach/ground missing or ambiguous')
    result.update(schema_version='pm99-private-original-ofk2015-celta-coupled-inputs-v1',
        secondary_fact_review=dict(policy=secondary.POLICY,facts=[facts[i] for i in sorted(facts)],
            nationality_chronology_override=dict(source_player_id=85029,source=wiki_binding,grade='declared-editorial-inference')),
        coupled_Celta_allocation=fitted,coupled_OFK_transferred_allocation=transferred,
        coupled_native_carrier_exchange=dict(OFK_to_Celta=moved_slot['carrier_id'],Celta_to_OFK=5468,
            fixed_OFK_capacity=18,fixed_Celta_capacity=25,
            policy='explicit-two-roster-carrier-exchange-no-name-growth-or-initial-guess',
            original_Celta_XI_not_historically_approved=True),
        dated_manager_ground=dict(date='2015-07-19',source_club_id=53,
            manager='Vladimir Petrovic',source_manager_id=5229,ground='Stadion Milos Obilic',source_match_id=2598829),
        dated_manager_ground_binding=report_binding,
        coupled_Celta_originals=[preseason_binding,international_binding,celta_binding,
            dict(path=registry.relative_workspace_path(review_path),sha256=registry.sha256_file(review_path))],
        remaining=['Compile/independently readback19 native identities and coupled no-new-duplicate proof.',
            'Three period-reviewed kit sizes; exact complete-game/recipe replay; actual named profiles/fresh startup.'])
    pipeline.write_canonical_json(output,result)
    return result


if __name__=='__main__':
    x=prepare(source.AUDIT/'ofk-2015-celta-verified-source-inputs-v1.json')
    print(dict(fixed_roster=len(x['allocation']),coupled_extra=len(x['coupled_Celta_allocation']),
        native_writes=0,coach=x['dated_manager_ground']),flush=True)
