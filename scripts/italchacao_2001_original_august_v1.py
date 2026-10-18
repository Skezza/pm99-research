"""Read preserved club reports without pretending they are a league opener.

The source bytes contain both Windows-1252 and UTF-8 replacement characters.
Only the latter's mojibake is normalised; lost accents are not reconstructed.
Published person aliases and DOBs are joined separately, never current roles.
"""
import re

from bs4 import BeautifulSoup

CUP_URL = 'https://www.geocities.ws/mchataing/ultimoenc.html'
FRIENDLY_URL = 'https://www.geocities.ws/mchataing/preccs-itc.html'
CALENDAR_URL = 'https://www.geocities.ws/mchataing/calmerconorte.html'
LEAGUE_URL = 'https://www.forovinotinto.com/historia/ficha.php?div=1&id=4755'
CUP_LINE = ('DEPORTIVO ITALCHACAO (0): Jos� Fasciana; Luis Vallenilla Pacheco, '
            'Gregory Luzardo, Daniel Diez, Cesar Modesto Gonz�lez, Arsenio Santeugini '
            '(Felix Hern�ndez a los 46�), Claudio Silva, Leopoldo Jim�nez '
            '(Hector Bidoglio a los 64�), Andr� Luis Gomes, Edgardo Dar�o Parisi '
            '(Giovanny P�rez a 46�), Rafael Castellin. DT: Ra�l Cavallieri.')
FRIENDLY_LINE = ('DEPORTIVO ITALCHACAO (0): Jos� Fasciana; William Gonz�lez, '
                 'Daniel Diez, Gregory Luzardo, Modesto Gonz�lez; Arsenio Santeugini, '
                 'F�lix Hern�ndez, Dar�o Parisi, Andr� Gomes; Rafael Castell�n y '
                 'Fernando Mart�nez.. DT: Ra�l Cavallieri.')
XI = [('José Fasciana', 350368), ('Luis Vallenilla Pacheco', 77943),
      ('Gregory Luzardo', 147691), ('Daniel Diez', 140127),
      ('César Modesto González', 954596), ('Arsenio Santeugini', 824124),
      ('Claudio Silva', 172115), ('Leopoldo Jiménez', 140144),
      ('André Luis Gomes', 880823), ('Edgardo Darío Parisi', 511731),
      ('Rafael Castellín', 72532)]
USED = [('Félix Hernández', 350175, 46), ('Héctor Bidoglio', 347836, 64),
        ('Giovanny Pérez', 123498, 46)]
FRIENDLY_ADDITIONS = [('William González', 351335), ('Fernando Martínez', 112276)]
# Exact independent published aliases, not phonetic guesses or surname matches.
ALIASES = {350368: 'José Fasciana', 77943: 'Luis Vallenilla',
           147691: 'Gregory Luzardo', 140127: 'Daniel Diez',
           954596: 'César Modesto González', 824124: 'Arsenio Santeugini',
           172115: 'Claudio Silva da Fonseca', 140144: 'Leopoldo Jiménez',
           880823: 'André Luis Gomes Vieira', 511731: 'Edgardo Dario Parisi',
           72532: 'Rafael Castellín', 350175: 'Félix Hernández',
           347836: 'Héctor Bidoglio', 123498: 'Giovanny Pérez',
           351335: 'William González', 112276: 'Fernando Martínez'}


def flat(raw, encoding='cp1252'):
    if not isinstance(raw, bytes) or not 500 <= len(raw) <= 2 * 1024 ** 2:
        raise ValueError('unexpected original payload type or size')
    text = raw.decode(encoding, errors='replace').replace('ï¿½', '�')
    return re.sub(r'\s+', ' ', BeautifulSoup(text, 'html.parser').get_text(' ', strip=True))


def parse(cup_raw, friendly_raw, calendar_raw, league_raw, *,
          urls=(CUP_URL, FRIENDLY_URL, CALENDAR_URL, LEAGUE_URL)):
    if urls != (CUP_URL, FRIENDLY_URL, CALENDAR_URL, LEAGUE_URL):
        raise ValueError('unexpected original source URLs')
    cup, friendly, calendar = map(flat, (cup_raw, friendly_raw, calendar_raw))
    league = flat(league_raw, 'utf8')
    if cup.count(CUP_LINE) != 1 or 'Mie, 8 de Agosto de 2001' not in cup:
        raise ValueError('original cup XI/date missing, changed or ambiguous')
    if '8 de Julio de 2001' not in cup:
        raise ValueError('original conflicting incidence date not retained')
    if friendly.count(FRIENDLY_LINE) != 1 or 'Dom, 12 de Agosto de 2001' not in friendly:
        raise ValueError('original friendly XI/date missing, changed or ambiguous')
    if not re.search(r'8[/.-]0?8[/.-](?:20)?01', calendar):
        raise ValueError('original cup calendar does not corroborate August date')
    if ('19 de Agosto del 2001.' not in league
            or 'Torneo Apertura 2001 - Jornada 1' not in league
            or 'No hay información disponible sobre el banquillo de este equipo.' not in league):
        raise ValueError('independent league-date/coverage record changed')
    return dict(season='2001-02', club='Deportivo Italchacao',
        cup_date='2001-08-08', cup_opponent='MetroStars', cup_result='0-2',
        friendly_date='2001-08-12', friendly_opponent='Caracas FC', friendly_result='1-2',
        manager_published='Ra�l Cavallieri',
        starting_xi=[dict(published_match_name=n, source_player_id=id) for n, id in XI],
        used_substitutes=[dict(published_match_name=n, source_player_id=id, minute=m) for n, id, m in USED],
        additional_august_people=[dict(published_match_name=n, source_player_id=id) for n, id in FRIENDLY_ADDITIONS],
        league_opening_date='2001-08-19', league_starting_xi=None,
        unused_substitutes=None, formation=None,
        source_disagreements=[dict(field='cup date', published='2001-07-08',
            corroborated='2001-08-08', disposition='Body date and original cup calendar agree on August; July incidence typo retained.')],
        limitations=['Cup/friendly lineup is NOT the first league XI.',
            'Sixteen distinct August people fit the fixed16 slots; only one goalkeeper is sourced. Do not invent a second goalkeeper.',
            'Missing original accents must be joined through independently published person aliases.',
            'Héctor Bidoglio period club DOB February15 disagrees with independent February5.'],
        native_writes=0, publication_authorised=False)


def join_people(parsed, people_document):
    if (people_document.get('schema_version') != 'pm99-original-published-person-identities-v1'
            or parsed.get('league_starting_xi') is not None):
        raise ValueError('unsupported independent identities or falsely completed league lineup')
    people = {}
    for batch in people_document['batches']:
        for person in batch['people']:
            id = person['source_player_id']
            if id in people:
                raise ValueError('duplicate independent identity')
            people[id] = person
    selected = parsed['starting_xi'] + parsed['used_substitutes'] + parsed['additional_august_people']
    if len(selected) != 16 or len({r['source_player_id'] for r in selected}) != 16:
        raise ValueError('August union not sixteen distinct source-named players')
    rows = []
    for row in selected:
        id = row['source_player_id']
        person = people[id]
        if (ALIASES[id] not in person['published_name_variants']
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', person['birth_date'] or '')):
            raise ValueError('independent published alias or birthday missing')
        rows.append(dict(row, independent_name=person['name'],
            independent_published_alias=ALIASES[id], independent_birth_date=person['birth_date'],
            birthday_approved=id != 347836,
            current_roles_imported=False, current_club_imported=False))
    return rows
