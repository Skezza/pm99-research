# Inferred Product & Engineering Requirements

Based on the current code, tests, and documentation, the Premier Manager 99 editor project appears to target the following capabilities:

## Core product goals
- Provide a safe desktop/CLI toolchain for inspecting and editing Premier Manager 99 `.FDI` database files while preserving unknown bytes (`README.md`, [docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Support player queries (list/search by name, lookup by ID) and controlled renames through the CLI ([pm99_editor/cli.py](../pm99_editor/cli.py)).
- Parse and serialize database records conservatively, with backups when writing ([docs/GETTING_STARTED.md](GETTING_STARTED.md)).

## Technical scope
- `FDIFile` encapsulates header/directory parsing, record iteration and persistence ([README.md](../README.md), [pm99_editor/io.py](../pm99_editor/io.py)).
- `PlayerRecord` handles dynamic field offsets, name end detection, and double-XOR attribute decoding ([README.md](../README.md), [docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Planned support for eager-loading an in-memory `DataStore` that indexes all `.FDI` and `.PKF` assets for bulk operations ([docs/EAGER_IMPLEMENTATION_PLAN.md](EAGER_IMPLEMENTATION_PLAN.md)).

## Safety & quality requirements
- Always operate on backups and ensure directory offsets remain valid after edits ([README.md](../README.md), [docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Maintain automated tests covering I/O decoding, writer behaviour, and integration scenarios (referenced in [docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Document new offsets/fields in canonical docs and keep legacy artifacts for provenance ([README.md](../README.md)).

## Outstanding needs
- Canonical documentation for architecture, data formats, and editor usage is referenced but missing, implying a requirement to author or restore those files ([docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Test execution depends on bundled sample data (`DBDAT/*.FDI`), indicating a requirement to distribute fixtures or provide setup guidance (see [docs/Bugs/MISSING_DBDAT_FIXTURES.md](Bugs/MISSING_DBDAT_FIXTURES.md)).
