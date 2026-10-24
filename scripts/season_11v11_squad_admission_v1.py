"""Workspace-bound 11v11 biography and dated annual-squad admission.

The exact 11v11 profile supplies identity and a named club-career interval.
FootballSquads supplies the exact target-season club/name/DOB/position row and
is independently reparsed by the existing season SourceVerifier. This proves
dated roster membership only, not matchday selection or appearance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import csv
import hashlib
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry


POLICY = "11v11+footballsquads-independent-row-v2"
CAPTURE_SCHEMAS = {"pm99-original-http-source-capture-v1", "first8-positive-replacements-source-capture-v2"}
NATIONALITY_LABEL_ALIASES = {
    "English": "England", "Scottish": "Scotland", "Welsh": "Wales",
    "Northern Irish": "Northern Ireland", "Irish": "Republic of Ireland",
    "French": "France", "German": "Germany", "Spanish": "Spain",
    "Dutch": "Netherlands", "Italian": "Italy", "Brazilian": "Brazil",
    "Argentine": "Argentina", "Portuguese": "Portugal", "American": "United States",
}
POSITION_LABEL_TO_BROAD = {
    "goalkeeper": "G", "keeper": "G",
    "defender": "D", "defence": "D", "defender/midfielder": "D",
    "midfielder": "M", "midfield": "M", "midfielder/forward": "M",
    "forward": "F", "striker": "F", "forward/midfielder": "F",
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _workspace_file(bound: dict) -> tuple[object, bytes]:
    from pathlib import Path
    if not isinstance(bound, dict) or not isinstance(bound.get("path"), str):
        raise ValueError("source binding requires a retained workspace path")
    root = registry.ROOT.resolve()
    path = Path(bound["path"])
    path = path if path.is_absolute() else root / path
    absolute = path.absolute()
    try:
        relative = absolute.relative_to(root)
        resolved = absolute.resolve(strict=True)
        resolved.relative_to(root)
    except (ValueError, OSError) as exc:
        raise ValueError("source path must exist inside the workspace") from exc
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("source path may not traverse a symlink")
    if resolved != absolute:
        raise ValueError("source path resolution changed through a symlink or alias")
    raw = absolute.read_bytes()
    if sha256(raw) != bound.get("sha256"):
        raise ValueError("retained source SHA-256 differs")
    return absolute, raw


@dataclass(frozen=True)
class Identity:
    provider: str
    provider_player_id: str
    full_name: str
    birth_date: str
    nationality_label: str
    profile_position: str
    careers: tuple[dict, ...]
    profile_url: str


def _verify_capture_receipt(bound: dict, receipt_binding: dict, url: str, pid: str) -> dict:
    _, receipt_raw = _workspace_file(receipt_binding)
    import json
    receipt = json.loads(receipt_raw)
    if receipt.get("schema") not in CAPTURE_SCHEMAS:
        raise ValueError("original 11v11 capture receipt schema differs")
    rows = [row for row in receipt.get("sources", [])
            if row.get("path") == bound["path"] and row.get("sha256") == bound["sha256"]
            and row.get("url") == url and row.get("final_url") == url
            and row.get("http_status") == 200]
    if len(rows) != 1:
        raise ValueError("capture receipt must bind one exact successful 11v11 response")
    _, raw = _workspace_file(bound)
    if sha256(raw) != rows[0]["sha256"]:
        raise ValueError("captured 11v11 body does not match original receipt")
    return rows[0]


def parse_11v11(bound: dict, capture_receipt: dict) -> Identity:
    """Parse a unique player profile, unique bio fields and unique career table."""
    path, raw = _workspace_file(bound)
    url = bound.get("url")
    requested = urlsplit(url or "")
    match = re.fullmatch(r"/players/[a-z0-9-]+-([1-9]\d*)/?", requested.path)
    if (requested.scheme != "https" or requested.netloc != "www.11v11.com" or not match
            or requested.query or requested.fragment
            or bound.get("final_url") != url or bound.get("http_status") != 200):
        raise ValueError("11v11 source must be one exact successful player URL")
    pid = match.group(1)
    _verify_capture_receipt(bound, capture_receipt, url, pid)
    soup = BeautifulSoup(raw, "html.parser")
    h1s = soup.find_all("h1")
    og_urls = soup.select('meta[property="og:url"]')
    og_titles = soup.select('meta[property="og:title"]')
    if len(h1s) != 1 or len(og_urls) != 1 or len(og_titles) != 1:
        raise ValueError("11v11 must contain one h1 and one self URL/title")
    name = " ".join(h1s[0].get_text(" ", strip=True).split())
    if (not name or og_urls[0].get("content") != url
            or " ".join(og_titles[0].get("content", "").split()) != name):
        raise ValueError("11v11 page title and self URL do not bind one profile")

    bio_tables, career_tables = [], []
    for table in soup.select("table"):
        rows = [[" ".join(cell.get_text(" ", strip=True).split())
                 for cell in tr.find_all(["th", "td"], recursive=False)]
                for tr in table.select("tr")]
        labels = [r[0].rstrip(":").casefold() for r in rows if len(r) >= 2]
        if {"date of birth", "nationality", "position"} <= set(labels):
            bio_tables.append(rows)
        if rows and [v.casefold() for v in rows[0][:4]] == ["team", "joined", "left", "loan / trialist"]:
            career_tables.append(rows)
    if len(bio_tables) != 1 or len(career_tables) != 1:
        raise ValueError("11v11 requires one biography table and one career table")
    bio_rows = [r for r in bio_tables[0] if len(r) >= 2]
    bio = {}
    for label in ("date of birth", "nationality", "position"):
        fields = [r[1].strip() for r in bio_rows if r[0].rstrip(":").casefold() == label]
        if len(fields) != 1 or not fields[0]:
            raise ValueError("11v11 biography fields must be unique and nonempty")
        bio[label] = fields[0]
    birthday = _parse_long_date(bio["date of birth"])
    careers = []
    for row in career_tables[0][1:]:
        if len(row) < 3 or not row[0].strip():
            continue
        joined, left = _parse_short_date(row[1]), _parse_short_date(row[2])
        if joined > left:
            raise ValueError("11v11 career row has inverted dates")
        careers.append({"club": row[0].strip(), "joined": joined, "left": left,
                        "loan_or_trialist": bool(len(row) > 3 and row[3].strip())})
    if not careers:
        raise ValueError("11v11 profile has no dated club history")
    return Identity("11v11", pid, name, birthday, bio["nationality"],
                    bio["position"], tuple(careers), url)


def _parse_long_date(value: str) -> str:
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("11v11 exact day/month/year DOB is required")


def _parse_short_date(value: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%d %b %Y").date().isoformat()
    except ValueError as exc:
        raise ValueError("11v11 career date must name day, month and year") from exc


def _matches_short_dob(literal: str, exact_iso: str) -> bool:
    """Compare DD-MM-YY to the exact profile year suffix; never century-pivot."""
    if not re.fullmatch(r"\d{2}-\d{2}-\d{2}", literal.strip()):
        return False
    exact = date.fromisoformat(exact_iso)
    day, month, year2 = literal.strip().split("-")
    return (int(day), int(month), int(year2)) == (exact.day, exact.month, exact.year % 100)


def _verify_football_squads_source_file(season: str, source_path: str, source_sha: str) -> dict:
    """Reparse the captured annual file; this does not validate its Past Players row."""
    from pathlib import Path
    from scripts import season_historical_roster_audit_v1 as audit
    root = registry.ROOT
    cache_root = root / ".local/external-sources/cache.footballsquads"
    sources, _ = audit.load_sources(season)
    rel = Path(source_path).resolve().relative_to(cache_root.resolve()).as_posix()
    rows = [r for r in sources if r.get("source_path") == rel and r.get("source_sha256") == source_sha]
    if len(rows) != 1:
        raise ValueError("FootballSquads retained capture dataset must bind one exact source row")
    result = audit.SourceVerifier(season).verify(rows[0])
    if result.get("status") != "raw-source-reparsed":
        raise ValueError("existing FootballSquads SourceVerifier did not reparse this source")
    return {"source_path": rel, "source_sha256": source_sha,
            "capture_status": result["status"], "capture_local_path": result.get("local_path")}


def parse_footballsquads(bound: dict, *, season: str, club: str,
                         full_name: str, birth_date: str) -> dict:
    """Parse exact season row, then verify the whole archived source row."""
    from pathlib import Path
    source_url = urlsplit(bound.get("url", ""))
    match = re.fullmatch(r"(\d{4})/(\d{2})", season)
    if not match:
        raise ValueError("target season must use YYYY/YY form")
    year = int(match.group(1))
    if int(match.group(2)) != (year + 1) % 100:
        raise ValueError("target season year suffix is inconsistent")
    season_key = f"{year}-{year + 1}"
    if (source_url.scheme != "https" or source_url.netloc != "www.footballsquads.co.uk"
            or season_key not in source_url.path or bound.get("source_kind") != "retained-normalized-footballsquads-text"):
        raise ValueError("FootballSquads source URL/season/retained-text kind differs")
    path, raw = _workspace_file(bound)
    cache_root = registry.ROOT / ".local/external-sources/cache.footballsquads"
    if not path.is_relative_to(cache_root.resolve()):
        raise ValueError("FootballSquads source must be from the retained source cache")
    source_rel = path.relative_to(cache_root.resolve()).as_posix()
    expected_url = "https://www.footballsquads.co.uk/" + source_rel[:-4] + ".htm" if source_rel.endswith(".txt") else ""
    if bound.get("url") != expected_url:
        raise ValueError("FootballSquads source URL does not map to the bound cached file")
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("=  "):
        raise ValueError("FootballSquads source needs one season/club title row")
    title = lines[0][3:].strip()
    if season not in title or not title.startswith(club + " - "):
        raise ValueError("FootballSquads exact club or season title differs")
    rows, section = [], "current"
    for line in lines[1:]:
        if line.strip() == "== Past Players":
            section = "past"
            continue
        if not line.strip() or line.lstrip().startswith("Number,"):
            continue
        try:
            row = next(csv.reader([line], skipinitialspace=True))
        except csv.Error:
            continue
        if len(row) < 7 or not row[0].strip().isdigit():
            continue
        name, pos, dob = row[1].strip(), row[2].strip(), row[5].strip()
        if name.casefold() == full_name.casefold() and _matches_short_dob(dob, birth_date):
            rows.append({"shirt_number": int(row[0]), "name": name, "position": pos,
                         "birth_date": birth_date, "dob_literal": dob, "section": section,
                         "row": line})
    if len(rows) != 1:
        raise ValueError("FootballSquads needs exactly one same-name/literal-DOB season row")
    row = rows[0]
    if row["position"] not in {"G", "D", "M", "F"}:
        raise ValueError("FootballSquads position is outside G/D/M/F")
    # These dated annual values are not present-day biography measurements.
    # Reuse the existing imperial/metric readers and retain unsupported literals.
    fields = next(csv.reader([row['row']], skipinitialspace=True))
    from scripts.capture_footballsquads_season import _height_cm, _weight_kg, CaptureError
    gaps = []
    for key, index, parser in [('height_cm', 3, _height_cm), ('weight_kg', 4, _weight_kg)]:
        literal = fields[index].strip()
        try:
            row[key] = parser(literal, label=full_name)
        except CaptureError:
            row[key] = None
            gaps.append({'field': key, 'published_literal': literal,
                         'status': 'unavailable-or-unparsed-source-literal'})
    row['secondary_fact_gaps'] = gaps
    # The legacy capture's canonical player list omits its "Past Players"
    # section. The verifier validates the source file/current-roster capture;
    # this adapter separately reparses the exact candidate row above.
    source_capture = _verify_football_squads_source_file(season.replace("/", "-"), str(path), bound["sha256"])
    row["source_file_verification"] = source_capture
    row["candidate_row_reparsed_by_adapter"] = True
    row["candidate_row_in_legacy_canonical_roster"] = False if section == "past" else None
    row["nationality_column_present"] = False
    return row


def _profile_broad_options(profile_position: str) -> set[str]:
    choices = set()
    for label in re.split(r"[/,]", profile_position):
        key = " ".join(label.casefold().split())
        broad = POSITION_LABEL_TO_BROAD.get(key)
        if broad:
            choices.add(broad)
    return choices


def admit(selection: dict, evidence: dict) -> dict:
    """Reparse both sources and emit honest provider + explicit role projection."""
    if selection.get("provider") != POLICY:
        raise ValueError("unsupported explicit 11v11/FootballSquads provider policy")
    selection_season = selection.get("season")
    season_match = re.fullmatch(r"(\d{4})/(\d{2})", str(selection_season))
    if not season_match:
        raise ValueError("membership requires explicit target season YYYY/YY")
    year = int(season_match.group(1))
    if int(season_match.group(2)) != (year + 1) % 100:
        raise ValueError("target season year suffix is inconsistent")
    window = selection.get("membership_window")
    if window != {"start": f"{year}-08-01", "end": f"{year}-08-31"}:
        raise ValueError("membership window must be exactly August of target season")
    profile_bound = evidence[selection["identity_source"]]
    identity = parse_11v11(profile_bound, evidence[selection["capture_receipt_source"]])
    if (identity.provider_player_id != str(selection["provider_player_id"])
            or identity.full_name != selection["full_name"]
            or identity.birth_date != selection["birth_date"]
            or identity.nationality_label != selection["nationality_label"]
            or identity.profile_position != selection["profile_position"]):
        raise ValueError("11v11 profile identity facts differ from selection")
    if date.fromisoformat(identity.birth_date) > date(year, 8, 31):
        raise ValueError('source birthday is later than the target season')
    if selection.get("native_display_name") != identity.full_name:
        raise ValueError("native display must use the exact source full name unless another reviewed source authorizes an alias")
    from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES
    country_label = NATIONALITY_LABEL_ALIASES.get(identity.nationality_label, identity.nationality_label)
    if NATIONALITY_CODES.get(country_label) != selection["nationality"]:
        raise ValueError("11v11 source nationality does not map through existing native country codes")
    options = _profile_broad_options(identity.profile_position)
    role = selection.get("editorial_fine_role")
    from scripts.season_exact_fifa_role_delta_v1 import compatible
    if (not isinstance(role, dict) or role.get("classification") != "editorial-compatible-not-source-specific"
            or type(role.get("code")) is not int or not compatible(selection["position"], role["code"])):
        raise ValueError("one explicitly editorial fine role compatible with broad source role is required")
    if selection["position"] not in options:
        raise ValueError("selected broad role conflicts with 11v11 source position")
    squad = parse_footballsquads(evidence[selection["roster_source"]],
        season=selection_season, club=selection["club"], full_name=selection["full_name"],
        birth_date=selection["birth_date"])
    if squad["position"] != selection["footballsquads_position"]:
        raise ValueError("FootballSquads source position differs from selected row claim")
    if selection["position"] != squad["position"]:
        raise ValueError("selected broad role must agree with FootballSquads source position")
    intervals = [c for c in identity.careers if c["club"] == selection["club"]]
    if len(intervals) != 1:
        raise ValueError("11v11 needs one exact named-club career interval")
    start, end = date.fromisoformat(window["start"]), date.fromisoformat(window["end"])
    career = intervals[0]
    if not (date.fromisoformat(career["joined"]) <= end and date.fromisoformat(career["left"]) >= start):
        raise ValueError("dated 11v11 club interval does not intersect August of target season")
    capture_receipt_path, _ = _workspace_file(evidence[selection["capture_receipt_source"]])
    return {
        "source_person": {"name": identity.full_name, "birth_date": identity.birth_date,
            "source_provider": identity.provider, "source_player_id": identity.provider_player_id,
            "source_profile_url": identity.profile_url},
        "source_player": {"name": identity.full_name, "birth_date": identity.birth_date,
            "position": selection["position"], "nationality": selection["nationality"],
            "nationality_evidence_scope": "11v11-profile-only; FootballSquads row has no nationality column",
            "height_cm": squad['height_cm'], "weight_kg": squad['weight_kg'], "shirt_number": None,
            "fine_roles": [role["code"]],
            "fine_role_provenance": "editorial-compatible-not-source-specific"},
        "native_display_name": selection["native_display_name"],
        "unknown_secondary_fact_policy": {key: 'preserve-existing-mode1'
            for key in ('height_cm', 'weight_kg') if squad[key] is None},
        "published_shirt_number_not_admitted_by_this_writer": squad['shirt_number'],
        "membership": "target-season-11v11-career-interval-and-footballsquads-row-not-matchday-claim",
        "career_interval": career, "football_squads_row": squad,
        "capture_receipt_path": str(capture_receipt_path),
    }


def new_person(selection, evidence, season, club):
    """Compose the existing exchange with explicit source and editorial claims."""
    import copy
    if (selection.get('admission_policy') != POLICY
            or selection.get('season') != season.replace('-', '/')
            or selection.get('club') not in (club['name'], club.get('full_name'))
            or selection.get('name') != selection.get('full_name')
            or selection.get('fine_roles') != [selection.get('editorial_fine_role', {}).get('code')]):
        raise ValueError('11v11 admission must match exact destination season/club/name and editorial role')
    result = admit(selection, evidence)
    keys = {selection[k] for k in ('identity_source', 'capture_receipt_source', 'roster_source')}
    retained = {key: copy.deepcopy(evidence[key]) for key in sorted(keys)}
    person = result['source_person']
    person.update(source_player_id='11v11:' + person['source_player_id'],
        source_profile_sha256=evidence[selection['identity_source']]['sha256'],
        identity_policy=POLICY,
        source_admission={'selection': copy.deepcopy(selection), 'evidence': retained})
    result['raw_evidence'] = dict(status='raw-source-reparsed',
        local_path=evidence[selection['identity_source']]['path'],
        source_sha256=evidence[selection['identity_source']]['sha256'],
        editorial_fine_role=copy.deepcopy(selection['editorial_fine_role']),
        annual_roster_row=result['football_squads_row'],
        nationality_scope='11v11 explicit biography, not the nationality-free annual roster')
    result['opening_date'] = max(selection['membership_window']['start'], result['career_interval']['joined'])
    return result


def person_id(person):
    """Revalidate this provider before issuing its separate stable namespace."""
    admission = person.get('source_admission')
    if person.get('source_provider') != '11v11' or person.get('identity_policy') != POLICY or not isinstance(admission, dict):
        raise ValueError('explicit source-bound 11v11 identity policy required')
    selected = admission['selection']
    club = {'name': selected['club']}
    replay = new_person(selected, admission['evidence'], selected['season'].replace('/', '-'), club)
    if replay['source_person'] != person:
        raise ValueError('11v11 identity differs from its original source admission')
    return 'person-11v11-' + str(selected['provider_player_id'])
