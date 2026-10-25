"""Source-context negatives and optional retained official-source replay."""
import hashlib
import unittest
from pathlib import Path
from scripts import season_official_career_context_v1 as helper
from scripts import season_annual_row_identity_guard_v1 as annual
from scripts import season_release_registry_v1 as registry
_helper=helper
POLICY=helper.POLICY
check_annual_dob=helper.check_annual_dob
country_code=helper.country_code
verify_official_career_context=helper.verify_official_career_context
pdf_subject_text=helper._pdf_subject_text
html_subject_text=helper._html_subject_text

class NullAnnualDobAdmissionV2Tests(unittest.TestCase):
    def career(self, paragraph, fullname='Ada Example', club='FC North Town', season='1999-00'):
        body=('<html><body><p>'+paragraph+'</p></body></html>').encode()
        url='https://www.uefa.com/example/history';sha=hashlib.sha256(body).hexdigest()
        receipt={'url':url,'raw_sha256':sha,'http_status':200,'method':'original-network-body'}
        return verify_official_career_context(body,source_url=url,source_sha256=sha,receipt=receipt,
            fullname=fullname,source_club=club,target_season=season)

    def test_null_dob_is_only_admitted_by_explicit_policy(self):
        self.assertEqual(check_annual_dob(POLICY,None,'1966-02-20'),'1966-02-20')
        with self.assertRaises(ValueError):check_annual_dob(POLICY,'1973-06-25','1966-02-20')
        with self.assertRaises(ValueError):check_annual_dob(POLICY,None,'1966-02-30')
        with self.assertRaises(ValueError):check_annual_dob('annual-source-row-person-identity-v1',None,'1966-02-20')

    def test_same_generic_policy_accepts_different_persons_years_and_countries(self):
        self.assertEqual(check_annual_dob(POLICY,None,'1966-02-20'),'1966-02-20')
        self.assertEqual(check_annual_dob(POLICY,None,'1981-11-03'),'1981-11-03')
        self.assertEqual(country_code('Switzerland'),'SUI')
        self.assertEqual(country_code('France'),'FRA')
        self.assertEqual(country_code('England'),'ENG')
        self.assertEqual(country_code('Schweiz'),'SUI')
        self.assertEqual(country_code('Swiss'),'SUI')
        with self.assertRaises(ValueError):country_code('born in Switzerland')
        a=self.career('North Town coach Ada Example played for them as a defender in two spells (1984-87 and 1996-2003).')
        b=self.career('Ben Sample played for FC Lakeview as a defender (2002-2006).',fullname='Ben Sample',club='FC Lakeview',season='2004-05')
        self.assertEqual(a['career_ranges'],[[1984,1987],[1996,2003]])
        self.assertEqual(b['career_ranges'],[[2002,2006]])

    def test_explicit_playing_club_must_match_target_not_just_paragraph(self):
        with self.assertRaises(ValueError):
            self.career('Target FC coach Ada Example played for Other FC as a defender (1980-1989).',club='Target FC',season='1985-86')
        direct=self.career('Target FC coach Ada Example played for Target FC as a defender (1980-1989).',club='Target FC',season='1985-86')
        self.assertEqual(direct['career_ranges'],[[1980,1989]])

    def test_ambiguous_them_and_coaching_years_are_rejected(self):
        with self.assertRaises(ValueError):
            self.career('Target FC and Other FC coach Ada Example played for them as a defender (1980-1989).',club='Target FC',season='1985-86')
        with self.assertRaises(ValueError):
            self.career('Target FC coach Ada Example played for them as a defender (1980-1989) and coached there in 2010-2020.',club='Target FC',season='2015-16')
        with self.assertRaises(ValueError):
            self.career('Target FC coach Ada Example played for them as a defender (1980-2000).',club='Target FC',season='2000-01')

    def test_year_only_tenure_boundaries_are_not_opening_membership_proof(self):
        with self.assertRaises(ValueError):
            self.career('North Town coach Ada Example played for them as a defender (1996-2003).',season='1996-97')
        with self.assertRaises(ValueError):
            self.career('North Town coach Ada Example played for them as a defender (1996-2003).',season='2003-04')

    def test_birthplace_and_job_do_not_prove_player_career(self):
        with self.assertRaises(ValueError):self.career('Ada Example was born in North Town and is its coach.')
        with self.assertRaises(ValueError):self.career('North Town coach Ada Example joined as youth and took charge in 2010.')

    def test_pdf_fields_must_align_with_named_column(self):
        good='Urs Fischer\nBorn: 20/02/1966,\nTriengen (SUI)\nNationality: Swiss\nPaulo Fonseca\nBorn: 05/03/1973\nNationality: Portuguese\n'
        claims=[{'label':'Born:','literal':'20/02/1966'},{'label':'Nationality:','literal':'Swiss'}]
        self.assertIn('Urs Fischer',pdf_subject_text(good,'Urs Fischer',claims))
        wrong='Urs Fischer\nTriengen (SUI)\nNationality: Swiss\nPaulo Fonseca\nBorn: 20/02/1966\n'
        with self.assertRaises(ValueError):pdf_subject_text(wrong,'Urs Fischer',claims)
        cross='Urs Fischer\nBorn: 20/02/1966,\nTriengen (SUI)\nPaulo Fonseca\nNationality: Swiss\n'
        with self.assertRaises(ValueError):pdf_subject_text(cross,'Urs Fischer',claims)
        wrong_country='Urs Fischer\nBorn: 20/02/1966,\nTriengen (SUI)\nNationality: Portuguese\n'
        with self.assertRaises(ValueError):pdf_subject_text(wrong_country,'Urs Fischer',claims)

    def test_html_claims_must_share_named_profile_container(self):
        source={'subject_name_label':'Name:','birth_date':{'label':'Birthday:','literal':'20/02/1966'},
                'nationality':{'label':'Nation:','literal':'Schweiz'}}
        good=b'<section><table><tr><td>Name: Urs Fischer</td></tr><tr><td>Birthday: 20/02/1966</td></tr><tr><td>Nation: Schweiz</td></tr></table></section>'
        self.assertIn('Urs Fischer',html_subject_text(good,'Urs Fischer',source))
        split=b'<section><table><tr><td>Name: Urs Fischer</td></tr></table></section><p>Birthday: 20/02/1966 Nation: Schweiz</p>'
        with self.assertRaises(ValueError):html_subject_text(split,'Urs Fischer',source)
        wrong=b'<section><table><tr><td>Name: Other Player</td></tr><tr><td>Birthday: 20/02/1966</td></tr><tr><td>Nation: Schweiz</td></tr></table></section>'
        with self.assertRaises(ValueError):html_subject_text(wrong,'Urs Fischer',source)

    def test_actual_official_bodies_fit_name_and_period_guards(self):
        base=Path('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/fischer-2000-inherited-native-facts-v1')
        root=registry.ROOT
        if not (root/base/'source/v2/uefa-zurich-player-career.html').is_file():
            self.skipTest('retained official-source corpus unavailable in this clone')
        career=(root/base/'source/v2/uefa-zurich-player-career.html').read_bytes()
        sha=hashlib.sha256(career).hexdigest()
        receipt={'url':'https://www.uefa.com/uefaeuropaleague/news/01f5-0e79738121cc-333257df258a-1000--zurich-out-to-end-portuguese-hoodoo-against-sporting/',
                 'raw_sha256':sha,'http_status':200,'method':'original-network-body'}
        out=verify_official_career_context(career,source_url=receipt['url'],source_sha256=sha,receipt=receipt,
            fullname='Urs Fischer',source_club='FC Zürich',target_season='2000-01')
        self.assertIn([1996,2003],out['career_ranges'])
        dfb=(root/base/'source/v2/dfb-urs-fischer-player-v2.html').read_bytes()
        context=html_subject_text(dfb,'Urs Fischer',{'subject_name_label':'Name:',
            'birth_date':{'label':'Geburtstag:','literal':'20.02.1966'},
            'nationality':{'label':'Nation:','literal':'Schweiz'}})
        self.assertIn('Nation: Schweiz',context)
        pdf_path=root/base/'source/v2/uefa-2015-16-technical-report.pdf'
        import subprocess
        extracted=subprocess.run(['pdftotext','-raw',str(pdf_path),'-'],capture_output=True,check=True).stdout.decode()
        pdf_context=pdf_subject_text(extracted,'Urs Fischer',[
            {'label':'Born:','literal':'20/02/1966'},{'label':'Nationality:','literal':'Swiss'}])
        self.assertIn('Born: 20/02/1966',pdf_context)
        request=__import__('json').loads(((root/base/'prototype-v4-adversarial/fischer-null-dob-request-v3.json')).read_text())
        pdfsource=request['changes'][0]['witness']['official_sources'][1]
        self.assertEqual(_helper.source_text(pdfsource),extracted)
        version=subprocess.run(['pdftotext','-v'],capture_output=True,text=True,check=True).stderr.splitlines()[0]
        self.assertTrue(version.startswith('pdftotext version ')) # QA provenance only, not a semantic rejection rule




class AdversarialNullDobV4Tests(unittest.TestCase):
    def test_named_target_and_other_players_sentence_is_rejected(self):
        import hashlib
        for paragraph in (
                'Target FC coach Ada Example was appointed in 2010, while Bob Smith played for Target FC as a defender (1980-1989).',
                'Bob Smith said Ada Example played for Target FC as a defender (1980-1989).',
                'Target FC coach Ada Example mentored Bob Smith, who played for Target FC as a defender (1980-1989).',
                'Ada Example joined the club as a youth player in the early 1970s, Bob Smith, who played for Target FC as a defender (1980-1989).',
                'Ada Example spoke with the club, then he played for Target FC as a defender (1980-1989).',
                "Ada Example's former teammate played for Target FC as a defender (1980-1989)."):
            body = ('<p>' + paragraph + '</p>').encode()
            sha = hashlib.sha256(body).hexdigest()
            with self.subTest(paragraph=paragraph), self.assertRaises(ValueError):
                helper.verify_official_career_context(
                    body, source_url='https://www.uefa.com/example/history', source_sha256=sha,
                    receipt={'url': 'https://www.uefa.com/example/history', 'raw_sha256': sha,
                             'http_status': 200, 'method': 'original-network-body'},
                    fullname='Ada Example', source_club='Target FC', target_season='1985-86')

    def test_html_cannot_borrow_fact_rows_from_another_subject(self):
        source = {'subject_name_label': 'Name:',
                  'birth_date': {'label': 'Birthday:', 'literal': '20/02/1966'},
                  'nationality': {'label': 'Nation:', 'literal': 'Schweiz'}}
        body = (b'<table><tr><td>Name:</td><td>Urs Fischer</td>'
                b'<td>Birthday:</td><td>11/11/1980</td><td>Nation:</td><td>Germany</td></tr>'
                b'<tr><td>Name:</td><td>Other Coach</td><td>Birthday:</td><td>20/02/1966</td>'
                b'<td>Nation:</td><td>Schweiz</td></tr></table>')
        with self.assertRaises(ValueError):
            helper._html_subject_text(body, 'Urs Fischer', source)

    def test_nonofficial_fact_host_is_rejected(self):
        with self.assertRaises(ValueError):
            helper.approved_official_fact_publisher({
                'url': 'https://example.net/person/urs-fischer',
                'document_type': 'text/html'})

    def test_actor_club_must_match_source_selector_and_be_unambiguous(self):
        package = {'clubs': [
            {'id': 'club-a', 'name': 'FC North Town', 'full_name': 'FC North Town'},
            {'id': 'club-b', 'name': 'FC South Town', 'full_name': 'FC South Town'}]}
        self.assertEqual(annual._verified_actor_club('FC North Town', package, 'club-a'),
                         'FC North Town')
        with self.assertRaisesRegex(ValueError, 'differ'):
            annual._verified_actor_club('FC North Town', package, 'club-b')
        ambiguous = {'clubs': package['clubs'] + [
            {'id': 'club-c', 'name': 'FC North Town', 'full_name': 'FC North Town'}]}
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            annual._verified_actor_club('FC North Town', ambiguous, 'club-a')

    def test_null_dob_namesake_in_same_source_club_is_rejected(self):
        selected = {'facts': {'name': 'Alex Example', 'birth_date': None}}
        source_club = {'players': [selected]}
        annual._require_unique_null_dob_name(selected, source_club)
        source_club['players'].append({'facts': {'name': 'Alex Example', 'birth_date': '1974-05-01'}})
        with self.assertRaisesRegex(ValueError, 'not unique'):
            annual._require_unique_null_dob_name(selected, source_club)
        # A same-name row in another source club does not make this club's row ambiguous.
        annual._require_unique_null_dob_name(
            selected, {'players': [{'facts': {'name': 'Alex Example', 'birth_date': None}}]})


