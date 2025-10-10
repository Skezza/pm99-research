# Inferred Product & Engineering Requirements

Based on the current code, tests, and documentation, the Premier Manager 99 editor project appears to target the following capabilities:

## Core product goals
- Provide a safe desktop/CLI toolchain for inspecting and editing Premier Manager 99 `.FDI` database files while preserving unknown bytes (`README.md`, [docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Support player queries (list/search by name, lookup by ID) and controlled renames through the CLI ([app/cli.py](../app/cli.py)).
- Parse and serialize database records conservatively, with backups when writing ([docs/GETTING_STARTED.md](GETTING_STARTED.md)).

## Technical scope
- `FDIFile` encapsulates header/directory parsing, record iteration and persistence ([README.md](../README.md), [app/io.py](../app/io.py)).
- `PlayerRecord` handles dynamic field offsets, name end detection, and double-XOR attribute decoding ([README.md](../README.md), [docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Planned support for eager-loading an in-memory `DataStore` that indexes all `.FDI` and `.PKF` assets for bulk operations ([docs/EAGER_IMPLEMENTATION_PLAN.md](EAGER_IMPLEMENTATION_PLAN.md)).

## Safety & quality requirements
- Always operate on backups and ensure directory offsets remain valid after edits ([README.md](../README.md), [docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Maintain automated tests covering I/O decoding, writer behaviour, and integration scenarios (referenced in [docs/GETTING_STARTED.md](GETTING_STARTED.md)).
- Document new offsets/fields in canonical docs and keep legacy artifacts for provenance ([README.md](../README.md)).

## Outstanding needs
- Keep canonical documentation (architecture, data formats, editor usage) synchronised with implementation changes so references in `README.md` remain trustworthy.
- Test execution depends on proprietary sample data (`DBDAT/*.FDI`), indicating a requirement to distribute fixtures, provide a fetch script, or expose a flag that forces failures when data is missing so contributors notice the gap early.

