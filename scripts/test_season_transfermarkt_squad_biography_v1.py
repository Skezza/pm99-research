"""Synthetic contract and retained-source tests for the squad-row biography reader."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import season_transfermarkt_squad_biography_v1 as subject


PLAYER_ID = 163589
PLAYER_NAME = "Gary Parkinson"
SQUAD_URL = "https://www.transfermarkt.com/club/kader/verein/466/saison_id/2000/plus/1"
SOCCERBASE_URL = "https://www.soccerbase.com/players/player.sd?player_id=6119"


def _row(*, player_id: int = PLAYER_ID, name: str = PLAYER_NAME,
         birth: str = "10/01/1968 (33)", nation: str = "England",
         position: str = "Right-Back", height: str = "1,80m",
         shirt: str = "12", link_url: str | None = None,
         image_name: str | None = None, extra_profile_links: str = "") -> str:
    href = link_url or f"/{name.lower().replace(' ', '-')}/profil/spieler/{player_id}"
    image_label = image_name if image_name is not None else name
    return f"""<tr class="even">
      <td class="zentriert"><div>{shirt}</div></td>
      <td class="posrela"><table><tbody>
        <tr><td><img alt="{image_label}" title="{image_label}" /></td>
            <td><a href="{href}">{name}</a>{extra_profile_links}</td></tr>
        <tr><td>{position}</td></tr>
      </tbody></table></td>
      <td>{birth}</td>
      <td><img title="{nation}" alt="{nation}" /></td>
      <td>Retired</td><td>{height}</td><td>right</td><td>01/08/1997</td>
      <td>Burnley</td><td>-</td>
    </tr>"""


def _squad(*, rows: str | None = None, title: str = "Preston North End - Detailed squad 00/01",
           canonical: str = "https://www.transfermarkt.com/club/kader/verein/466",
           year: str = "2000", columns: list[str] | None = None) -> bytes:
    columns = columns or subject.HEADERS
    headers = "".join(f"<th>{header}</th>" for header in columns)
    if rows is None:
        rows = _row()
    return f"""<!doctype html><html><head><title>{title}</title>
      <link rel="canonical" href="{canonical}" /></head><body>
      <select name="saison_id"><option value="{year}" selected>{year}</option></select>
      <table class="items"><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>
      </body></html>""".encode()


def _soccerbase(*, name: str = PLAYER_NAME, birthday: str = "10 Jan, 1968") -> bytes:
    return f"""<!doctype html><html><head><title>{name} | Soccerbase</title></head><body>
      <table><tr><th>Real name</th><td>{name}</td></tr>
      <tr><th>Age</th><td>(Born {birthday})</td></tr></table>
      </body></html>""".encode()


def _bind(root: Path, relative: str, raw: bytes, url: str) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "url": url}


@pytest.fixture
def evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict]:
    # The production receipt resolver is deliberately pointed at a temporary
    # workspace so the synthetic test is portable to a clean checkout.
    monkeypatch.setattr(subject.exchange.registry, "ROOT", tmp_path)
    squad = _bind(tmp_path, "squad.html", _squad(), SQUAD_URL)
    witness = _bind(tmp_path, "soccerbase.html", _soccerbase(), SOCCERBASE_URL)
    witness.update({
        "format": "soccerbase-real-name-long-birthday-v1",
        "provider_player_id": 6119,
    })
    value = {"format": subject.FORMAT, **squad, "birth_date_witness": witness}
    return value, witness


def _read(value: dict, *, pid: int = PLAYER_ID, season: str = "2000-01",
          club_name: str = "Preston North End", provider_club_id: int = 466) -> dict:
    return subject.read(value, pid, season=season, club_name=club_name,
                        provider_club_id=provider_club_id)


def test_reads_same_row_biography_and_explicitly_does_not_claim_profile_capture(evidence):
    value, _ = evidence
    result = _read(value)

    assert result == {
        "published_full_name": PLAYER_NAME,
        "published_birth_date": "1968-01-10",
        "published_profile_position": "Right-Back",
        "published_nationality_label": "England",
        "published_height_cm": 180,
        "published_shirt_number": 12,
        "linked_profile_url": "https://www.transfermarkt.com/gary-parkinson/profil/spieler/163589",
        "biography_source_kind": subject.FORMAT,
        "profile_page_captured": False,
    }


def _new_person_case(evidence, tmp_path):
    from scripts import season_dated_reserve_membership_v1 as membership
    value, _ = evidence
    url = 'https://www.skysports.com/football/preston-vs-wimbledon/teams/9988'
    raw = f'''<html><head><link rel="canonical" href="{url}"></head><body>
      <time class="sdc-site-match-header__detail-time" aria-label="3:00pm, Monday 28th August 2000"></time>
      <div class="sdc-site-match-header__team-name-block">Preston North End</div>
      <div class="sdc-site-team-lineup__col">
        <div class="sdc-site-team-lineup__header--main"><img class="sdc-site-team-lineup__team-badge" alt="Preston North End"></div>
        <dl class="sdc-site-team-lineup__players"><dd class="sdc-site-team-lineup__player-name">
          <span class="sdc-site-team-lineup__player-initial" title="Gary">G.</span>
          <span class="sdc-site-team-lineup__player-surname">Parkinson</span>
        </dd></dl></div></body></html>'''.encode()
    fixture = _bind(tmp_path, 'sky.html', raw, url)
    fixture['date'] = '2000-08-28'
    sources = {'squad': value, 'fixture': fixture}
    selection = dict(name=PLAYER_NAME, birth_date='1968-01-10', provider_player_id=PLAYER_ID,
        nationality='ENG', nationality_label='England', position='D', fine_roles=[1],
        profile_position='Right-Back', squad_biography='squad', opening_contract=dict(
            policy=membership.SKY_XI_POLICY, opening_date='2000-08-28', fixture='fixture',
            season_roster='squad', club_name='Preston North End', provider_club_id=466))
    return selection, sources


def test_new_person_binds_row_biography_and_explicit_august_starting_xi(evidence, tmp_path):
    selection, sources = _new_person_case(evidence, tmp_path)
    result = subject.exchange.new_person(selection, sources)
    assert result['source_person']['name'] == PLAYER_NAME
    assert result['source_person']['birth_date'] == '1968-01-10'
    assert result['source_person']['source_profile_url'].endswith('/gary-parkinson/profil/spieler/163589')
    assert result['source_player']['height_cm'] == 180
    assert result['source_player']['shirt_number'] == 12
    assert result['source_player']['weight_kg'] is None
    assert result['raw_evidence']['local_path'] == 'squad.html'
    assert result['raw_evidence']['profile_page_captured'] is False
    assert result['membership'] == 'original-published-August-Sky-starting-XI-not-opening-match-claim'


@pytest.mark.parametrize('fault', ['fake_profile', 'family_heading', 'bench_claim', 'wrong_club', 'wrong_year'])
def test_new_person_row_path_refuses_unsupported_identity_or_membership_claim(evidence, tmp_path, fault):
    from scripts import season_dated_reserve_membership_v1 as membership
    selection, sources = _new_person_case(evidence, tmp_path)
    if fault == 'fake_profile':
        selection['profile'] = 'squad'
    elif fault == 'family_heading':
        selection['native_display_name'] = 'Parkinson'
    elif fault == 'bench_claim':
        selection['opening_contract']['policy'] = membership.SKY_POLICY
    elif fault == 'wrong_club':
        selection['opening_contract']['club_name'] = 'Different Club'
    else:
        selection['opening_contract']['opening_date'] = '2001-08-28'
    with pytest.raises(ValueError):
        subject.exchange.new_person(selection, sources)


def test_cross_row_birthday_and_nationality_are_not_joined_to_target(evidence, tmp_path: Path):
    value, _ = evidence
    decoy = _row(player_id=163588, name="Other Player", birth="01/10/1970 (30)",
                 nation="Scotland", position="Centre-Back", height="1,90m", shirt="4")
    raw = _squad(rows=decoy + _row())
    path = Path(subject.exchange.registry.ROOT) / value["path"]
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()

    result = _read(value)
    assert result["published_birth_date"] == "1968-01-10"
    assert result["published_nationality_label"] == "England"
    assert result["published_profile_position"] == "Right-Back"
    assert result["published_shirt_number"] == 12


@pytest.mark.parametrize(("field", "replacement", "kwargs"), [
    ("url", "https://www.transfermarkt.com/club/kader/verein/466/saison_id/2001/plus/1", {}),
    ("url", "https://www.transfermarkt.com/club/kader/verein/467/saison_id/2000/plus/1", {}),
    ("url", "https://evil.example/club/kader/verein/466/saison_id/2000/plus/1", {}),
    ("url", "https://www.transfermarkt.com/club/kader/verein/466/saison_id/2000/plus/1?foo=1", {}),
    ("url", "https://www.transfermarkt.com/club/kader/verein/466/saison_id/2000/plus/1", {"season": "2001-02"}),
    ("url", "https://www.transfermarkt.com/club/kader/verein/466/saison_id/2000/plus/1", {"club_name": "Blackpool"}),
    ("url", "https://www.transfermarkt.com/club/kader/verein/466/saison_id/2000/plus/1", {"provider_club_id": 467}),
])
def test_rejects_wrong_year_club_host_or_route_context(evidence, tmp_path: Path, field, replacement, kwargs):
    value, _ = evidence
    if kwargs:
        value["url"] = replacement
    else:
        value[field] = replacement
    with pytest.raises(ValueError):
        _read(value, **kwargs)


@pytest.mark.parametrize("canonical", [
    "https://www.transfermarkt.com/club/kader/verein/467",
    "https://evil.example/club/kader/verein/466",
    "https://www.transfermarkt.com/club/kader/verein/466?saison_id=2001",
])
def test_rejects_wrong_canonical_club_origin_or_query(evidence, canonical):
    value, _ = evidence
    raw = _squad(canonical=canonical)
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="context"):
        _read(value)


def test_rejects_wrong_selected_year_and_wrong_title_club(evidence):
    value, _ = evidence
    path = subject.exchange.original(value)
    for raw in (_squad(year="2001"), _squad(title="Blackpool - Detailed squad 00/01")):
        path.write_bytes(raw)
        value["sha256"] = hashlib.sha256(raw).hexdigest()
        with pytest.raises(ValueError, match="context"):
            _read(value)


@pytest.mark.parametrize("bad_id", ["1635890", "0163589", "0", "abc"])
def test_rejects_prefix_or_malformed_player_ids(evidence, bad_id):
    value, _ = evidence
    raw = _squad(rows=_row(link_url=f"/gary-parkinson/profil/spieler/{bad_id}"))
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        _read(value)


def test_rejects_multiple_target_rows(evidence):
    value, _ = evidence
    raw = _squad(rows=_row() + _row())
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="one exact"):
        _read(value)


def test_rejects_conflicting_or_duplicate_profile_links_in_target_row(evidence):
    value, _ = evidence
    extra = '<a href="/gary-parkinson-copy/profil/spieler/163590">Gary Parkinson</a>'
    raw = _squad(rows=_row(extra_profile_links=extra))
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="identity"):
        _read(value)

    # A duplicated exact ID is also ambiguous even when set-based ID checks
    # would otherwise collapse both links to the same numeric value.
    extra = '<a href="/gary-parkinson-copy/profil/spieler/163589">Gary Parkinson</a>'
    raw = _squad(rows=_row(extra_profile_links=extra))
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        _read(value)


@pytest.mark.parametrize("name,image_name", [
    ("Gary P. Parkinson", "Gary P. Parkinson"),
    (PLAYER_NAME, "Derek Collins"),
])
def test_rejects_name_or_image_identity_mismatch(evidence, name, image_name):
    value, _ = evidence
    raw = _squad(rows=_row(name=name, image_name=image_name))
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        _read(value)


@pytest.mark.parametrize("birth", ["", "10/01/68 (33)", "32/01/1968 (33)", "10-01-1968 (33)"])
def test_rejects_malformed_or_missing_row_birthday(evidence, birth):
    value, _ = evidence
    raw = _squad(rows=_row(birth=birth))
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        _read(value)


def test_rejects_independent_birthday_conflict(evidence):
    value, witness = evidence
    raw = _soccerbase(birthday="1 Oct, 1968")
    path = subject.exchange.original(witness)
    path.write_bytes(raw)
    witness["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="disagrees"):
        _read(value)


def test_rejects_shifted_squad_columns(evidence):
    value, _ = evidence
    columns = list(subject.HEADERS)
    columns[2], columns[3] = columns[3], columns[2]
    raw = _squad(columns=columns)
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="column contract"):
        _read(value)


def test_empty_body_is_rejected_but_empty_optional_height_is_none(evidence):
    value, _ = evidence
    path = subject.exchange.original(value)
    raw = b""
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        _read(value)

    raw = _squad(rows=_row(height=""))
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    assert _read(value)["published_height_cm"] is None


def test_rejects_malformed_nonempty_height(evidence):
    value, _ = evidence
    raw = _squad(rows=_row(height="180 cm"))
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="height"):
        _read(value)


@pytest.mark.parametrize("link", [
    "https://evil.example/gary-parkinson/profil/spieler/163589",
    "http://www.transfermarkt.com/gary-parkinson/profil/spieler/163589",
])
def test_rejects_profile_link_with_untrusted_origin(evidence, link):
    value, _ = evidence
    raw = _squad(rows=_row(link_url=link))
    path = subject.exchange.original(value)
    path.write_bytes(raw)
    value["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="origin"):
        _read(value)


def test_retained_gary_parkinson_row_and_soccerbase_birthday_when_available():
    root = Path(__file__).resolve().parents[1]
    squad_path = root / ".local/external-sources/historical-detailed-roles-v1/2000-01/squad/2000/eng/466.html"
    witness_path = root / ".local/consolidated-audit-20261009/Collins2000-opening-review-v1/source/source-cache-v1/blobs/c6/c6850f43e28ad80fc36a4b061a33d92744eee2aeaef4a91a0df7a662cfb7da8e"
    if not squad_path.is_file() or not witness_path.is_file():
        pytest.skip("retained original Transfermarkt/Soccerbase source captures are not present")
    squad_sha = "f627357fa826922036b177bceafa4c876582695971483ac742bcfad5ef66d9e6"
    witness_sha = "c6850f43e28ad80fc36a4b061a33d92744eee2aeaef4a91a0df7a662cfb7da8e"
    squad = {"format": subject.FORMAT, "path": squad_path.relative_to(root).as_posix(),
             "sha256": squad_sha, "url": SQUAD_URL}
    witness = {"format": "soccerbase-real-name-long-birthday-v1",
               "path": witness_path.relative_to(root).as_posix(), "sha256": witness_sha,
               "url": SOCCERBASE_URL, "provider_player_id": 6119}
    assert hashlib.sha256(squad_path.read_bytes()).hexdigest() == squad_sha
    assert hashlib.sha256(witness_path.read_bytes()).hexdigest() == witness_sha

    result = subject.read({**squad, "birth_date_witness": witness}, PLAYER_ID,
                          season="2000-01", club_name="Preston North End", provider_club_id=466)
    assert result["published_full_name"] == PLAYER_NAME
    assert result["published_birth_date"] == "1968-01-10"
    assert result["published_profile_position"] == "Right-Back"
    assert result["published_nationality_label"] == "England"
    assert result["published_height_cm"] == 180
    assert result["published_shirt_number"] == 12
    assert result["linked_profile_url"] == "https://www.transfermarkt.com/gary-parkinson/profil/spieler/163589"
    assert result["profile_page_captured"] is False
