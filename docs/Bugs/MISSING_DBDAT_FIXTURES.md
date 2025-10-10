# Missing bundled DBDAT fixtures break tests

## Summary
The automated test suite assumes that specific Premier Manager 99 database files are present under `DBDAT/` (for example `ENT98030.FDI` and `JUG98030.FDI`). These binary fixtures are not committed in the repository. The suite now skips affected tests when the files are missing, but that means critical integration coverage is lost on clean checkouts.

## Impact
- `scripts/test_coach_parser.py`
- `scripts/test_name_fixes.py`
- `test_loader_directly.py`

Each test now reports `skipped` when the fixtures are absent, so the overall run passes but the behaviours are unverified.

## Reproduction steps
1. Clone the repository on a machine that does not already have the Premier Manager database assets.
2. From the repository root, execute `pytest -q`.
3. Observe multiple skipped tests referencing missing `DBDAT/*.FDI` fixtures.

## Suggested fixes
- **Best**: Provide redistributable sample fixtures inside the repo (or fetch them automatically) so tests can run offline.
- **Alternative**: Keep the skip logic but add an opt-in flag (e.g. `--run-proprietary-fixtures`) so maintainers can force failures when the data is expected to be present.
- **Documentation**: Explicitly list the required data files in `README.md` / developer guide with download instructions (already covered in `docs/GETTING_STARTED.md`).
