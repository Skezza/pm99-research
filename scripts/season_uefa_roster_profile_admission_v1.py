"""Generic retained UEFA player-table and exact-profile source admissions.

PDF nationality claims use the existing known-wrong-country writer. A separate
explicit profile policy corrects the primary fine role through the existing
native role API, preserving all five secondary role slots. Legacy factory
projection rules remain unchanged.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import copy
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from scripts import season_official_career_context_v1 as official
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES
from scripts.season_exact_fifa_role_delta_v1 import compatible
from scripts.season_historical_roster_audit_v1 import normalise

PROVIDER = "uefa-player-roster-table-pdf-v1"
UEFA_HOSTS = {"www.uefa.com", "uefa.com"}
HEADER = ("No.", "Name", "Position", "Date of Birth", "Nationality",
          "Height (cm)", "Joined", "Previous Club")
POSITION_TO_BROAD = {"Defender": "D", "Midfielder": "M", "Forward": "F",
                     "Goalkeeper": "G"}


def _workspace_file(binding: dict) -> tuple[Path, bytes]:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("source binding must contain only path and SHA-256")
    rel = binding["path"]
    if not isinstance(rel, str) or Path(rel).is_absolute():
        raise ValueError("source path must be workspace-relative")
    path = registry.ROOT / rel
    if (path.is_symlink() or not path.resolve().is_relative_to(registry.ROOT.resolve())
            or not path.is_file()):
        raise ValueError("source must be a regular retained workspace file")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("retained source SHA-256 differs")
    return path, raw


def _label_key(value: str) -> str:
    return " ".join(normalise(value).split())


def _club_key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_value.casefold())
    while words and words[0] in {"cd", "fc", "cf", "sc", "club", "football"}:
        words.pop(0)
    return " ".join(words)


def _table_lines(page: list[str], expected_club_label: str) -> list[tuple[str, list[str]]]:
    heading_rows = [i for i, line in enumerate(page)
                    if "|" in line and line.split("|", 1)[1].strip().startswith("Group")]
    matches = []
    for heading_index in heading_rows:
        heading = page[heading_index].split("|", 1)[0].strip()
        if _club_key(heading) != _club_key(expected_club_label):
            continue
        header_pattern = re.compile(
            r"^No\.\s+Name\s+Position\s+Date of Birth\s+Nationality\s+"
            r"Height \(cm\)\s+Joined\s+Previous Club$", re.IGNORECASE)
        header_indices = [i for i in range(heading_index + 1, min(len(page), heading_index + 14))
                          if header_pattern.fullmatch(" ".join(page[i].split()))]
        if len(header_indices) != 1:
            continue
        header_index = header_indices[0]
        if not any(line.strip() == "PLAYERS" for line in page[heading_index + 1:header_index]):
            continue
        for line in page[header_index + 1:]:
            cells = [x.strip() for x in re.split(r"\s{2,}", line.strip()) if x.strip()]
            if cells and re.fullmatch(r"\d+", cells[0]) and len(cells) == len(HEADER):
                matches.append((heading, cells))
            if "GROUP FIXTURES" in line.upper():
                break
    return matches


def parse_roster_table_text(text: str, *, full_name: str, birth_date: str,
                            expected_club_label: str) -> dict:
    """Parse exactly one literal player row from the selected handbook club."""
    try:
        datetime.strptime(birth_date, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError("expected DOB must be exact ISO date") from exc
    rows = []
    for page in text.split("\f"):
        rows.extend(_table_lines(page.splitlines(), expected_club_label))
    exact_name = [row for row in rows if _label_key(row[1][1]) == _label_key(full_name)]
    if len(exact_name) != 1:
        raise ValueError("exact full name must identify one row in the selected club table")
    heading, cells = exact_name[0]
    try:
        parsed_dob = datetime.strptime(cells[3], "%d.%m.%Y").date().isoformat()
    except ValueError as exc:
        raise ValueError("UEFA row DOB is not an exact day/month/year literal") from exc
    country_code = cells[4]
    broad = POSITION_TO_BROAD.get(cells[2])
    if parsed_dob != birth_date:
        raise ValueError("UEFA row DOB differs from the bound annual person identity")
    if broad is None:
        raise ValueError("UEFA row position is outside the reviewed broad-position vocabulary")
    if (not re.fullmatch(r"[A-Z]{3}", cells[4])
            or country_code not in set(NATIONALITY_CODES.values())):
        raise ValueError("UEFA row nationality must be a supported three-letter country code")
    return {
        "provider": PROVIDER,
        "club_context": heading,
        "full_name": cells[1],
        "position_literal": cells[2],
        "broad_position": broad,
        "birth_date": parsed_dob,
        "nationality_literal": cells[4],
        "nationality": country_code,
        "height_cm": int(cells[5]),
        "joined_year": int(cells[6]),
        "previous_club": cells[7],
        "row_cells": cells,
    }


def admit_pdf_row(source: dict, *, full_name: str, birth_date: str,
                  expected_club_label: str) -> dict:
    """Reproduce PDF body, transport receipt, extraction and row claims."""
    allowed = {"url", "body", "receipt", "document_type", "text_extraction"}
    if (set(source) not in (allowed, allowed | {"provider"})
            or source.get("provider") not in (None, PROVIDER)):
        raise ValueError("UEFA roster PDF source binding schema differs")
    parsed = urlsplit(source["url"])
    if (parsed.scheme != "https" or parsed.hostname not in UEFA_HOSTS
            or source.get("document_type") != "application/pdf"
            or not re.fullmatch(r"/multimediafiles/download/publications/uefa/uefamedia/(?:\d+/){3}\d+_download\.pdf",
                                parsed.path, re.IGNORECASE)):
        raise ValueError("source URL is outside the generic UEFA handbook PDF family")
    body_path, body = _workspace_file(source["body"])
    receipt_path, _ = _workspace_file(source["receipt"])
    import json
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("url") != source["url"] or receipt.get("final_url") != source["url"]
            or receipt.get("http_status") != 200
            or receipt.get("method") != "original-network-body-pdf"
            or receipt.get("raw_sha256") != source["body"]["sha256"]):
        raise ValueError("UEFA original PDF transport receipt differs")
    extraction = source["text_extraction"]
    text_path, _ = _workspace_file(extraction)
    text = official.source_text({
        "url": source["url"], "path": source["body"]["path"],
        "sha256": source["body"]["sha256"], "document_type": "application/pdf",
        "text_extraction": {**extraction, "extractor_mode": "-layout"},
    })
    row = parse_roster_table_text(text, full_name=full_name,
                                  birth_date=birth_date,
                                  expected_club_label=expected_club_label)
    return {**row, "url": source["url"],
            "body_path": registry.relative_workspace_path(body_path),
            "body_sha256": source["body"]["sha256"],
            "receipt_path": registry.relative_workspace_path(receipt_path),
            "receipt_sha256": source["receipt"]["sha256"],
            "text_path": registry.relative_workspace_path(text_path),
            "text_sha256": extraction["sha256"],
            "target_season_ownership_claimed": False,
            "height_or_joined_year_edit_claimed": False}



PROFILE_ROLE_POLICY = 'indexed-exact-provider-profile-DOB-and-published-detailed-position-v1'


def workspace_path(binding):
    return _workspace_file(binding)[0]


def _name_crosswalk(short, full):
    wanted = [normalise(word) for word in str(short).split() if normalise(word)]
    published = [normalise(word) for word in str(full).split() if normalise(word)]
    if len(wanted) < 2 or len(published) < len(wanted) or wanted[0] != published[0] or wanted[-1] != published[-1]:
        return False
    remaining = iter(published)
    return all(any(word == candidate for candidate in remaining) for word in wanted)

def parse_indexed_role(binding, *, annual_name, annual_birth_date, annual_provider_id):
    path = workspace_path(binding)
    cap = pipeline.read_json_file(path)
    url = cap.get('profile_url','')
    if (cap.get('schema') != 'pm99-indexed-profile-result-capture-v1'
        or cap.get('capture_method') != 'web-search-indexed-result-transcription'
        or cap.get('provider') != 'transfermarkt-indexed-profile-result-v1'
        or not re.fullmatch(r'https://www\.transfermarkt\.com/[a-z0-9-]+/profil/spieler/' + re.escape(str(annual_provider_id)), url)
        or cap.get('provider_player_id') != str(annual_provider_id)
        or cap.get('identity_crosswalk',{}).get('annual_provider_player_id') != str(annual_provider_id)):
        raise ValueError('indexed profile source family or exact provider ID differs')
    claims = cap.get('claims',{})
    crosswalk = cap.get('identity_crosswalk',{})
    indexed_text=cap.get('indexed_text','')
    if (claims.get('published_birth_date') != annual_birth_date
        or crosswalk.get('annual_birth_date') != annual_birth_date
        or crosswalk.get('annual_source_name') != annual_name
        or not _name_crosswalk(annual_name, claims.get('published_full_name',''))
        or hashlib.sha256(indexed_text.encode()).hexdigest()!=cap.get('sha256_of_indexed_text')
        or url not in indexed_text
        or claims.get('published_full_name') not in indexed_text
        or f"Date of birth: {datetime.strptime(annual_birth_date,'%Y-%m-%d').strftime('%d/%m/%Y')}" not in indexed_text
        or f"Citizenship: {claims.get('published_country')}" not in indexed_text):
        raise ValueError('exact profile DOB or declared full-name crosswalk differs')
    position = claims.get('published_position')
    if not isinstance(position,str) or not re.search(r'Position: (?:Goalkeeper|Defender|Midfielder|Forward) - ' + re.escape(position) + r'(?:[.\s]|$)', indexed_text):
        raise ValueError('indexed profile has no literal detailed position')
    role_key = re.sub(r'[^a-z]', '', position.casefold())
    from scripts.season_historical_role_plan_v1 import HTML_ROLES
    if role_key not in HTML_ROLES:
        raise ValueError('published detailed position has no existing native role mapping')
    fine_role = HTML_ROLES[role_key]
    # Existing mapping taxonomy: right-back -> native fine code 1.
    return {'provider':cap['provider'],'profile_url':url,'provider_player_id':str(annual_provider_id),
            'published_full_name':claims['published_full_name'],'annual_source_name':annual_name,
            'birth_date':annual_birth_date,'position_literal':position,'fine_role_code':fine_role,
            'mapping':'season_historical_role_plan_v1.HTML_ROLES exact normalized published label',
            'indexed_text_sha256':cap['sha256_of_indexed_text'],
            'capture_path':binding['path'],'capture_sha256':binding['sha256'],
            'claim_scope':'published profile position, not a date-specific opening-lineup role'}


def verify_annual_source_chain(binding, *, annual_name, annual_birth_date, expected_provider_id):
    """Bind shared source-row facts and the ID/fixture fields added at preallocation."""
    from scripts.season_source_package_builder_v1 import _source_person_id
    docs=[]
    for key in ('preallocation','source_intake'):
        f=binding[key]; path=workspace_path(f)
        doc=pipeline.read_json_file(path)
        if doc.get('season',{}).get('label')!=binding['season_label']:
            raise ValueError('annual source artifact season differs')
        rows=[(club,row) for club in doc.get('source_clubs',[]) for row in club.get('players',[])
              if row.get('source_row_sha256')==binding['source_row_sha256']]
        if len(rows)!=1: raise ValueError('annual source row is absent or ambiguous')
        club,row=rows[0]
        facts=row.get('facts',{})
        if (row.get('source_row_index')!=binding['source_row_index'] or facts.get('name')!=annual_name
            or facts.get('birth_date')!=annual_birth_date
            or facts.get('position')!=binding['expected_broad_position']
            or club.get('selector')!=binding['selector']):
            raise ValueError('annual source row index/name/DOB/broad role/club differs')
        docs.append((club,row))
    if docs[0][0].get('selector')!=docs[1][0].get('selector'):
        raise ValueError('annual source selector differs across retained artifacts')
    pre_club,pre_row=docs[0]
    normalized_pre=copy.deepcopy(pre_row)
    for key in ('opening_source_player_id','opening_xi_order','opening_xi_origin'):
        normalized_pre.pop(key,None)
    if normalized_pre!=docs[1][1]:
        raise ValueError('preallocation row differs from source-intake row beyond the three documented opening annotations')
    pid=str(pre_row.get('opening_source_player_id') or '')
    if (pid!=str(expected_provider_id) or pre_club.get('opening_source_match_id')!=str(binding['fixture_match_id'])
        or pre_club.get('opening_fixture_date')!=binding['fixture_date']
        or _source_person_id(pre_row)!=binding.get('person_id')):
        raise ValueError('preallocation provider ID/person ID/opening fixture link differs')
    return {'provider_player_id':pid,'source_row_sha256':binding['source_row_sha256'],
        'source_row_index':binding['source_row_index'],'full_name':annual_name,
        'birth_date':annual_birth_date,'broad_position':binding['expected_broad_position'],'selector':docs[0][0]['selector'],
        'fixture_match_id':str(binding['fixture_match_id']),'fixture_date':binding['fixture_date']}


def parse_country(raw, source, *, actor_name, birth_date):
    """Read a literal nationality; never infer it from the club or birthplace."""
    if (hashlib.sha256(raw).hexdigest() != source['body']['sha256']
            or source['path'] != source['body']['path'] or source['sha256'] != source['body']['sha256']):
        raise ValueError('UEFA source body differs from the country input')
    verify_annual_source_chain(source['annual_source_binding'], annual_name=actor_name,
        annual_birth_date=birth_date, expected_provider_id=source['annual_source_binding']['provider_player_id'])
    parsed = admit_pdf_row({k: source[k] for k in
        ('url', 'body', 'receipt', 'document_type', 'text_extraction', 'provider')},
        full_name=actor_name, birth_date=birth_date, expected_club_label=source['expected_club_label'])
    return dict(name=parsed['full_name'], birth_date=parsed['birth_date'],
        published_country=parsed['nationality_literal'], nationality=parsed['nationality'],
        provider=PROVIDER, url=source['url'], source_row=parsed,
        target_season_ownership_claimed=False, height_or_joined_year_edit_claimed=False)


def prepare_profile_role(base, request, input_path):
    """Correct only a source-bound primary fine role; preserve secondary slots."""
    from scripts import season_editorial_factory_role_projection_v1 as legacy
    from scripts import season_package_v2 as packages
    from scripts import season_opening_identity_exchange_v1 as exchange
    from scripts import season_source_package_builder_v1 as builder
    from scripts import season_opening_order_repair_v1 as ownership
    from scripts.season_historical_roster_audit_v1 import native_player
    from scripts.season_within_club_reserve_repair_v1 import native_facts
    from app.fdi_indexed import IndexedFDIFile
    from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_primary_roles
    if (request.get('schema') != legacy.INPUT_SCHEMA or request.get('kind') != legacy.KIND
            or request.get('policy') != legacy.POLICY or request.get('role_source_policy') != PROFILE_ROLE_POLICY
            or request.get('season') != base.season or request.get('release_id') != base.release_id
            or type(request.get('carrier_id')) is not int):
        raise ValueError('exact parent and explicit literal-profile role policy required')
    for key, path in [('package', base.package_path), ('manifest', base.release_manifest_path),
                      ('jug', base.game_path/'DBDAT/JUG98030.FDI'), ('eq', base.game_path/'DBDAT/EQ98030.FDI')]:
        if request.get('parent_' + key + '_sha256') != registry.sha256_file(path):
            raise ValueError('profile role immutable parent changed')
    witness = request['historical_identity_witness']
    historical = witness['historical_identity']
    annual = witness['annual_identity']
    pid = str(historical['provider_player_id'])
    claim = verify_annual_source_chain(annual['source_chain'], annual_name=witness['full_name'],
        annual_birth_date=annual['birth_date'], expected_provider_id=pid)
    if (claim['source_row_sha256'] != historical['source_row_sha256']
            or claim['fixture_match_id'] != str(historical['match_id'])
            or claim['fixture_date'] != historical['match'].get('date')
            or claim['fixture_date'][:4] != base.season[:4]):
        raise ValueError('annual row and target-year fixture crosslink differs')
    match = historical['match']; exchange.original(match)
    parsed_url = urlsplit(match['url'])
    if (parsed_url.scheme != 'https' or parsed_url.hostname not in {
            'www.transfermarkt.co.uk', 'www.transfermarkt.com', 'www.transfermarkt.us'}
            or not re.fullmatch(r'/spielbericht/index/spielbericht/' + re.escape(str(historical['match_id'])), parsed_url.path)
            or parsed_url.query or parsed_url.fragment):
        raise ValueError('opening fixture URL is outside its exact provider route')
    xi, bench = exchange.match_people(match)
    if sum(str(p.get('source_player_id')) == pid for p in xi + bench) != 1:
        raise ValueError('profile person is not a unique participant in the selected fixture')
    parsed = parse_indexed_role(request['source_role_evidence'], annual_name=witness['full_name'],
        annual_birth_date=annual['birth_date'], annual_provider_id=pid)
    package = pipeline.read_json_file(base.package_path)
    actors = [a for a in package['players'] if a['carrier_id'] == request['carrier_id']]
    if len(actors) != 1:
        raise ValueError('profile role carrier is ambiguous')
    actor = actors[0]; carrier = actor['carrier_id']
    chain = annual['source_chain']; allocation = pipeline.read_json_file(workspace_path(chain['preallocation']))
    source_club, source_row = next((c, r) for c in allocation['source_clubs'] for r in c['players']
                                  if r.get('source_row_sha256') == claim['source_row_sha256'])
    artifact_id = 'opening-squad-preallocation-' + base.season
    artifacts = [a for a in package['artifacts'] if a['id'] == artifact_id]
    if (len(artifacts) != 1 or artifacts[0]['sha256'] != chain['preallocation']['sha256']
            or actor.get('person_id') != builder._source_person_id(source_row)
            or actor.get('person_id') != witness['person_id'] or actor.get('source_name') != witness['full_name']
            or actor['facts']['birth_date'] != claim['birth_date']
            or actor['facts']['primary_position'] != claim['broad_position']
            or actor['facts']['fine_roles'] != {'policy': 'preserve-existing-mode1'}):
        raise ValueError('literal role does not bind the exact annual recipe identity')
    expected_bindings = {'preallocation': chain['preallocation'], 'fixture': {
        'path': match['path'], 'sha256': match['sha256']}}
    if request['source_bindings'] != expected_bindings:
        raise ValueError('literal role source bindings differ')
    fine = parsed['fine_role_code']
    if not compatible(claim['broad_position'], fine):
        raise ValueError('published detailed role conflicts with annual broad position')
    jug = (base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    entry = next(e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id == carrier)
    payload = entry.decode_payload(jug); end, before_roles = read_indexed_native_roles(payload, carrier)
    native = native_player(payload, carrier); facts = native_facts(jug, carrier)
    club = next(c for c in package['clubs'] if c['id'] == actor['club_id'])
    if (normalise(native['name']) != normalise(actor['name']) or facts['birth_date'] != claim['birth_date']
            or native['position'] != claim['broad_position']
            or ownership.native_owners(eq).get(carrier) != {club['carrier_id']}
            or before_roles[0] in (fine, 98) or fine in before_roles[1:]):
        raise ValueError('native literal-role identity, owner or primary-role preimage differs')
    after, _ = rewrite_indexed_native_primary_roles(jug, {carrier: (before_roles[0], fine)})
    after_roles = read_indexed_native_roles(entry.decode_payload(after), carrier)[1]
    if after_roles != [fine] + before_roles[1:]:
        raise ValueError('literal-role edit changed secondary roles')
    offset = entry.payload_offset + end + 2
    result = dict(schema=legacy.SCHEMA, kind=legacy.KIND, policy=PROFILE_ROLE_POLICY,
        season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path), jug_sha256=hashlib.sha256(jug).hexdigest(),
        eq_sha256=hashlib.sha256(eq).hexdigest(), source_input={'path': registry.relative_workspace_path(input_path),
            'sha256': registry.sha256_file(input_path)}, updates=[dict(carrier_id=carrier, before=copy.deepcopy(actor),
            field_mask=['fine_roles'], values={'fine_roles': [r for r in after_roles if r != 98]},
            native_masks=[dict(file='DBDAT/JUG98030.FDI', record_offset=end+2, file_offset=offset,
                before=jug[offset], after=after[offset])], expected_owner=club['carrier_id'],
            evidence={'historical_identity_witness': copy.deepcopy(witness),
                'source_bindings': copy.deepcopy(request['source_bindings']), 'published_fine_role_source': parsed,
                'before_native_roles': before_roles, 'after_native_roles': after_roles})],
        scope='Only source-bound primary fine role and its recipe fact; five secondary role bytes and all other native/recipe fields remain unchanged.')
    result['transaction_id'] = hashlib.sha256(packages.canonical_json_bytes(result)).hexdigest()[:24]
    return result


def validate_profile_role(plan):
    path = workspace_path(plan['source_input'])
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    if prepare_profile_role(base, pipeline.read_json_file(path), path) != plan:
        raise ValueError('literal-role source plan does not independently reproduce')

