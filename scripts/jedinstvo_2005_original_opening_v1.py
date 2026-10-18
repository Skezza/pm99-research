"""Exact first league XI/used substitutes from retained Partizanopedia.

Publisher labels are kept as written; no invented full names, unused bench,
formation or stable-ID equivalence. Those need independent source joining.
"""
import re

from bs4 import BeautifulSoup

URL='https://www.partizanopedia.rs/0506.html'
XI=['Jovšić','Ermin Drndar','Pešić','Sadžakov','Veličković','Petrović',
    'Drašković','Trifunović','Vuković','Babača','Ekrem Drndar']
LINE='Jedinstvo Bijelo Polje: Jovšić, Ermin Drndar, Pešić, Sadžakov, Veličković, Petrović (87’ Franca), Drašković, Trifunović (od 75’ Čindrak), Vuković, Babača, Ekrem Drndar (od 68’ Ćurkić) Trener: Sava Kovačević'


def parse(payload,url=URL):
    if url not in (URL,'https://partizanopedia.rs/0506.html') or not 1000<=len(payload)<=2*1024**2:
        raise ValueError('unexpected original season URL/size')
    page=BeautifulSoup(payload,'html.parser')
    headings=[h for h in page.select('h3') if h.get_text(' ',strip=True)=='Prvenstvo:']
    if len(headings)!=1:
        raise ValueError('original domestic league section missing or ambiguous')
    nodes=list(headings[0].find_all_next(['h1','h2','h3','p']))
    if len(nodes)<5 or nodes[0].name!='h3' or nodes[0].get_text(' ',strip=True)!='Partizan - Jedinstvo Bijelo Polje 2:0 (1:0)':
        raise ValueError('original first league opponent/result differs')
    paragraphs=[]
    for node in nodes[1:]:
        if node.name!='p':
            break
        paragraphs.append(re.sub(r'\s+',' ',node.get_text(' ',strip=True)))
    if (len(paragraphs)!=4 or paragraphs[0]!='6. avgust 2005. Gledalaca: 5 000'
            or paragraphs[2]!=LINE or paragraphs[3]!="Strelci: 1:0 Ivan Tomić 23' 2:0 Radović 58'"):
        raise ValueError('original first date/XI/substitutes/coach differs')
    return dict(season='2005-06',fixture_date='2005-08-06',club='Jedinstvo Bijelo Polje',opponent='Partizan',result='2-0',
        starting_xi=XI.copy(),used_substitutes=[dict(name='Franca',minute=87),dict(name='Čindrak',minute=75),dict(name='Ćurkić',minute=68)],
        unused_substitutes=None,formation=None,manager='Sava Kovačević',source_url=url,
        source_credit='Partizanopedia / original historical first domestic match',native_writes=0,publication_authorised=False,
        limitation='Actual XI11/used3 only. Full names, DOB/roles and four additional positive opening members need independent original sources before fixed18/native approval.')
