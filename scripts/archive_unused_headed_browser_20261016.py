"""Offload unused headed Chromium; retain the working headless Playwright shell."""
from pathlib import Path
from scripts import archive_old_playwright_cache_20261016 as archive
from scripts import season_release_registry_v1 as registry


def main():
    archive.SOURCE=Path('/home/joe/.cache/ms-playwright/chromium-1234')
    archive.CURRENT=Path('/home/joe/.cache/ms-playwright/chromium_headless_shell-1234')
    archive.REMOTE='/srv/hdd/pm99-archive/regenerable-tool-caches/20261016/unused-headed/chromium-1234'
    archive.ROOT=registry.ROOT/'.local/cleanup-20261016/unused-headed-browser'
    archive.SCOPE='Only inactive regenerable headed Chromium1234 cache. Current headless shell1234 retained for normal headless Playwright tests; headed sessions require restoring this cache from Pi or reinstalling it. No games, recipes, source datasets, screenshots or personal files removed.'
    archive.main()


if __name__=='__main__':main()
