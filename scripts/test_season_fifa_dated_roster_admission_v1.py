import copy
import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import season_fifa_dated_roster_admission_v1 as admission
from scripts import season_release_registry_v1 as registry


@pytest.fixture
def sample(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    row = dict(player_id='100', player_url='/player/100/sample-player/180002',
               fifa_version='18', fifa_update_date='2017-09-18',
               short_name='S. Player',
               long_name='Sample Middle Player', dob='1990-01-02',
               player_positions='CB', nationality_name='Scotland', height_cm='190', weight_kg='80')
    row.update({column: '55' for column in admission.ratings.MAPPING.values()})
    row['goalkeeping_handling'] = '12'
    fifa = tmp_path / 'fifa.csv'
    pdf = tmp_path / 'roster.pdf'
    pdf.write_bytes(b'\n\n%PDF-1.5\nretained-pdf-fixture')
    def write_rows(rows):
        with fifa.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row))
            writer.writeheader()
            writer.writerows(rows)
    write_rows([row])
    evidence = dict(
        fifa=dict(path='fifa.csv', sha256=registry.sha256_file(fifa)),
        roster=dict(path='roster.pdf', sha256=registry.sha256_file(pdf),
                    url='https://premierleague-static-files.s3.amazonaws.com/premierleague/document/2017/08/11/id/squad.pdf'))
    selection = dict(admission_policy=admission.POLICY, name=row['long_name'], birth_date=row['dob'],
                     fifa_player_id='100', fifa_source='fifa', roster_source='roster',
                     roster_date='2017-08-11', club_name='Sample United',
                     native_display_name='Sample Player', position='D', fine_roles=[4], nationality='SCO')
    text = ('The Premier League\nNOTIFICATION OF SHIRT NUMBERS : Sample United\n'
            '36 Player, Sample\n\fThe Premier League\n'
            'NOTIFICATION OF SHIRT NUMBERS : Other Club\n31 Other, Person\n')
    monkeypatch.setattr(admission.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=text))
    return selection, evidence, row, write_rows


def admit(sample):
    selection, evidence, *_ = sample
    return admission.new_person(selection, evidence, '2017-18', {'name': 'Sample United'})


def test_period_fifa_and_official_roster_have_distinct_identity_membership_proofs(sample):
    result = admit(sample)
    assert admission.person_id(result['source_person']) == 'person-fifa-100'
    assert result['source_player']['name'] == 'Sample Middle Player'
    assert result['raw_evidence']['published_display_name'] == 'Sample Player'
    assert result['raw_evidence']['fine_roles'] == [4]
    assert result['source_player']['nationality'] == 'SCO'
    assert result['source_player']['shirt_number'] == 36
    assert result['raw_evidence']['fifa_values']['handling'] == 12
    assert 'not-matchday-or-opening-XI-claim' in result['membership']


@pytest.mark.parametrize('field,value', [
    ('birth_date', '1991-01-02'), ('fifa_player_id', '101'),
    ('fine_roles', [13]), ('position', 'F'), ('nationality', 'ENG'),
    ('roster_date', '2018-08-11'), ('native_display_name', 'S. Player'),
    ('club_name', 'Other Club'), ('admission_policy', 'unreviewed-policy'),
])
def test_wrong_identity_period_role_country_or_roster_is_refused(sample, field, value):
    sample[0][field] = value
    with pytest.raises(ValueError):
        admit(sample)


def test_wrong_roster_publisher_is_not_an_official_membership_witness(sample):
    sample[1]['roster']['url'] = sample[1]['roster']['url'].replace('s3.amazonaws.com', 'example.com')
    with pytest.raises(ValueError, match='publisher and date'):
        admit(sample)


def test_rehashed_same_name_dob_namesakes_still_require_unique_fifa_identity(sample):
    _, evidence, row, write_rows = sample
    write_rows([row, {**row, 'player_id': '101'}])
    evidence['fifa']['sha256'] = registry.sha256_file(registry.ROOT / 'fifa.csv')
    with pytest.raises(ValueError, match='ambiguous'):
        admit(sample)


def test_changed_original_bytes_cannot_be_hidden_by_cached_edition_rows(sample):
    admit(sample)
    path = registry.ROOT / 'fifa.csv'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='path/hash changed'):
        admit(sample)


def test_published_shorter_name_does_not_choose_between_different_middle_name_namesakes(sample):
    _, evidence, row, write_rows = sample
    write_rows([row, {**row, 'player_id': '101', 'long_name': 'Sample Another Player'}])
    evidence['fifa']['sha256'] = registry.sha256_file(registry.ROOT / 'fifa.csv')
    with pytest.raises(ValueError, match='ambiguous FIFA identities'):
        admit(sample)


def test_move_uses_only_the_literal_published_short_name(sample):
    selection, evidence, *_ = sample
    actor = dict(source_name=selection['name'], facts=dict(birth_date=selection['birth_date']))
    result = admission.published_move_display(actor,
        dict(fifa_player_id='100', fifa_source='fifa'), evidence, '2017-18')
    assert result['display_name'] == 'S. Player'
    with pytest.raises(ValueError):
        admission.published_move_display(actor,
            dict(fifa_player_id='100', fifa_source='fifa', display_name='An invented name'), evidence, '2017-18')


def test_fifa_person_namespace_cannot_claim_a_transfermarkt_identity(sample):
    person = admit(sample)['source_person']
    forged = copy.deepcopy(person)
    forged['source_profile_url'] = 'https://www.transfermarkt.com/player/profil/spieler/100'
    with pytest.raises(ValueError, match='does not reproduce'):
        admission.person_id(forged)


def test_roster_pdf_header_rejects_non_pdf_bytes(sample):
    pdf = registry.ROOT / 'roster.pdf'
    pdf.write_bytes(b'<html>not an official PDF</html>')
    sample[1]['roster']['sha256'] = registry.sha256_file(pdf)
    with pytest.raises(ValueError, match='not a PDF'):
        admit(sample)


@pytest.fixture
def biography(tmp_path, monkeypatch):
    from scripts import season_opening_identity_exchange_v1 as exchange
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    path = tmp_path / 'original.html'
    path.write_text('<article><h1>Example Person er klar for Molde FK</h1>'
                    '<p>Example Person (f.26. februar 1991, Akranes Island)</p></article>')
    source = dict(path='original.html', sha256=registry.sha256_file(path),
                  url='https://www.moldefk.no/nyheter/example-person')
    actor = dict(source_name='Example Person', facts=dict(birth_date='1991-12-26'))
    claim = dict(format='norwegian-club-named-parenthetical-birthday-v1',
                 evidence_key='biography', birth_date='1991-02-26')
    return exchange, actor, claim, {'biography': source}, path


def test_named_biography_corrects_only_the_explicit_birth_date(biography):
    exchange, actor, claim, evidence, _ = biography
    before = copy.deepcopy(actor)
    result = exchange.official_biography_birth_date(actor, claim, evidence)
    assert (result['before'], result['after']) == ('1991-12-26', '1991-02-26')
    assert actor == before


def test_displaced_unknown_birth_date_is_logged_as_slot_preimage_not_person_fact():
    from scripts.season_opening_identity_exchange_v1 import omitted_slot_birth_date_preimage
    actor = dict(carrier_id=10, facts=dict(birth_date={'policy': 'preserve-existing-mode1'}))
    result = omitted_slot_birth_date_preimage(actor, {'birth_date': '1976-10-02'}, {11, 12})
    assert result['native_slot_birth_date'] == '1976-10-02'
    assert result['historical_birth_date_verified'] is False
    assert omitted_slot_birth_date_preimage(actor, {'birth_date': '1976-10-02'}, {10}) is None
    actor['facts']['birth_date'] = '1991-01-01'
    assert omitted_slot_birth_date_preimage(actor, {'birth_date': '1976-10-02'}, set()) is None
    actor['facts']['birth_date'] = None
    assert omitted_slot_birth_date_preimage(actor, {'birth_date': '1976-10-02'}, set()) is None


@pytest.fixture
def foreign_scope(monkeypatch):
    from scripts import season_opening_identity_exchange_v1 as exchange
    club = dict(id='club-755', carrier_id=755, division='preserve-existing-mode1-membership',
                opening=dict(policy='preserve-existing-mode1'))
    request = dict(foreign_mode1_identity_only=dict(
        policy=exchange.FOREIGN_IDENTITY_ONLY_POLICY, club_carrier_ids=[755]))
    mode = [1]
    entry = SimpleNamespace(record_id=755, payload_offset=0, payload_length=5)
    monkeypatch.setattr(exchange.IndexedFDIFile, 'from_bytes',
                        staticmethod(lambda raw: SimpleNamespace(entries=[entry])))
    monkeypatch.setattr(exchange.delta.compiler, 'parse_eq_external_team_roster_payload',
                        lambda *args: SimpleNamespace(mode_byte=mode[0]))
    def run():
        return exchange.foreign_mode1_identity_scope(request, {club['id']: club},
            {100: {'club_id': club['id']}}, [100], b'eqraw')
    return request, club, mode, run


def test_foreign_profile_scope_preserves_controls_without_claiming_an_ai_xi(foreign_scope):
    *_, run = foreign_scope
    result = run()
    assert result['clubs'][0]['club_carrier_id'] == 755
    assert result['clubs'][0]['opening_semantics'] == 'foreign-AI-XI-unproven-no-historical-opening-assignment-claim'
    assert 'unchanged' in result['controls']


@pytest.mark.parametrize('change', ['english', 'mode0', 'authored-opening', 'orders', 'complete', 'extra-club', 'duplicate'])
def test_foreign_profile_optin_does_not_relax_managed_or_authored_opening_guards(foreign_scope, change):
    request, club, mode, run = foreign_scope
    if change == 'english':
        club['id'] = 'english-club-314'
        club['division'] = 'Premier League'
    elif change == 'mode0':
        mode[0] = 0
    elif change == 'authored-opening':
        club['opening']['policy'] = 'source-bound-opening'
    elif change == 'orders':
        request['orders'] = [{'club_carrier_id': 755}]
    elif change == 'complete':
        request['complete_mode1_opening'] = {'club_carrier_id': 755}
    elif change == 'extra-club':
        request['foreign_mode1_identity_only']['club_carrier_ids'].append(752)
    else:
        request['foreign_mode1_identity_only']['club_carrier_ids'].append(755)
    with pytest.raises(ValueError):
        run()


@pytest.mark.parametrize('change', ['publisher', 'name', 'date', 'bytes', 'duplicate', 'sidebar'])
def test_biography_refuses_unbound_or_unrelated_dob(biography, change):
    exchange, actor, claim, evidence, path = biography
    if change == 'publisher':
        evidence['biography']['url'] = 'https://unreviewed.example.no/example-person'
    elif change == 'name':
        actor['source_name'] = 'Different Person'
    elif change == 'date':
        claim['birth_date'] = '1991-03-26'
    elif change == 'bytes':
        path.write_text(path.read_text() + 'changed')
    else:
        if change == 'duplicate':
            path.write_text(path.read_text().replace('</article>',
                '<p>Example Person (f.26. februar 1991, Akranes Island)</p></article>'))
        else:
            path.write_text('<article><h1>Different Person joins Molde</h1></article>'
                            '<aside>Example Person (f.26. februar 1991, Akranes Island)</aside>')
        evidence['biography']['sha256'] = registry.sha256_file(path)
    with pytest.raises(ValueError):
        exchange.official_biography_birth_date(actor, claim, evidence)
