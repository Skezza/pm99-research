"""Fail-closed parser tests; synthetic fixtures are not historical evidence."""
import pytest

from scripts.season_palermo_opening_review_v1 import LABELS, guardalben_past_row, report


def original(*, publication='2005-08-30T16:46:00+00:00', date='28/agosto/2005',
             keeper='Guardalben', extra=''):
    return f'''<meta property="article:published_time" content="{publication}">
    <h1>Fichas completas da primeira rodada da Série A</h1><article>
    Parma 1×1 Palermo Parma Lupatelli; Corradi – Técnico: Mario Beretta Palermo
    {keeper} (Santoni, 43min); Zaccardo, Barzagli, Terlizzi e Grosso;
    Santana, Corini (Brienza, 65min), Barone e Bonanni (Mutarelli, 59min);
    Makinwa e Caracciolo – Técnico: Luigi del Neri Data: {date} Estádio: Ennio Tardini
    {extra}</article>'''.encode()


def test_literal_starters_excludes_used_substitutes():
    parsed = report(original())
    assert parsed['starting_xi_names'] == LABELS
    assert parsed['used_substitute_names'] == ['Santoni', 'Brienza', 'Mutarelli']
    assert parsed['complete_bench_published'] is False


@pytest.mark.parametrize('kwargs', [
    {'publication': '2006-08-30T16:46:00+00:00'}, {'date': '29/agosto/2005'},
    {'keeper': 'Sirigu'}, {'keeper': 'Guardalben, Guardalben'},
])
def test_wrong_date_publication_or_starters_refused(kwargs):
    with pytest.raises(ValueError):
        report(original(**kwargs))


def test_missing_substitution_annotation_refused():
    with pytest.raises(ValueError):
        report(original().replace(b'(Santoni, 43min)', b''))


def test_duplicate_article_refused():
    with pytest.raises(ValueError):
        report(original() + b'<article>duplicate</article>')


def past(*, title='=  Palermo - Italian Serie A 2005/06', name='Matteo Guardalben',
         dob='05-06-74', pos='G', extra=''):
    return f'''{title}
Number, Name, Pos, Height, Weight, Date of Birth, Birth Place, Previous Club
1, Federico Agliardi, G, , , 11-02-83, Brescia, Brescia
== Past Players
Number, Name, Pos, Height, Weight, Date of Birth, Birth Place, New Club
99, {name}, {pos}, , , {dob}, Nogara, Parma (On Loan)
{extra}'''.encode()


def test_only_positive_guardalben_past_row_admitted():
    result = guardalben_past_row(past(extra='9, Simone Pepe, F, , , 30-08-83, Rome, Udinese'))
    assert result['name'] == 'Matteo Guardalben'
    assert result['birth_date'] == '1974-06-05'
    assert result['annual_section'] == 'Past Players'


@pytest.mark.parametrize('kwargs', [
    {'title': '=  Palermo - Italian Serie A 2006/07'}, {'name': 'Nicola Santoni'},
    {'dob': '05-05-74'}, {'pos': 'D'},
    {'extra': '99, Matteo Guardalben, G, , , 05-06-74, Nogara, Parma'},
])
def test_past_row_identity_section_or_dob_change_refused(kwargs):
    with pytest.raises(ValueError):
        guardalben_past_row(past(**kwargs))
