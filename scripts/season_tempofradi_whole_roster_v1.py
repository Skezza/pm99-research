"""Source-bound Tempó Fradi opening roster using existing native writers."""
from datetime import date
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_order_repair_v1 as ordering
from scripts import season_package_v2 as packages
from scripts import season_release_registry_v1 as registry
from scripts import season_complete_mode1_opening_v1 as complete
from scripts import season_same_carrier_name_capacity_v1 as name_capacity

SCHEMA = 'pm99re.hajnal-ftc-whole-roster-admission.v3'
POLICY = 'tempofradi-dated-first-fixtures-fixed-capacity-editorial-formation-v3'
ID_POLICY = 'tempofradi-profile-plus-dated-match-archive-identity-v1'
ROOT = Path('.local/consolidated-audit-20261009/parallel-rc-20261023/reconcile')
COHORT = ROOT / 'hajnal-ftc-opening-cohort-inputs-v1.json'
NATIONALITY = ROOT / 'hajnal-ftc-fixed21-allocation-nationality-review-v3.json'
CLUB = 1701
GERA = 30027
SCHALKE_HAJNAL = 14706
ROLE = {
    'goalkeeper': ('G', 0, 'kapus'),
    'defender': ('D', 4, 'hátvéd'),
    'midfielder': ('M', 9, 'középpályás'),
    'forward': ('F', 12, 'csatár'),
}
COUNTRIES = {'Hungary': 'HUN', 'Romania': 'ROU', 'Serbia': 'SRB', 'Slovakia': 'SVK'}
LABELS = {
    'Vámos János':'Vámos', 'Cheregi Marius':'Cheregi', 'Dragóner Attila':'Dragóner',
    'Szűcs Mihály':'Szűcs M.', 'Halgas Tibor':'Halgas', 'Lipcsei Péter':'Lipcsei',
    'Csiszár Ákos':'Csiszár Á.', 'Vén Gábor':'Vén', 'Gera Zoltán':'Gera',
    'Horváth Péter':'Horváth P.', 'Rob Kornél':'Rob', 'Kardos Ernő':'Kardos',
    'Földvári Csaba':'Földvári', 'Gajda István':'Gajda', 'Tóth Mihály':'Tóth M.',
    'Lakos Pál':'Lakos', 'Csoknay Norbert':'Csoknay', 'Németh Gábor':'Németh G.',
    'Kriston Attila':'Kriston', 'Balog Zoltán':'Balog Z.', 'Gyepes Gábor':'Gyepes',
}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def bind_source(path, digest):
    p = registry.ROOT / path
    registry.relative_workspace_path(p)
    raw = p.read_bytes()
    if sha(raw) != digest:
        raise ValueError('retained FTC source hash differs: ' + str(path))
    return p, raw

def visible(raw):
    return ' '.join(BeautifulSoup(raw, 'html.parser').get_text(' ', strip=True).split())

def person_key(person):
    if (person.get('source_provider') not in ('tempofradi','hlsz')
            or person.get('identity_policy') != ID_POLICY
            or not person.get('source_profile_sha256')
            or not person.get('name') or not person.get('birth_date')):
        raise ValueError('Tempó identity needs exact provider policy, profile hash, name and DOB')
    url = person.get('source_profile_url', '')
    parsed = urlsplit(url)
    key = person.get('source_player_id', '')
    if person['source_provider']=='tempofradi':
        valid = (parsed.scheme=='https' and parsed.netloc=='tempofradi.hu'
            and parsed.path=='/'+key.removeprefix('tempofradi:')
            and re.fullmatch(r'tempofradi:[a-z0-9-]+',key))
    else:
        valid = (parsed.scheme=='https' and parsed.netloc=='hlsz.wsg.hu'
            and key=='hlsz:'+hashlib.sha256(url.encode()).hexdigest()[:24])
    if not valid:
        raise ValueError('local identity key does not match exact source profile URL')
    return 'person-tempofradi-' + hashlib.sha256(
        (url + '|' + person['birth_date']).encode()).hexdigest()[:24]

def _claims(report):
    result = {}
    review = report['nationality_review']
    for name, row in {**review['carried_forward_from_v1'], **review['newly_covered']}.items():
        kind = row['kind']
        if kind == 'explicit_nationality':
            country = row['country']
        elif kind == 'national_team_representation':
            country = 'Hungary'
        elif kind == 'wikipedia_fifa_nation_team_designation':
            country = {'HUN':'Hungary', 'SVK':'Slovakia'}.get(row['designation'])
        else:
            raise ValueError('unknown country evidence kind for ' + name)
        if country not in COUNTRIES:
            raise ValueError('missing explicit game-country decision for ' + name)
        result[name] = (COUNTRIES[country], row)
    return result

def _verify_country(name, code, row):
    if row['kind'] == 'wikipedia_fifa_nation_team_designation':
        s = row['source']
        _, raw = bind_source(s['capture_path'], s['sha256'])
        soup = BeautifulSoup(raw, 'html.parser')
        def words(value):
            folded = unicodedata.normalize('NFKD', value.casefold())
            folded = ''.join(c for c in folded if not unicodedata.combining(c))
            return set(re.sub(r'[^a-z0-9]+', ' ', folded).split())
        tokens = words(name)
        matches = []
        for tr in soup.find_all('tr'):
            text = ' '.join(tr.get_text(' ', strip=True).split())
            row_words = words(text)
            if tokens <= row_words and code.casefold() in row_words:
                matches.append(text)
        if not matches:
            raise ValueError('Wikipedia Nation code does not uniquely bind ' + name)
    elif row['kind'] == 'explicit_nationality':
        ev = row['evidence'][0]
        _, raw = bind_source((ROOT / ev['path']).as_posix(), ev['sha256'])
        text = visible(raw).casefold()
        anchor = {'Romania':'nemzetisége: román', 'Serbia':'nemzetisége: szerb'}[row['country']]
        if anchor not in text:
            raise ValueError('Tempó profile nationality anchor differs for ' + name)
    elif not any('mlsz.hu' in e.get('url', '') for e in row.get('evidence', [])):
        raise ValueError('prior national-team claim lacks MLSZ provenance for ' + name)

def _profile(person, role):
    s = person['profile_source']
    path = (ROOT / s['path']).as_posix()
    _, raw = bind_source(path, s['sha256'])
    soup = BeautifulSoup(raw, 'html.parser')
    text = visible(raw)
    if urlsplit(s['url']).netloc == 'hlsz.wsg.hu':
        if person['full_name'].casefold() not in text.casefold():
            raise ValueError('HLSZ identity name is absent: ' + person['full_name'])
        tokens = person['full_name'].split()
        given, family = ' '.join(tokens[1:]), tokens[0]
        dob = date.fromisoformat(person['dob']).isoformat()
        if dob not in text:
            raise ValueError('HLSZ exact DOB is absent: ' + person['full_name'])
        if 'Poszt Csatár' not in text:
            raise ValueError('HLSZ attacker position evidence absent for Rob Kornél')
        return path, raw, person['full_name'], given, family
    title = soup.title.get_text(' ', strip=True).split('|')[0].strip() if soup.title else ''
    tokens = title.split()
    source_tokens = person['full_name'].split()
    if len(tokens) < 2 or sorted(t.casefold() for t in tokens) != sorted(t.casefold() for t in source_tokens):
        raise ValueError('profile title does not bind full name: ' + person['full_name'])
    if title.casefold() == person['full_name'].casefold():
        given, family = ' '.join(tokens[1:]), tokens[0]
    elif title.casefold() == ' '.join(reversed(source_tokens)).casefold():
        given, family = tokens[0], ' '.join(tokens[1:])
    else:
        raise ValueError('unsupported source name order: ' + title)
    dob = date.fromisoformat(person['dob']).strftime('%Y.%m.%d')
    pattern = r'(?<!\d)' + re.escape(dob[:4]) + r'\.\s*' + re.escape(dob[5:7]) + r'\.\s*' + re.escape(dob[8:]) + r'\.'
    if not re.search(pattern, text):
        raise ValueError('exact DOB absent from source profile: ' + person['full_name'])
    role_text = re.search(r'Posztja:\s*(.*?)(?:\s+(?:Mezszáma|Magassága|Súlya|Nemzetisége|Érkezett):|$)', text, re.I)
    if not role_text or ROLE[role][2].casefold() not in role_text.group(1).casefold():
        raise ValueError('broad role anchor absent from profile: ' + person['full_name'])
    return path, raw, title, given, family

def _archive_blocks(text):
    hits = list(re.finditer(r'2000\.\s*(\d{2})\.\s*(\d{2})\.', text))
    blocks = {}
    for i, m in enumerate(hits):
        day = '2000-' + m.group(1) + '-' + m.group(2)
        blocks[day] = text[m.start():hits[i+1].start() if i+1 < len(hits) else len(text)]
    return blocks

def _capacity_assignment(jug, target_names, requested, source_rows, recovered_records):
    from app.fdi_indexed import IndexedFDIFile
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    recovered_entries={c:{e.record_id:e for e in IndexedFDIFile.from_bytes(data).entries}
                       for c,data in recovered_records.items()}
    candidates={}
    display={}
    for name in target_names:
        person=source_rows[name]['source_person']
        project=delta.compiler._pm99_text
        family=person.get('family_name')
        given=person.get('given_name')
        if not (isinstance(given,str) and given.strip() and isinstance(family,str) and family.strip()):
            raise ValueError('every selected source identity requires explicit profile-bound given/family components')
        # The JUG parser stores the last display component as surname. Preserve
        # raw source_person.name separately; always project Western display order.
        proposed=[project(given+' '+family, label='given-first full source name')]
        proposed.append(project(given[0]+'. '+family, label='given-initial plus full family surname'))
        proposed.append(project(family, label='full family surname only'))
        unique=[]
        for value in proposed:
            if value not in unique: unique.append(value)
        candidates[name]=[]
        for carrier in sorted(requested.values()):
            test_jug=recovered_records.get(carrier,jug)
            test_entry=(recovered_entries[carrier][carrier] if carrier in recovered_entries else entries[carrier])
            raw=test_entry.decode_payload(test_jug)
            current=delta.compiler._player_name(raw,record_id=carrier)
            for value in unique:
                try:
                    delta.compiler._patch_indexed_player_variable_name_payload(raw,current,value)
                except (ValueError,RuntimeError):
                    continue
                candidates[name].append(carrier)
                display[(name,carrier)]=value
                break
    if any(not candidates[name] for name in target_names):
        missing=[name for name in target_names if not candidates[name]]
        raise ValueError('no fixed FTC carrier can fit a sourced display alias: '+', '.join(missing))
    order={name:i for i,name in enumerate(target_names)}
    by_carrier={}
    def assign(name,seen):
        preference=sorted(candidates[name],key=lambda c:(c!=requested[name],c))
        for carrier in preference:
            if carrier in seen: continue
            seen.add(carrier)
            if carrier not in by_carrier or assign(by_carrier[carrier],seen):
                by_carrier[carrier]=name
                return True
        return False
    for name in sorted(target_names,key=lambda n:(len(candidates[n]),order[n])):
        if not assign(name,set()):
            raise ValueError('20 source names cannot be matched injectively to the native display windows')
    assigned={name:carrier for carrier,name in by_carrier.items()}
    if len(assigned)!=len(target_names):
        raise ValueError('capacity-aware carrier assignment is incomplete')
    choices={name:display[(name,carrier)] for name,carrier in assigned.items()}
    changes=[dict(source_name=n,requested_carrier=requested[n],assigned_carrier=assigned[n],
                  preferred_display=choices[n]) for n in target_names if requested[n]!=assigned[n]]
    return assigned,choices,changes

def _native_display_form(person, display):
    project=delta.compiler._pm99_text
    given=person['given_name']
    family=person['family_name']
    if display == project(given+' '+family, label='given-first full source name'):
        return 'given-first-full-name'
    if display == project(given[0]+'. '+family, label='given-initial plus full family surname'):
        return 'given-initial-plus-full-family'
    if display == project(family, label='full family surname only'):
        return 'full-family-only'
    raise ValueError('selected native display is not one of the declared source-derived forms')

def prepare(base, input_path):
    input_path = Path(input_path)
    if not input_path.is_absolute():
        input_path = registry.ROOT / input_path
    req = json.loads(input_path.read_text(encoding='utf-8'))
    if req.get('schema') != SCHEMA or req.get('policy') != POLICY:
        raise ValueError('explicit Tempó whole-roster policy required')
    if (base.season, base.release_id) != (req['parent']['season'], req['parent']['release_id']):
        raise ValueError('exact r198a parent ID differs')
    if base.manifest_sha256 != req['parent']['manifest_sha256']:
        raise ValueError('exact r198a manifest pin differs')
    files = {'package':base.package_path, 'JUG98030.FDI':base.game_path/'DBDAT/JUG98030.FDI',
             'EQ98030.FDI':base.game_path/'DBDAT/EQ98030.FDI', 'TEXTOS.PKF':base.game_path/'DBDAT/TEXTOS.PKF'}
    for field, expected in req['parent']['release_bindings'].items():
        if registry.sha256_file(files[field]) != expected:
            raise ValueError('exact r198a input pin changed: ' + field)
    _, cohort_raw = bind_source(req['cohort']['path'], req['cohort']['sha256'])
    _, nat_raw = bind_source(req['nationality_review']['path'], req['nationality_review']['sha256'])
    _, allocation_raw = bind_source(req['allocation_review']['path'], req['allocation_review']['sha256'])
    cohort, nat, allocation = map(json.loads, (cohort_raw, nat_raw, allocation_raw))
    package = json.loads(base.package_path.read_text(encoding='utf-8'))
    clubs = [c for c in package['clubs'] if c['carrier_id'] == CLUB]
    if len(clubs) != 1 or clubs[0]['id'] != 'club-1701' or len(clubs[0]['roster_player_ids']) != 21:
        raise ValueError('r198a FTC recipe capacity not exactly 21')
    club = clubs[0]
    players = {p['id']:p for p in package['players']}
    old = {p['carrier_id']:p for p in package['players'] if p['club_id'] == club['id']}
    if len(old) != 21 or {p['id'] for p in old.values()} != set(club['roster_player_ids']):
        raise ValueError('exact FTC actor/recipe set differs')
    jug = (base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    owners = ordering.native_owners(eq)
    native = {c:exchange.facts.native_facts(jug,c) for c in old}
    if any(owners.get(c) != {CLUB} for c in old):
        raise ValueError('all FTC carrier owners must remain exactly {1701}')
    for expected in req['parent']['ftc_carrier_preimages']:
        observed = native.get(expected['carrier_id'])
        if (observed is None or observed['name'] != expected['native_name']
                or observed['birth_date'] != expected['native_dob']
                or observed['position'] != expected['native_position']
                or observed['startup_order'] != expected['native_order']
                or owners.get(expected['carrier_id']) not in ({CLUB}, [CLUB])):
            raise ValueError('r198a carrier preimage/owner differs: ' + str(expected['carrier_id']))
    if (native[GERA]['name'],native[GERA]['birth_date'],native[GERA]['position']) != ('Gera','1979-04-22','M'):
        raise ValueError('preserved source Gera is not exact native carrier 30027')
    if owners.get(SCHALKE_HAJNAL) == {CLUB}:
        raise ValueError('Schalke Hajnal carrier 14706 must remain outside FTC')
    recovery_req=req.get('capacity_recovery',{})
    if recovery_req.get('selected_carrier_ids') != [1924,1930]:
        raise ValueError('only the minimum exact two-carrier recovery [1924,1930] is approved')
    capacity_bundle=recovery_req.get('runtime_bundle')
    if not isinstance(capacity_bundle,dict):
        raise ValueError('exact same-carrier capacity runtime bundle is required')
    recovered_records={}
    recovery_claims={}
    for carrier in recovery_req['selected_carrier_ids']:
        recovered_records[carrier],recovery_claims[carrier]=name_capacity.recover_slot(jug,carrier,capacity_bundle)
    if (set(recovery_claims)!={1924,1930}
            or recovery_claims[1924]['recovery']['recovered_name_bytes']!=10
            or recovery_claims[1930]['recovery']['recovered_name_bytes']!=8):
        raise ValueError('minimum carrier1924/1930 recoveries differ from exact reviewed factory inverses')
    from app.fdi_indexed import IndexedFDIFile
    ee = next(e for e in IndexedFDIFile.from_bytes(eq).entries if e.record_id == CLUB)
    er = delta.compiler.parse_eq_external_team_roster_payload(eq[ee.payload_offset:ee.payload_offset+ee.payload_length],{})
    if er is None or er.mode_byte != 1 or any(r.flag for r in er.rows) or len(er.rows) != 21:
        raise ValueError('r198a FTC native EQ is not unflagged mode-1 capacity 21')
    country_table = delta.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    archive_rel = (ROOT / cohort['dated_match_archive_source']['path']).as_posix()
    _, archive_raw = bind_source(archive_rel, cohort['dated_match_archive_source']['sha256'])
    blocks = _archive_blocks(visible(archive_raw))
    by_name = {p['full_name']:p for p in cohort['players']}
    if req['capacity_tail']['aug19_selection'] != ['Balog Zoltán','Gyepes Gábor']:
        raise ValueError('only the reviewed positive-source Aug19 capacity pair is admitted')
    names = list(cohort['first_three_fixture_union_19']) + req['capacity_tail']['aug19_selection']
    if len(names) != 21 or len(set(names)) != 21 or set(names)-set(by_name):
        raise ValueError('cohort selection not 19 first-three plus exact two Aug19 members')
    countries = _claims(nat)
    if set(names) - set(countries):
        raise ValueError('a selected source identity has no explicit country evidence')
    requested_carriers = {r['target_source_name']:r['carrier_id'] for r in allocation['identity_assignment']['replace_20']}
    if set(requested_carriers) != set(names)-{'Gera Zoltán'}:
        raise ValueError('approved deterministic crosswalk does not cover exact 20 replacements')
    source_rows, updates, decisions = {}, [], []
    for name in names:
        person = by_name[name]
        profile_role = person['source_profile_role'].split(';')[0].split(' (')[0].strip().lower()
        first_role = profile_role.split(',')[0].split('/')[0].strip()
        role = ('goalkeeper' if 'goalkeeper' in first_role else
                'defender' if 'defender' in first_role else
                'midfielder' if 'midfielder' in first_role else
                'forward' if ('forward' in first_role or 'attacker' in first_role) else None)
        if role not in ROLE:
            raise ValueError('unsupported broad source role: ' + name)
        country, country_evidence = countries[name]
        _verify_country(name,country,country_evidence)
        profile_path, profile_raw, title, given, family = _profile(person,role)
        day = person['first_observed_league_squad_date']
        label = LABELS[name]
        if day not in blocks or label not in blocks[day]:
            raise ValueError('dated league archive lacks exact squad label for ' + name)
        url = person['profile_source']['url']
        provider = 'hlsz' if urlsplit(url).netloc=='hlsz.wsg.hu' else 'tempofradi'
        key = ('hlsz:'+hashlib.sha256(url.encode()).hexdigest()[:24]
               if provider=='hlsz' else 'tempofradi:'+urlsplit(url).path.strip('/').split('/')[-1])
        profile_sha = person['profile_source']['sha256']
        identity = dict(name=name,given_name=given,family_name=family,birth_date=person['dob'],
            source_player_id=key,source_provider=provider,source_profile_url=url,
            source_profile_sha256=profile_sha,identity_policy=ID_POLICY)
        person_key(identity)
        position,fine,_ = ROLE[role]
        native_country = country
        delta.compiler._country_code(native_country,country_table)
        evidence = dict(status='raw-source-reparsed',local_path=profile_path,source_sha256=profile_sha,
            match_archive_path=archive_rel,
            match_archive_sha256=cohort['dated_match_archive_source']['sha256'],
            event_date=day,published_lineup_label=label,
            statement='positive observed matchday squad membership; not official season registration')
        identity['source_country_claim'] = country
        source_rows[name] = dict(source_person=identity,
            source_player=dict(name=name,birth_date=person['dob'],position=position,nationality=native_country,
                height_cm=None,weight_kg=None,shirt_number=None),
            raw_evidence=evidence,membership='original-published-date-bounded-league-squad',
            source_role=person['source_profile_role'],fine_roles=[fine],editorial_role_projection=True,
            source_country_code=country,native_country_code=native_country)
        if name == 'Gera Zoltán':
            continue
    target_names=[n for n in names if n!='Gera Zoltán']
    assigned,display_choice,capacity_changes=_capacity_assignment(
        jug,target_names,requested_carriers,source_rows,recovered_records)
    map_carrier=dict(assigned,**{'Gera Zoltán':GERA})
    for name in target_names:
        carrier=map_carrier[name]
        actor = old[carrier]
        replacement = {k:source_rows[name][k] for k in ('source_person','source_player','raw_evidence','membership')}
        update=dict(layer='main',player_id=actor['id'],carrier_id=carrier,before=actor,
            replacement=replacement,replacement_opening_evidence=dict(date=day,source_club_id='club-1701',
                raw_sources=[dict(path=source_rows[name]['raw_evidence']['local_path'],
                                      sha256=source_rows[name]['raw_evidence']['source_sha256']),
                    dict(path=archive_rel,
                         sha256=cohort['dated_match_archive_source']['sha256'])]))
        decision=dict(carrier_id=carrier,preserved_source_carrier=None,before=actor,
            fine_roles=source_rows[name]['fine_roles'],display_name=display_choice[name],
            display_policy='capacity-checked-given-first-family-last-full-initial-or-family-only-CP1252-v3')
        if carrier in recovery_claims:
            update['same_carrier_name_capacity']=recovery_claims[carrier]
            decision['same_carrier_capacity_claim']=recovery_claims[carrier]
        updates.append(update)
        decisions.append(decision)
    xi_names = cohort['source_XI_order_2000_07_22']
    if len(xi_names)!=11 or xi_names[8]!='Gera Zoltán':
        raise ValueError('original XI source order does not preserve Gera at index 9')
    xi = [map_carrier[n] for n in xi_names]
    tail_names = [n for n in cohort['first_three_fixture_union_19'] if n not in xi_names and n!='Gera Zoltán']
    tail_names += req['capacity_tail']['aug19_selection']
    tail_names.sort(key=lambda n:(by_name[n]['first_observed_league_squad_date'],
        cohort['first_three_fixture_union_19'].index(n) if n in cohort['first_three_fixture_union_19']
        else 100+req['capacity_tail']['aug19_selection'].index(n)))
    tail = [map_carrier[n] for n in tail_names]
    all_order = xi+tail
    if len(all_order)!=21 or len(set(all_order))!=21 or len(tail)!=10:
        raise ValueError('source XI plus chronological tail must fill exactly 21 unique actors')
    orders = [dict(carrier_id=c,native_name=native[c]['name'],before=native[c]['startup_order'],after=i)
              for i,c in enumerate(all_order,1)]
    complete_plan = dict(policy=complete.POLICY,club_carrier_id=CLUB,club_id='club-1701',
        orders=orders,starting_xi=xi,fixture_date='2000-07-22',chronological_tail=tail,
        reserve_policy='first-observed-league-date then source cohort order; Aug19 tie order is explicit',
        reserve_bench_order_claim=False,opaque_tactics_unchanged=True)
    request = dict(schema=exchange.INPUT_SCHEMA,season=base.season,release_id=base.release_id,
        proposal_kind=POLICY,moves=[],retirements=[],new_people=[
            dict(carrier_id=map_carrier[n],club_id='club-1701',name=n,
                 provider_key=source_rows[n]['source_person']['source_player_id'],
                 opening_fixture_date=source_rows[n]['raw_evidence']['event_date'])
            for n in names if n!='Gera Zoltán'],complete_mode1_opening=complete_plan,
        same_carrier_name_capacity=capacity_bundle)
    plan = dict(schema=exchange.SCHEMA,schema_version=delta.planner.SCHEMA,
        season=base.season,release_id=base.release_id,
        source_input=dict(path=registry.relative_workspace_path(Path(input_path)),sha256=registry.sha256_file(Path(input_path))),
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=sha(jug),eq_sha256=sha(eq),
        request=request,updates=updates,decisions=decisions,complete_mode1_opening=complete_plan,
        selected_carriers=sorted(set(map_carrier.values())-{GERA}),source_players=source_rows,
        bindings=dict(snapshot=dict(project_url=cohort['dated_match_archive_source']['url'],
            same_carrier_name_capacity=capacity_bundle)),
        source_title='Dated Tempó Fradi opening XI and capacity-bounded 2000 participant cohort with given-first native display projection',
        proof_covers=['source-bound-opening-XI','positive-observed-matchday-membership','no-retirement-claims',
                      'editorial-central-role-projection','source-country-code-exactly-translated-through-bound-TEXTOS-table'],
        scope='Replace 20 FTC-exclusive inherited local slots; preserve Gera 30027 and Schalke Hajnal 14706; mode-1 capacity stays 21.')
    plan['allow_same_carrier_name_capacity']=True
    plan['capacity_recovery']={'selected_carrier_ids':[1924,1930], 'claims':{str(c):claim for c,claim in recovery_claims.items()},
        'bundle':capacity_bundle, 'scope':'Only recovered native player JUG records1924 and1930 before existing compiler. Every other record and other club remains exact.'}
    plan['requested_source_carriers']=requested_carriers
    plan['capacity_aware_carrier_assignments']=map_carrier
    plan['capacity_fit_reassignments']=capacity_changes
    plan['display_name_fits']=[dict(carrier_id=map_carrier[n],source_name=n,
        display_name=display_choice[n],method=_native_display_form(source_rows[n]['source_person'],display_choice[n]))
        for n in target_names]
    plan['transaction_id'] = exchange.digest(packages.canonical_json_bytes(plan))[:24]
    return plan

def bind(package, plan):
    result = exchange.bind(package,plan)
    packages.validate_package(result)
    return result

def apply(jug,eq,plan):
    return exchange.apply(jug,eq,plan)

