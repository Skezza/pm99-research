# PM99RE Restructure Handover (2026-03-09)

## Objective

Complete the PM99 split so PM99RE is research-only, while editor/patcher implementation work lives in dedicated upstream repos.

## Final Structure

- PM99RE (this repo):
  - research notes/docs
  - probes/experiments/scripts
  - local workspace data (`.local/`, `DBDAT/`)
  - upstream submodule pointers
- Editor product repo:
  - `upstream/pm99-skezmod-db-editor`
- Patcher product repo:
  - `upstream/pm99-skezmod-patcher`

## What Was Changed

1. Product code removed from PM99RE root:
   - removed tracked `app/`
   - removed tracked `tests/`
   - removed tracked `pm99_database_editor.py`
   - removed tracked `pytest.ini`

2. Binary data policy hardened:
   - PM99RE ignores `.FDI/.PKF/.EXE`
   - PM99RE keeps tracked empty `DBDAT/.gitkeep`
   - editor and patcher repos also ignore `.FDI/.PKF/.EXE`

3. PM99RE CI now enforces boundary:
   - `.github/workflows/ci.yml` now runs `python scripts/check_repo_boundary.py`

4. Developer convenience wrappers added:
   - `scripts/dev_editor.sh`
   - `scripts/dev_patcher.sh`

5. Documentation updated:
   - root `README.md` now defines repo roles and workflow
   - `docs/README.md` now points implementation truth to submodules
   - `scripts/README.md` now documents new orchestration role

6. Canonical remotes/submodule URLs aligned:
   - PM99RE origin -> `git@github.com:Skezza/pm99-research.git`
   - editor submodule -> `git@github.com:Skezza/pm99-skezmod-db-editor`
   - patcher submodule -> `git@github.com:Skezza/pm99-skezmod-patcher`

7. History rewrite completed for PM99RE:
   - rewrote history to remove `*.FDI/*.PKF/*.EXE` from all branch commits
   - force-pushed rewritten refs

## Current Validation Snapshot

- `git ls-files | rg -i '\.(fdi|pkf|exe)$'` in PM99RE returns `0`.
- Same check returns `0` in both submodules.
- `python scripts/check_repo_boundary.py` should pass.

## Day-to-Day Workflow (Required)

1. Research/probing in PM99RE only.
2. Editor implementation changes in `upstream/pm99-skezmod-db-editor`.
3. Patcher implementation changes in `upstream/pm99-skezmod-patcher`.
4. Merge upstream repos first.
5. Commit submodule SHA bump in PM99RE.

## Known Caveat

GitHub hidden PR refs (`refs/pull/*`) cannot be rewritten via normal push and may still retain old objects until GitHub backend GC/purge.
If full storage-level purge is required, open a GitHub Support ticket referencing the forced history rewrite.

## Suggested Next Worker Tasks

1. Keep PM99RE docs focused on research context; avoid drifting product docs back here.
2. Add optional local `pre-commit` hook that runs `python scripts/check_repo_boundary.py`.
3. Periodically run submodule pointer updates from upstream repos.
