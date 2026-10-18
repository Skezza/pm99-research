"""Acquire two independent country-code ambiguity witnesses; no game writes."""
from scripts.capture_stock_replacement_sources_20261010 import main

if __name__=='__main__':
    main(extra_sources=[
        ('cgo-samba-original-country-witness','https://en.wikipedia.org/wiki/Christopher_Samba'),
        ('cgo-imbula-original-country-witness','https://en.wikipedia.org/wiki/Giannelli_Imbula'),
    ],only_extra=True,transport='curl')
