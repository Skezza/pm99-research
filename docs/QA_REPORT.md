# QA Report — Current Test Run

## Environment
- Python: 3.11.12 (pyenv)
- Command: `pytest -q`
- Working directory: repository root

## Result
The test run aborted during collection because required binary fixtures under `DBDAT/` are missing.

### Error excerpt
```
FileNotFoundError: [Errno 2] No such file or directory: 'DBDAT/ENT98030.FDI'
```

### Affected suites
- `scripts/test_coach_parser.py`
- `scripts/test_name_fixes.py`
- `test_loader_directly.py`

No other tests executed because of the early failure.

## Follow-up
See [docs/Bugs/MISSING_DBDAT_FIXTURES.md](docs/Bugs/MISSING_DBDAT_FIXTURES.md) for remediation ideas.
