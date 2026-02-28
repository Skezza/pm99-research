# Premier Manager 99 Database Editor

This repository contains the active PM99 editor code in [app/](app/), the CLI in [app/cli.py](app/cli.py), the GUI in [app/gui.py](app/gui.py), tests in [tests/](tests/), and local working data in [DBDAT/](DBDAT/).

The project contract is defined by the root governance docs:
- [codex.md](codex.md)
- [project_plan.md](project_plan.md)
- [technical_considerations.md](technical_considerations.md)

Everything else should be reached through the documentation map in [docs/README.md](docs/README.md).

The canonical docs are:
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
- [docs/EDITOR_README.md](docs/EDITOR_README.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md)
- [docs/REFERENCE/PLAYER_FIELDS.md](docs/REFERENCE/PLAYER_FIELDS.md)
- [docs/REFERENCE/TEAM_FIELDS.md](docs/REFERENCE/TEAM_FIELDS.md)

Historical context is intentionally separated:
- [docs/HISTORY/README.md](docs/HISTORY/README.md)
- [docs/archive/README.md](docs/archive/README.md)

Quick commands:
```bash
python -m app.cli info DBDAT/JUG98030.FDI
python -m app.cli list DBDAT/JUG98030.FDI --limit 20
python -m app.cli search DBDAT/JUG98030.FDI "Ronaldo"
python -m app.gui
pytest -q
```

Reference data retained for investigation and comparison:
- [app/DBDAT/](app/DBDAT/)
- [FDI-PKF/](FDI-PKF/)
