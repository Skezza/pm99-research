# Suggested Follow-up Improvements

## 1. Document or restore missing canonical files
Multiple guides (for example the root [README](../README.md) and [docs/GETTING_STARTED.md](GETTING_STARTED.md)) reference `docs/ARCHITECTURE.md`, `docs/DATA_FORMATS.md`, and `docs/EDITOR_README.md`, but these files are absent from the repository. Either add the documents or trim the references so newcomers are not sent to dead links.

## 2. Provide open sample data or conditionalize data-heavy tests
The automated tests expect proprietary `DBDAT/*.FDI` assets. Add redistributable fixtures, or gate the tests when the files are not available, so contributors can run the suite without extra setup. See [docs/Bugs/MISSING_DBDAT_FIXTURES.md](Bugs/MISSING_DBDAT_FIXTURES.md).

## 3. Clarify CLI rename limitations
`pm99_editor/cli.py` performs in-place renames by assigning `record.name = args.name` and writing via `FDIFile.save()`. Consider documenting padding requirements or adding length validation before writes to avoid silent truncation/corruption when new names exceed original byte windows.

## 4. Register custom pytest markers
`tests/test_embedded_player_detection.py` uses `@pytest.mark.integration` but pytest warns that the marker is unknown. Add a `pytest.ini` or `conftest.py` with `markers = integration: ...` to silence the warning and clarify intent.
