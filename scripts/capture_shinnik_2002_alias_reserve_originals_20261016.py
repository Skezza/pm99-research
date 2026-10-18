"""Small original source package for the coupled Stoke/Shinnik alias owners."""
from scripts import capture_manager_conflict_articles_20261016 as capture
from scripts.audit_shtanyuk_runtime_aliases_20261016 import ROOT


if __name__ == '__main__':
    capture.ROOT = ROOT / 'Shinnik2002-originals'
    capture.SOURCES = (
        ('khomukha-biography', 'https://en.wikipedia.org/wiki/Dmitri_Khomukha'),
        ('Shinnik2002-registered-squad', 'https://100bombardirov.ru/ru/2002/squad/shn.htm'),
        ('Shinnik2002-opening-report', 'https://www.transfermarkt.co.uk/spartak-moscow_shinnik-yaroslavl/index/spielbericht/2833981'),
    )
    capture.main()
