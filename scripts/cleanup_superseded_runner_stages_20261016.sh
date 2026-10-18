#!/usr/bin/env bash
set -euo pipefail
export PM99_RUNNER_ARCHIVE_COLD_RUNS=0
export PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE=0
# Original local evidence must exist before either reproducible test install
# is retired. No shared base, artifact directory or playable release is a target.
test -s .local/runlogs/pm99_runner/manager_display_field_probe_2016_17_20261005_c/control_launch.json
test -s .local/runlogs/pm99_runner/manager_display_field_probe_2016_17_20261005_c/screens/022_observed_championships_continue.png
test -s .local/runlogs/pm99_runner/crash04_database03_control_20261003_a/summary.json
source upstream/pm99-runner/scripts/pm99_runner/common.sh
pm99_runner_select_remote_worker default
pm99_runner_acquire_remote_host_lock cleanup-superseded-test-stages-20261016
trap 'pm99_runner_release_remote_host_lock' EXIT
pm99_runner_ssh 'set -euo pipefail
test -z "$(docker ps -q)"
test -d /home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c
test ! -L /home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c
test "$(realpath /home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c)" = /home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c
test -d /home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a
test ! -L /home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a
test "$(realpath /home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a)" = /home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a
df -B1 /home/joe/pm99-runner'
pm99_runner_unmount_remote_game_overlay /home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c
pm99_runner_unmount_remote_game_overlay /home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a
pm99_runner_ssh 'set -euo pipefail
test -z "$(docker ps -q)"
! mountpoint -q /home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c
! mountpoint -q /home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a
if findmnt -rn -o TARGET | awk -v p=/home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c '\''$0==p || index($0,p"/")==1 {found=1} END {exit !found}'\''; then exit 1; fi
if findmnt -rn -o TARGET | awk -v p=/home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a '\''$0==p || index($0,p"/")==1 {found=1} END {exit !found}'\''; then exit 1; fi
sudo -n rm -rf -- /home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c
sudo -n rm -rf -- /home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a
test ! -e /home/joe/pm99-runner/workspace/runs/manager_display_field_probe_2016_17_20261005_c
test ! -e /home/joe/pm99-runner/workspace/runs/crash04_database03_control_20261003_a
df -B1 /home/joe/pm99-runner'
