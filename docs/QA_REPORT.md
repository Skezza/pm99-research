# QA Report — Current Test Run

## Environment
- Python: 3.11.12
- Command: `pytest -q`
- Working directory: repository root

## Result
The suite completes successfully when the proprietary `DBDAT` databases are absent thanks to skip guards. Summary:

```
39 passed, 27 skipped in 0.30s
```

### Skipped checks
- `scripts/test_coach_parser.py`
- `scripts/test_name_fixes.py`
- `test_loader_directly.py`

All three rely on `DBDAT/*.FDI` fixtures and emit informative skip messages if the assets are not present.

## Follow-up
Bundled fixtures (or a documented fetch step) would allow CI to exercise the skipped integration suites. See [docs/Bugs/MISSING_DBDAT_FIXTURES.md](docs/Bugs/MISSING_DBDAT_FIXTURES.md) for remediation ideas.
