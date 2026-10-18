"""Share exact superseded birthday SOURCE copies; retain every recovery path."""
from scripts import season_release_registry_v1 as registry
from scripts import share_verified_old_number_sources_20261016 as core

ROOT = registry.ROOT / '.local/cleanup-20261016/shared-old-birthday-SOURCE-copies'
PAIRS = (
    ('sourced-biographic-birth-years-20261010-r67a', 'replayed-biographic-birth-years-20261010-r67b'),
    ('sourced-original-person-birth-years-20261010-r77a', 'replayed-original-person-birth-years-20261010-r77b'),
    ('sourced-original-person-birth-years-20261010-r78a', 'replayed-original-person-birth-years-20261010-r78b'),
)


if __name__ == '__main__':
    core.ROOT, core.PAIRS = ROOT, PAIRS
    core.main()
