"""Capture the SOURCE-complete Exeter correction after the owned runner batch.

Waiting observes the exact existing process; it never restarts that process or
rebuilds games. The normal runner's lease remains the final concurrency guard.
"""
import argparse
from pathlib import Path
import time

from scripts import capture_discovered_fixture_batches_20261017 as capture
from scripts import build_public_fixture_batches_20261017 as build


def tag(season):
    return 'public_original_fixture_' + season.replace('-', '_') + '_r124a_20261017'


def main(previous_runner_pid):
    process = Path('/proc') / str(previous_runner_pid) / 'cmdline'
    while process.exists():
        try:
            command = process.read_bytes()
        except FileNotFoundError:
            break
        if not command:
            break
        if b'scripts.capture_discovered_fixture_batches_20261017' not in command:
            raise ValueError('prior runner PID now belongs to another process')
        print(dict(waiting_for_owned_runner_pid=previous_runner_pid), flush=True)
        time.sleep(10)
    folder = build.ROOT / '2024-25'
    if not (folder / 'complete-SOURCE-replay.json').exists():
        raise ValueError('Exeter actual whole SOURCE proof required before capture')
    capture.ROOT = build.ROOT
    capture.RELEASE = build.RELEASE
    capture.tag = tag
    capture.run('2024-25')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-runner-pid', type=int, required=True)
    main(parser.parse_args().previous_runner_pid)
