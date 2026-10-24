"""Focused source-admission tests for known-wrong player fact adjudication."""

import copy
import hashlib
import json
from datetime import date
from pathlib import Path
import re

import pytest
from bs4 import BeautifulSoup

from app.fdi_indexed import IndexedFDIFile
from scripts import season_adjudicated_player_facts_v1 as subject
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_source_package_builder_v1 as builder
from scripts import season_source_verified_player_changes_v1 as changes
from scripts.season_historical_roster_audit_v1 import native_player
from scripts.season_within_club_reserve_repair_v1 import native_facts


ROOT = Path(__file__).resolve().parents[1]
WITNESS_PATH = ROOT / ".local/consolidated-audit-20261009/Scotland2000-label-manager-v1/larsson-facts/adjudicated-witness-v1.json"


@pytest.fixture
def witness():
    if not WITNESS_PATH.is_file():
        pytest.skip('retained original-source witness unavailable')
    return json.loads(WITNESS_PATH.read_text(encoding="utf-8"))


def test_retained_witness_reproduces_adjudicated_facts(witness):
    assert subject.adjudicate(witness) == {
        "birth_date": "1971-09-20",
        "nationality": "SWE",
    }


def test_country_code_must_match_published_country_literal(witness):
    """A source's literal 'Sweden' must not be relabelable as another valid code."""
    forged = copy.deepcopy(witness)
    forged["values"]["nationality"] = "ENG"
    forged["official_sources"][0]["nationality"]["code"] = "ENG"

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


def test_historical_provider_id_is_not_replaceable_by_matching_name_or_old_dob(witness):
    forged = copy.deepcopy(witness)
    forged["historical_identity"]["provider_player_id"] = 3515

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


@pytest.mark.parametrize("field", ["source_row_sha256", "preallocation_sha256", "match_sha256"])
def test_historical_identity_requires_exact_source_hashes(witness, field):
    """Hashes bind the historical row and original source bodies; a name/DOB is not enough."""
    forged = copy.deepcopy(witness)
    if field == "source_row_sha256":
        forged["historical_identity"][field] = "0" * 64
    elif field == "preallocation_sha256":
        forged["historical_identity"]["preallocation"]["sha256"] = "0" * 64
    else:
        forged["historical_identity"]["match"]["sha256"] = "0" * 64

    with pytest.raises((ValueError, OSError)):
        subject.adjudicate(forged)


def test_historical_person_id_must_be_derived_from_bound_source_row(witness):
    forged = copy.deepcopy(witness)
    forged["person_id"] = "person-source-" + "0" * 64

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


def _diacritic_identity_fixture(tmp_path, monkeypatch, witness):
    """Exercise the full source-row/fixture chain with one transliterated label."""
    synthetic = copy.deepcopy(witness)
    historical = synthetic["historical_identity"]
    source_path = ROOT / historical["preallocation"]["path"]
    preallocation = json.loads(source_path.read_text(encoding="utf-8"))
    matches = [(club, row) for club in preallocation["source_clubs"] for row in club["players"]
               if row.get("source_row_sha256") == historical["source_row_sha256"]]
    assert len(matches) == 1
    club, row = matches[0]
    row["facts"]["name"] = "Henrik Tokić"
    row_hash = hashlib.sha256(b"synthetic exact original row for name-key test").hexdigest()
    row["source_row_sha256"] = row_hash
    historical["source_row_sha256"] = row_hash
    historical["preallocation"]["path"] = "synthetic/preallocation.json"
    historical["match"]["path"] = "synthetic/match.html"
    synthetic["full_name"] = "Henrik Tokić"
    synthetic["person_id"] = builder._source_person_id(row)

    report_path = ROOT / historical["match"]["path"]
    original_report = ROOT / witness["historical_identity"]["match"]["path"]
    page = BeautifulSoup(original_report.read_bytes(), "lxml")
    provider_id = str(historical["provider_player_id"])
    person_links = [a for a in page.select("a[href]")
                    if re.search(r"/spieler/" + re.escape(provider_id) + r"(?:/|$)", a["href"])]
    assert person_links
    for link in person_links:
        link["title"] = "Henrik Tokic"

    preallocation_path = tmp_path / "preallocation.json"
    report_path = tmp_path / "match.html"
    preallocation_path.write_text(json.dumps(preallocation), encoding="utf-8")
    report_path.write_text(str(page), encoding="utf-8")
    bindings = {
        "synthetic/preallocation.json": preallocation_path,
        "synthetic/match.html": report_path,
    }

    def original(binding):
        path = bindings[binding["path"]]
        if hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError("synthetic source binding hash differs")
        return path

    historical["preallocation"]["sha256"] = hashlib.sha256(preallocation_path.read_bytes()).hexdigest()
    historical["match"]["sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    monkeypatch.setattr(exchange, "original", original)
    return synthetic, person_links


def test_historical_identity_accepts_complete_diacritic_transliteration(tmp_path, monkeypatch, witness):
    synthetic, _links = _diacritic_identity_fixture(tmp_path, monkeypatch, witness)

    assert subject.verify_historical_identity(synthetic) == synthetic["historical_identity"]["provider_player_id"]


@pytest.mark.parametrize("reported_name", ["H. Tokic", "Tokic", "Henri Tokic"])
def test_historical_identity_rejects_initial_surname_only_and_different_full_name(
        tmp_path, monkeypatch, witness, reported_name):
    synthetic, links = _diacritic_identity_fixture(tmp_path, monkeypatch, witness)
    match_path = tmp_path / "match.html"
    page = BeautifulSoup(match_path.read_bytes(), "lxml")
    provider_id = str(synthetic["historical_identity"]["provider_player_id"])
    links = [a for a in page.select("a[href]")
             if re.search(r"/spieler/" + re.escape(provider_id) + r"(?:/|$)", a["href"])]
    for link in links:
        link["title"] = reported_name
    match_path.write_text(str(page), encoding="utf-8")
    synthetic["historical_identity"]["match"]["sha256"] = hashlib.sha256(match_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="full identity"):
        subject.verify_historical_identity(synthetic)


def test_historical_identity_still_rejects_wrong_provider_id_and_source_binding(
        tmp_path, monkeypatch, witness):
    synthetic, _links = _diacritic_identity_fixture(tmp_path, monkeypatch, witness)
    wrong_id = copy.deepcopy(synthetic)
    wrong_id["historical_identity"]["provider_player_id"] += 1
    with pytest.raises(ValueError):
        subject.verify_historical_identity(wrong_id)

    wrong_binding = copy.deepcopy(synthetic)
    wrong_binding["historical_identity"]["preallocation"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash differs"):
        subject.verify_historical_identity(wrong_binding)


def _title_free_slug_fixture(tmp_path, monkeypatch, witness, slug='henrik-tokic', *, origin=None):
    synthetic, _links = _diacritic_identity_fixture(tmp_path, monkeypatch, witness)
    match_path = tmp_path / "match.html"
    page = BeautifulSoup(match_path.read_bytes(), "lxml")
    provider_id = str(synthetic["historical_identity"]["provider_player_id"])
    links = [a for a in page.select("a[href]")
             if re.search(r"/spieler/" + re.escape(provider_id) + r"(?:/|$)", a["href"])]
    assert links
    for link in links:
        link.attrs.pop("title", None)
        suffix = "/profil/spieler/" + provider_id
        if "/leistungsdatendetails/spieler/" in link["href"]:
            suffix = "/leistungsdatendetails/spieler/" + provider_id
        link["href"] = (origin.rstrip("/") if origin else "") + "/" + slug + suffix
    match_path.write_text(str(page), encoding="utf-8")
    synthetic["historical_identity"]["match"]["sha256"] = hashlib.sha256(match_path.read_bytes()).hexdigest()
    return synthetic, match_path


def test_historical_identity_accepts_full_name_slug_when_numeric_links_have_no_titles(
        tmp_path, monkeypatch, witness):
    synthetic, _ = _title_free_slug_fixture(tmp_path, monkeypatch, witness)
    assert subject.verify_historical_identity(synthetic) == synthetic["historical_identity"]["provider_player_id"]


@pytest.mark.parametrize("slug", ["tokic", "h-tokic", "henri-tokic", "unknown"])
def test_historical_identity_rejects_missing_surname_initial_or_different_slug(
        tmp_path, monkeypatch, witness, slug):
    synthetic, _ = _title_free_slug_fixture(tmp_path, monkeypatch, witness, slug)
    with pytest.raises(ValueError, match="full identity"):
        subject.verify_historical_identity(synthetic)


def test_historical_identity_does_not_use_good_slug_to_override_contradictory_title(
        tmp_path, monkeypatch, witness):
    synthetic, match_path = _title_free_slug_fixture(tmp_path, monkeypatch, witness)
    page = BeautifulSoup(match_path.read_bytes(), "lxml")
    provider_id = str(synthetic["historical_identity"]["provider_player_id"])
    links = [a for a in page.select("a[href]")
             if re.search(r"/spieler/" + re.escape(provider_id) + r"(?:/|$)", a["href"])]
    for link in links:
        link["title"] = "Henri Tokic"
    match_path.write_text(str(page), encoding="utf-8")
    synthetic["historical_identity"]["match"]["sha256"] = hashlib.sha256(match_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        subject.verify_historical_identity(synthetic)


def test_historical_identity_rejects_nonapproved_match_or_slug_origins(tmp_path, monkeypatch, witness):
    synthetic, match_path = _title_free_slug_fixture(
        tmp_path, monkeypatch, witness, origin="https://evil.example")
    with pytest.raises(ValueError):
        subject.verify_historical_identity(synthetic)

    synthetic, _ = _title_free_slug_fixture(tmp_path, monkeypatch, witness)
    synthetic["historical_identity"]["match"]["url"] = synthetic["historical_identity"]["match"]["url"].replace(
        "www.transfermarkt.co.uk", "evil.example")
    with pytest.raises(ValueError, match="fixture URL/ID"):
        subject.verify_historical_identity(synthetic)


@pytest.mark.parametrize('origin', ['http://www.transfermarkt.com', 'javascript:', 'file:'])
def test_title_free_full_name_slug_rejects_non_https_schemes(tmp_path, monkeypatch, witness, origin):
    synthetic, _ = _title_free_slug_fixture(tmp_path, monkeypatch, witness, origin=origin)
    with pytest.raises(ValueError):
        subject.verify_historical_identity(synthetic)


def test_historical_identity_rejects_changed_match_source_hash(tmp_path, monkeypatch, witness):
    synthetic, _ = _title_free_slug_fixture(tmp_path, monkeypatch, witness)
    synthetic["historical_identity"]["match"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash differs"):
        subject.verify_historical_identity(synthetic)


def test_published_birthdays_must_agree_with_adjudicated_date(witness):
    forged = copy.deepcopy(witness)
    forged["values"]["birth_date"] = "1971-09-10"

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


def test_claimed_source_date_must_be_present_in_that_original_body(witness):
    forged = copy.deepcopy(witness)
    forged["official_sources"][1]["birth_date"]["literal"] = "10/09/1971"

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


def _prepared_2000_case():
    path = ROOT / ".local/consolidated-audit-20261009/Scotland2000-label-manager-v1/larsson-facts/2000-01-adjudicated-input-v1.json"
    if not path.is_file():
        pytest.skip("retained 2000-01 adjudication input is unavailable")
    request = json.loads(path.read_text(encoding="utf-8"))
    base = registry.load_registered_release(request["season"], request["release_id"])
    return base, path, request, changes.prepare(base, path)


def test_native_postreadback_matches_adjudicated_recipe_and_country():
    base, _path, _request, plan = _prepared_2000_case()
    original_jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    original_eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()

    updated_jug, updated_eq = changes.apply(original_jug, original_eq, plan)

    assert updated_eq == original_eq
    codes = compiler._extract_country_codes_from_textos(base.game_path / "DBDAT/TEXTOS.PKF")
    country_code = compiler._country_code("SWE", codes)
    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(updated_jug).entries}
    for row in plan["updates"]:
        carrier = row["carrier_id"]
        assert native_facts(updated_jug, carrier)["birth_date"] == row["values"]["birth_date"]
        raw = entries[carrier].decode_payload(updated_jug)
        end = row["native_masks"][0]["record_offset"]
        assert raw[end] ^ 0x61 == country_code

    allowed = {
        mask["file_offset"]
        for row in plan["updates"]
        for mask in row["native_masks"]
        if mask["before"] != mask["after"]
    }
    changed = {
        index for index, (before, after) in enumerate(zip(original_jug, updated_jug))
        if before != after
    }
    assert changed == allowed


def test_native_writer_rejects_a_mixed_preimage():
    base, _path, _request, plan = _prepared_2000_case()
    original_jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    original_eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    updated_jug, _ = changes.apply(original_jug, original_eq, plan)
    changed_mask = next(
        mask for row in plan["updates"] for mask in row["native_masks"]
        if mask["before"] != mask["after"]
    )
    mixed = bytearray(original_jug)
    mixed[changed_mask["file_offset"]] = updated_jug[changed_mask["file_offset"]]

    with pytest.raises(ValueError, match="exact complete pre/postimages"):
        changes.apply(bytes(mixed), original_eq, plan)


def _prepare_dob_only_larsson():
    base, path, request, _ = _prepared_2000_case()
    request = copy.deepcopy(request)
    assert len(request['changes']) == 1
    row = request['changes'][0]
    row['field_mask'] = ['birth_date']
    row['witness']['values'] = {'birth_date': row['witness']['values']['birth_date']}
    return base, path, request, subject.prepare(base, path, request)


def test_birth_date_only_replay_masks_all_four_date_bytes_and_preserves_country_and_eq():
    base, _path, request, plan = _prepare_dob_only_larsson()
    row = plan['updates'][0]
    carrier = row['carrier_id']
    before_jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    before_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    package_hash = registry.sha256_file(base.package_path)
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(before_jug).entries}
    original_payload = entries[carrier].decode_payload(before_jug)
    name_end = native_player(original_payload, carrier)['name_end']
    country_before = original_payload[name_end + 8] ^ 0x61
    expected_birth = date.fromisoformat(row['values']['birth_date'])
    expected_date_bytes = [expected_birth.day, expected_birth.month,
                           *expected_birth.year.to_bytes(2, 'little')]

    assert row['field_mask'] == ['birth_date']
    assert row['values'] == {'birth_date': request['changes'][0]['witness']['values']['birth_date']}
    assert len(row['native_masks']) == 4
    assert [mask['record_offset'] for mask in row['native_masks']] == [
        name_end + 12, name_end + 13, name_end + 14, name_end + 15,
    ]
    assert [mask['after'] for mask in row['native_masks']] == expected_date_bytes

    # The retained request on disk remains the original DOB+country request;
    # this opt-in DOB-only request is deliberately ephemeral. Validate and
    # replay its exact masks without asking apply() to re-open that different
    # immutable source request.
    subject.validate_mask(plan)
    after_jug = bytearray(before_jug)
    for mask in row['native_masks']:
        after_jug[mask['file_offset']] = mask['after']
    after_jug = bytes(after_jug)
    after_eq = before_eq
    after_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(after_jug).entries}
    after_payload = after_entries[carrier].decode_payload(after_jug)
    assert after_eq == before_eq
    assert after_payload[name_end + 8] ^ 0x61 == country_before
    assert native_facts(after_jug, carrier)['birth_date'] == row['values']['birth_date']
    allowed = {mask['file_offset'] for mask in row['native_masks']
               if mask['before'] != mask['after']}
    actual = {i for i, (before, after) in enumerate(zip(before_jug, after_jug)) if before != after}
    assert actual == allowed
    assert registry.sha256_file(base.package_path) == package_hash


def test_existing_birthday_and_nationality_mask_remains_accepted_unchanged():
    base, path, request, _ = _prepared_2000_case()
    plan = subject.prepare(base, path, request)
    row = plan['updates'][0]

    assert row['field_mask'] == ['birth_date', 'nationality']
    assert row['values'] == {
        'birth_date': '1971-09-20',
        'nationality': 'SWE',
    }
    assert len(row['native_masks']) == 5
    start = row['native_masks'][0]['record_offset']
    assert [mask['record_offset'] - start for mask in row['native_masks']] == [0, 4, 5, 6, 7]


@pytest.mark.parametrize(('field_mask', 'value_fields'), [
    (['birth_date', 'nationality', 'height_cm'], {'birth_date'}),
    (['birth_date', 'nationality'], {'birth_date'}),
    (['nationality'], {'birth_date'}),
    (['birth_date'], {'birth_date', 'nationality'}),
    (['birth_date', 'birth_date'], {'birth_date'}),
])
def test_birth_date_only_admission_rejects_malformed_or_expanded_masks(field_mask, value_fields):
    base, path, request, _ = _prepared_2000_case()
    request = copy.deepcopy(request)
    row = request['changes'][0]
    row['field_mask'] = field_mask
    row['witness']['values'] = {
        key: value for key, value in row['witness']['values'].items() if key in value_fields
    }

    with pytest.raises(ValueError):
        subject.prepare(base, path, request)


def test_birth_date_only_admission_rejects_invalid_calendar_date():
    base, path, request, _ = _prepared_2000_case()
    request = copy.deepcopy(request)
    row = request['changes'][0]
    row['field_mask'] = ['birth_date']
    row['witness']['values'] = {'birth_date': '1971-02-29'}

    with pytest.raises(ValueError):
        subject.prepare(base, path, request)


def test_birth_date_only_plan_rejects_missing_or_extra_native_masks():
    _base, _path, _request, plan = _prepare_dob_only_larsson()
    missing = copy.deepcopy(plan)
    missing['updates'][0]['native_masks'].pop()
    with pytest.raises(ValueError):
        subject.validate_mask(missing)

    expanded = copy.deepcopy(plan)
    expanded_row = expanded['updates'][0]
    expanded_row['field_mask'] = ['birth_date', 'nationality']
    expanded_row['values'] = {'birth_date': '1971-09-20', 'nationality': 'SWE'}
    expanded_row['witness']['values'] = dict(expanded_row['values'])
    with pytest.raises(ValueError):
        subject.validate_mask(expanded)


@pytest.mark.parametrize('claim', [
    {'literal': '1989', 'format': '%Y'},
    {'literal': 'April 1989', 'format': '%B %Y'},
    {'literal': '19 April', 'format': '%d %B'},
    {'literal': '19 April 89', 'format': '%d %B %y'},
])
def test_secondary_birthday_cannot_invent_missing_date_components(claim):
    with pytest.raises(ValueError, match='precise day'):
        subject._literal_day_birthday(claim)


def test_ordinal_official_birthday_preserves_day_month_and_full_year():
    assert subject._literal_day_birthday({'literal': '19th April, 1989',
                                          'format': '%dth %B, %Y'}) == '1989-04-19'


@pytest.fixture
def independent_witness(tmp_path, monkeypatch):
    monkeypatch.setattr(subject, 'verify_historical_identity', lambda witness: 77)
    def checked(bound):
        path = Path(bound['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != bound['sha256']:
            raise ValueError('test-bound source changed')
        return path
    monkeypatch.setattr(subject, 'checked', checked)
    sources = []
    for n, publisher in enumerate(['official_club_or_association_bio', 'independent_named_reference']):
        raw = b'<article><h1>Example Person</h1><p>Example Town</p><p>Born 19 April 1989</p></article>'
        body = tmp_path / f'{n}.html'
        body.write_bytes(raw)
        url = f'https://source{n}.example/player'
        digest = hashlib.sha256(raw).hexdigest()
        receipt = tmp_path / f'{n}.json'
        receipt.write_text(json.dumps({'url': url, 'raw_sha256': digest}))
        sources.append({'url': url, 'path': str(body), 'sha256': digest,
            'receipt': {'path': str(receipt), 'sha256': hashlib.sha256(receipt.read_bytes()).hexdigest()},
            'publisher_class': publisher, 'identity_anchors': ['Example Town'],
            'birth_date': {'context': 'Born 19 April 1989', 'label': 'Born',
                           'literal': '19 April 1989', 'format': '%d %B %Y'}})
    return {'full_name': 'Example Person', 'values': {'birth_date': '1989-04-19'},
            'independent_sources': sources}


def test_official_and_reference_sources_keep_their_distinct_publisher_classes(independent_witness):
    assert subject.adjudicate(independent_witness) == {'birth_date': '1989-04-19'}


def test_two_references_cannot_be_claimed_as_official_corroboration(independent_witness):
    independent_witness['independent_sources'][0]['publisher_class'] = 'independent_named_reference'
    with pytest.raises(ValueError, match='official club'):
        subject.adjudicate(independent_witness)


def test_reference_sidebar_name_cannot_identify_another_subjects_birthday(independent_witness):
    item = independent_witness['independent_sources'][1]
    path = Path(item['path'])
    path.write_text('<h1>Different Person</h1><aside>Example Person</aside><p>Example Town</p><p>Born 19 April 1989</p>')
    item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = Path(item['receipt']['path'])
    receipt.write_text(json.dumps({'url': item['url'], 'raw_sha256': item['sha256']}))
    item['receipt']['sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='subject heading'):
        subject.adjudicate(independent_witness)


def test_independent_reference_cannot_smuggle_an_unadmitted_country_change(independent_witness):
    independent_witness['values']['nationality'] = 'ENG'
    with pytest.raises(ValueError, match='unsupported fields'):
        subject.adjudicate(independent_witness)


def test_two_source_classes_cannot_share_one_publisher_host(independent_witness):
    independent_witness['independent_sources'][1]['url'] = independent_witness['independent_sources'][0]['url']
    with pytest.raises(ValueError, match='distinct hosts'):
        subject.adjudicate(independent_witness)


def test_correct_page_subject_cannot_borrow_a_nested_other_players_birthday(independent_witness):
    item = independent_witness['independent_sources'][1]
    path = Path(item['path'])
    path.write_text('<article><h1>Example Person</h1><p>Example Town</p>'
                    '<section><h3>Other Player</h3><p>Born 19 April 1989</p></section></article>')
    item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = Path(item['receipt']['path'])
    receipt.write_text(json.dumps({'url': item['url'], 'raw_sha256': item['sha256']}))
    item['receipt']['sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='another subject heading'):
        subject.adjudicate(independent_witness)
