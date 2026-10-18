#!/usr/bin/env bash
set -euo pipefail
export PM99_RUNNER_ARCHIVE_COLD_RUNS=0
export PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE=0
source upstream/pm99-runner/scripts/pm99_runner/common.sh
pm99_runner_select_remote_worker default
pm99_runner_acquire_remote_host_lock cleanup-owned-rating-runner-stages-20261011
trap 'pm99_runner_release_remote_host_lock' EXIT
# These exact two installs belong to this turn. Evidence remains local and
# remote; only reproducible Wine/game staging is removed, never shared bases.
pm99_runner_ssh 'set -euo pipefail
test -z "$(docker ps -q)"
test -d /home/joe/pm99-runner/workspace/runs/rating_calibration_2002_03_r100a_20261011
test ! -L /home/joe/pm99-runner/workspace/runs/rating_calibration_2002_03_r100a_20261011
test -d /home/joe/pm99-runner/namespaces/pm99-research-main/workspace/runs/rating_calibration_2022_23_r101a_20261011_neuer
test ! -L /home/joe/pm99-runner/namespaces/pm99-research-main/workspace/runs/rating_calibration_2022_23_r101a_20261011_neuer
df -B1 /home/joe/pm99-runner'
pm99_runner_unmount_remote_game_overlay /home/joe/pm99-runner/workspace/runs/rating_calibration_2002_03_r100a_20261011
pm99_runner_unmount_remote_game_overlay /home/joe/pm99-runner/namespaces/pm99-research-main/workspace/runs/rating_calibration_2022_23_r101a_20261011_neuer
pm99_runner_ssh 'set -euo pipefail
test -z "$(docker ps -q)"
! mountpoint -q /home/joe/pm99-runner/workspace/runs/rating_calibration_2002_03_r100a_20261011/game-merged
! mountpoint -q /home/joe/pm99-runner/namespaces/pm99-research-main/workspace/runs/rating_calibration_2022_23_r101a_20261011_neuer/game-merged
sudo -n rm -rf -- /home/joe/pm99-runner/workspace/runs/rating_calibration_2002_03_r100a_20261011
sudo -n rm -rf -- /home/joe/pm99-runner/namespaces/pm99-research-main/workspace/runs/rating_calibration_2022_23_r101a_20261011_neuer
test ! -e /home/joe/pm99-runner/workspace/runs/rating_calibration_2002_03_r100a_20261011
test ! -e /home/joe/pm99-runner/namespaces/pm99-research-main/workspace/runs/rating_calibration_2022_23_r101a_20261011_neuer
df -B1 /home/joe/pm99-runner'
