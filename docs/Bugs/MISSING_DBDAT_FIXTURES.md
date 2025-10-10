# Missing bundled DBDAT fixtures break tests

## Summary
The automated test suite assumes that specific Premier Manager 99 database files are present under `DBDAT/` (for example `ENT98030.FDI` and `JUG98030.FDI`). These binary fixtures are not committed in the repository, so any clean checkout that runs `pytest` fails during collection with `FileNotFoundError` exceptions when the tests attempt to load them.

## Impact
- `scripts/test_coach_parser.py`
- `scripts/test_name_fixes.py`
- `test_loader_directly.py`

All three suites abort before assertions run, preventing the rest of the tests from executing.

## Reproduction steps
1. Clone the repository on a machine that does not already have the Premier Manager database assets.
2. From the repository root, execute `pytest -q`.
3. Observe `FileNotFoundError: [Errno 2] No such file or directory: 'DBDAT/ENT98030.FDI'` (and similar for `JUG98030.FDI`).

## Suggested fixes
- **Best**: Provide redistributable sample fixtures inside the repo (or fetch them automatically) so tests can run offline.
- **Alternative**: Guard tests behind markers or skip logic when fixtures are absent, while documenting the external dependency.
- **Documentation**: Explicitly list the required data files in `README.md` / developer guide with download instructions.
