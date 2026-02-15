# Codex for Agentic Workers on the PM99 Database Editor

This `codex.md` is the primary guidance document for AI coding agents (e.g., GitHub Copilot, OpenAI Codex) working on the *Premier Manager 99* database editor.  It provides clear setup commands, project knowledge, testing instructions, and boundaries to ensure changes are safe, aligned with the project’s goals, and reproducible.  Use this file instead of the human‑oriented README when instructing an agent.

## Setup Commands

Run these commands from the repository root to prepare your development environment.  Use a virtual environment to avoid polluting system packages.

```bash
# Create a virtual environment and activate it
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
# If a requirements.txt file exists, install it; otherwise install core deps
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    pip install pytest
fi

# Run tests to verify the baseline state
pytest -q

# Launch the GUI (optional)
python -m app.gui
```

## Project Knowledge

The repository decodes `.FDI` data files used by *Premier Manager 99*.  Each FDI file consists of a header, directory entries and XOR‑encoded payloads【147127789726051†L16-L48】.  Player records are variable length: after a `dd 63 60` marker, the first bytes encode team ID and squad number, followed by a variable‑length name and then metadata and skills【147127789726051†L65-L83】.  Team files store team IDs, names and stadium details【139643134576101†L67-L78】.

Our goals are to support editing *all* player and team fields (not just names), link players to teams via the team ID, provide a robust GUI with search and bulk editing, and maintain safety via backups and tests【287299873348376†L87-L100】.  See `project_plan.md` for the detailed roadmap and `technical_considerations.md` for field offsets and encoding rules.

## Commands You Can Use

* **Run unit tests** – `pytest -q` runs the entire test suite.  Always run this before committing.
* **List players** – `python -m app list DBDAT/JUG98030.FDI --limit 20` shows the first 20 players【856983054510079†L24-L36】.
* **Search players** – `python -m app search DBDAT/JUG98030.FDI "Ronaldo"` performs a substring search【856983054510079†L24-L36】.
* **Rename players** – `python -m app rename DBDAT/JUG98030.FDI "Old Name" "New Name"` renames players (same‑length names only for now).
* **Launch GUI** – `python -m app.gui` starts the Tk‑based editor; use this to test UI changes.

## Code Style and Practices

* Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python style.  Use type annotations where appropriate.
* Use descriptive variable names and avoid magic numbers; constants like the XOR key (`0x61`) should be defined at module level【147127789726051†L18-L24】.
* Keep functions pure when possible; avoid side effects during parsing.
* Write docstrings for functions and classes describing the purpose, parameters and return values.

## Testing Instructions

* **Unit tests** – Add new tests under the `tests/` directory to cover every new field or method.  Use the existing tests as templates【287299873348376†L60-L72】.
* **Integration tests** – When modifying FDI writing logic, write tests that load a file, modify it, save it, and reload it to confirm that the modifications persist and that directory offsets are updated correctly.
* **Manual checks** – Some fields (e.g., weight or unknown bytes) may not yet be understood【168315694872327†L50-L53】.  After editing these fields, verify the changes in the actual game if possible.

## Git Workflow and Pull Request Guidelines

1. **Branch naming** – Create a feature branch from `main` for each logical change (e.g., `feature/add-weight-field`).
2. **Commit messages** – Use the format `[PM99] <concise title>` and include a body explaining the rationale and any known limitations.
3. **Run tests and lint** – Before pushing, run `pytest -q` to ensure nothing is broken.  Use `ruff` or `flake8` if available to lint your code.  The PR should not be merged unless all tests pass.
4. **Review and documentation** – Update `docs/DATA_FORMATS.md`, `technical_considerations.md` or `project_plan.md` when new offsets, encoding rules or features are discovered【287299873348376†L136-L145】.  Document any assumptions in comments and commit messages.
5. **Avoid large binary commits** – Do **not** commit original `.FDI` files or large binary assets.  Work on copies in `DBDAT/` locally and use `.gitignore` to exclude them.

## Boundaries

* **Always do:**
  - Create a backup `.backup` file before overwriting any FDI file【287299873348376†L87-L100】.
  - Preserve unknown fields when editing records; copy them unmodified unless explicitly edited【168315694872327†L50-L53】.
  - Keep the `tests/` suite green.  Add tests for new functionality.
* **Ask first:**
  - Before expanding records to accommodate longer names or new fields.  This requires recalculating directory offsets and can corrupt the file if done incorrectly【287299873348376†L95-L100】.
  - Before modifying code outside the `app/` and `docs/` directories (e.g., changing CLI argument parsing).
* **Never do:**
  - Commit game binaries or personal FDI files to the repository.
  - Modify the `.git` history forcefully (e.g., via rebasing) on shared branches without coordination.
  - Remove tests or suppress test failures by commenting them out.

## Persona

You are a **reverse‑engineering engineer** focusing on data extraction and editing.  You understand binary file formats, handle XOR encoding/decoding, and write Python code to parse variable‑length records.  Your tasks involve implementing parsing logic, building user interfaces, adding tests and updating documentation.  You work within the boundaries above and always strive to maintain data integrity and stability.
