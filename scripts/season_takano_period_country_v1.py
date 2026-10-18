"""One-byte country correction; retain the explicitly disputed adopted DOB."""
import copy
from datetime import date
import hashlib
from pathlib import Path
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from scripts import adjudicate_takano_period_identity_20261017 as evidence
from scripts import season_original_country_policy_v2 as countries

pipeline,registry,packages=countries.pipeline,countries.registry,countries.packages
SCHEMA='pm99-Takano-original-1997-country-event-and-explicit-DOB-conflict-v1'
PREFIX='sourced-takano-period-country-'
MODE='known-good-baseline-original-Takano-Japan-country-only-v1'
FILENAME='sourced-takano-period-country.json'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return FILENAME


def prepare(base):
    if base.season!='2000-01':raise ValueError('this actor admission only covers the sourced2000 opening person')
    source=evidence.source
    choice_path=source.ROOT/'takano-country-and-birthday-source-choice-v1.json'
    choice=pipeline.read_json_file(choice_path)
    raw,article=evidence.original('takano-original-independent-2006-nationality')
    raw_legacy,legacy=evidence.original('takano-official-southport-legacy-row-validated')
    if (article['url']!='https://www.the-independent.com/sport/football/news/fa-cup-countdown-maradona-of-basingstoke-423354.html'
            or legacy['url']!='https://southportfc.net/player-list/'
            or evidence.parse_news(raw)!=choice['nationality'] or article!=choice['nationality_original']
            or evidence.parse_legacy(raw_legacy)!=choice['legacy_birthday'] or legacy!=choice['legacy_original']
            or choice['adopted_birth_date']!='1976-09-30'):
        raise ValueError('original Japanese event or disclosed birthday conflict no longer reproduces')
    opening=pipeline.read_json_file(source.ROOT/'original-opening-equivalence.json')['actual']
    reviews=pipeline.read_json_file(source.ROOT/'provider-identity-and-bench-role-review-v2.json')
    review=next(r for r in reviews['resolutions'] if r['name']=='Kenny Takano')
    actor=next(r['soccerbase_person'] for group in opening['identity_bridges'].values() for r in group
        if r['soccerbase_person']['source_player_id']==review['source_provider_person_id'])
    if source.birthdays.resolve(review,actor,opening)!=choice['official_identity_resolution']:
        raise ValueError('exact original numeric actor/official nickname/DOB bridge differs')
    package=pipeline.read_json_file(base.package_path)
    matches=[p for p in package['players'] if p['carrier_id']==10992]
    if len(matches)!=1:raise ValueError('one actual Takano carrier required')
    player=matches[0];club=next(c for c in package['clubs'] if c['id']==player['club_id'])
    if (source.roster.normalise(player.get('source_name') or player['name'])!='kennytakano'
            or player['facts']['birth_date']!='1976-09-30' or club['carrier_id']!=3312 or club['name']!='Morecambe'):
        raise ValueError('country actor is not the exact adopted source-bound Morecambe person')
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    entry=next(e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id==10992)
    payload=entry.decode_payload(jug);native=source.roster.native_player(payload,10992);end=native['name_end']
    birth=date(int.from_bytes(bytes(v^0x61 for v in payload[end+14:end+16]),'little'),payload[end+13]^0x61,payload[end+12]^0x61).isoformat()
    codes=countries.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    code,label=countries.native_country('JPN',codes)
    if (source.roster.normalise(native['name'])!=source.roster.normalise(player['name'])
            or birth!=player['facts']['birth_date'] or source.ownership.native_owners(eq).get(10992)!={3312}
            or payload[end+8]^0x61!=codes['ENGLAND']):
        raise ValueError('actual Takano name/birthday/exclusive owner/inherited England preimage differs')
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=digest(jug),eq_sha256=digest(eq),
        before_player=player,nationality='JPN',native_country_code=code,native_label=label,
        source_choice=source.bind(choice_path),original_actor=actor,identity_resolution=review,
        original_article=article,original_legacy_conflict=legacy,
        implementation_inputs=[source.bind(Path(m.__file__)) for m in (evidence,source.birthdays,countries)]+[source.bind(Path(__file__))],
        birth_date_unchanged_and_explicitly_disputed=True,
        scope='Only Takano10992 country byte and matching recipe nationality/fallback/provenance. Detailed1976 date retained with aggregate1978 conflict explicitly logged; all birthdays, names, skills, roles, startup, roster, other players, managers, kits, portraits and EXE unchanged.')


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:raise ValueError('Takano original country source/native decision differs')


def bind(package,plan):
    if digest(packages.canonical_json_bytes(package))!=plan['package_sha256']:raise ValueError('Takano country recipe preimage differs')
    result=copy.deepcopy(package);p=next(p for p in result['players'] if p['carrier_id']==10992)
    if p!=plan['before_player']:raise ValueError('Takano country actor preimage differs')
    p['facts']['nationality']='JPN'
    p['fact_fallbacks']=[f for f in p.get('fact_fallbacks',[]) if f['field']!='nationality']
    result['artifacts'].append(dict(id=PREFIX+plan['season'],kind='season-input',relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if digest(before)!=plan['jug_sha256'] or digest(eq)!=plan['eq_sha256']:raise ValueError('Takano whole native preimage differs')
    after,_=rewrite_indexed_native_nationalities(before,{10992:plan['native_country_code']})
    if jug not in (before,after):raise ValueError('Takano input neither complete preimage nor postimage')
    if len(before)!=len(after) or sum(a!=b for a,b in zip(before,after))!=1:
        raise ValueError('Takano country delta must be exactly one actual native byte')
    return after,eq


def reconstruction(previous,release_id):
    receipt_path=getattr(previous,'compiler_receipt_path',None)
    if receipt_path is None or pipeline.read_json_file(receipt_path).get('compilation_mode')!=MODE:return None
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path)
    artifact=next(a for a in package['artifacts'] if a['id']==PREFIX+previous.season)
    if (path.resolve()!=(previous.package_path.parent/FILENAME).resolve() or registry.sha256_file(path)!=artifact['sha256']
            or bind(pipeline.read_json_file(base.package_path),plan)!=package):raise ValueError('edited Takano country recipe cannot be silently reconstructed')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('Takano country SOURCE descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():raise ValueError('Takano full SOURCE recipe differs')
    return dict(season=previous.season,complete_game_inventory_identical=True,complete_recipe_identical=True,compilation_mode=MODE)
