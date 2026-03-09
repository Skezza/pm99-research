# Scripts

This directory is now PM99RE research/orchestration only.

Product development wrappers:
- `dev_editor.sh` runs commands in `upstream/pm99-skezmod-db-editor`
- `dev_patcher.sh` runs commands in `upstream/pm99-skezmod-patcher`
- `check_repo_boundary.py` enforces that PM99RE does not track editor product paths

Research/probe scripts:
- `probe_*`, `profile_*`, `reconcile_*`, and targeted patch/probe helpers remain here
- These can use local `.local/` and `DBDAT/` data, but that data must stay untracked
