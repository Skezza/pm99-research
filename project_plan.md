# Project Plan for a Premier Manager 99 Database Editor

This plan outlines the high‑level phases and milestones required to turn the existing reverse‑engineering work on *Premier Manager 99* into a comprehensive database editor.  It is broken into phases so that tasks can be tackled iteratively, with each phase building on the previous one.  Citations throughout reference information from the repository’s documentation and reverse‑engineering notes.

## Goals

1. **Fully editable player records** – support editing of *all* fields in player records: names (variable length), team IDs, squad numbers, positions, nationalities, birth dates, height/weight, and the ten skill attributes.  Unknown fields should be preserved if not changed.
2. **Team editing and roster management** – parse team FDI files, enable editing of team metadata (name, stadium, division, budget, etc.) and display rosters.  Allow transferring players between teams via a roster view.
3. **Robust user interface** – extend the existing GUI to display and edit all player and team fields, provide search and filtering, and support bulk operations and transfers.
4. **Reliability and test coverage** – maintain backups, update directory offsets correctly when records change, and expand the test suite to cover new functionality【287299873348376†L87-L100】.

## Phase 1 – Setup and Baseline Validation

* **Environment preparation** – clone the repository and copy your original FDI files (`JUG98030.FDI`, `ENTP08030.FDI`, `EQP08030.FDI`) into the `DBDAT/` folder; always work on copies【856983054510079†L95-L99】.  Run `pytest -q` to ensure the current code passes the test suite【287299873348376†L59-L72】.
* **Explore existing tools** – use the CLI (`python -m app`) to list, search and rename players to become familiar with the existing functionality【856983054510079†L24-L36】.

## Phase 2 – Player Record Parsing Enhancements

1. **Understand the record layout** – read `docs/DATA_FORMATS.md` to learn how each FDI file contains a header, directory table and XOR‑encoded payloads【147127789726051†L16-L48】.  Player records begin with a marker (`dd 63 60`), followed by team ID and squad number bytes, a variable‑length name, and then structured metadata and skill attributes【147127789726051†L65-L83】.
2. **Map all fields** – extend the `PlayerRecord` parser to extract nationality codes, positions, birth dates, height and weight, plus all 10 skill values.  Consult the reverse‑engineering notes for offsets and heuristics【147127789726051†L75-L79】.  Investigate unknown bytes near the end of the record for possible contract data【168315694872327†L50-L53】.
3. **Variable‑length names** – implement logic to pad or expand records safely when changing player names.  Update directory offsets and file headers using `file_writer.write_fdi_record()` so that subsequent records remain valid【287299873348376†L95-L100】.
4. **Unit tests** – for each newly parsed field or writing rule, add tests under `tests/` to confirm round‑trip behaviour and ensure that files remain loadable by the game【287299873348376†L60-L72】.

## Phase 3 – Team File Analysis and Linking

1. **Decode team data** – use the existing `TeamRecord` class to load `EQP08030.FDI`, verify heuristics for team IDs, names and stadium details【139643134576101†L67-L78】.
2. **Identify additional fields** – map division, budget, short name, stadium capacity, car park size and pitch quality.  Extend `TeamRecord` to decode these values【139643134576101†L50-L58】.
3. **Link players to teams** – verify that the first two bytes of each player record store the team ID【147127789726051†L66-L69】.  Build a mapping from team IDs to lists of players and display rosters.  Implement transfer functions to change a player’s team ID and update rosters.
4. **Team editing UI** – enhance the GUI to show editable team fields and rosters.  Provide a dropdown or transfer view to move players between teams.

## Phase 4 – GUI Enhancements and Extended Features

1. **Enhanced player editor** – extend the Players tab to show nationality, positions, birth date, height, weight and all skill values.  Use appropriate form widgets (dropdowns, spin boxes, sliders) and validate ranges【168315694872327†L121-L133】.
2. **Search and filtering** – add filters for team, position, nationality and rating ranges【168315694872327†L168-L177】.  Implement virtualised lists or lazy loading for performance【168315694872327†L507-L513】.
3. **Batch operations and transfers** – provide tools for bulk editing, mass transfers and global adjustments (e.g., boost stamina for a team)【168315694872327†L179-L187】.  Create a dedicated Transfers tab to manage player moves【168315694872327†L139-L149】.
4. **Optional advanced features** – after the core editor is complete, consider variable record expansion, team formation editing, or even save‑game editors【168315694872327†L433-L439】.

## Phase 5 – Testing, Documentation and Polish

* **Integration tests** – expand tests to cover round‑trip editing of all fields and ensure directory offsets are recalculated correctly.  Use sample FDI files to validate that the game accepts edited files.
* **Documentation updates** – update `docs/DATA_FORMATS.md`, `docs/REVERSE_ENGINEERING_REPORT.md` and the project’s changelog whenever new offsets or decoding rules are discovered【287299873348376†L136-L145】.  Create a `PLAYER_FIELD_MAP.md` to summarise field offsets.
* **User guide** – extend `docs/EDITOR_README.md` with instructions for the new editor features.  Include examples of editing players, teams and performing transfers.
* **Refinement** – perform manual testing across different seasons and fix any UI glitches or parsing inconsistencies.  Optimise the interface for large datasets and ensure error messages are clear.

## Milestones and Timeline

| Phase | Estimated Duration | Key Deliverables |
| --- | --- | --- |
| Phase 1 | 1 week | Working development environment; baseline tests passing; familiarity with CLI. |
| Phase 2 | 3 weeks | Extended `PlayerRecord` parser with all fields; variable‑length name handling; unit tests. |
| Phase 3 | 2 weeks | Complete `TeamRecord` parser; player–team linking; preliminary team editor UI. |
| Phase 4 | 3–4 weeks | Fully functional GUI with enhanced player and team editors, filtering and bulk operations. |
| Phase 5 | 1–2 weeks | Comprehensive integration tests; updated documentation; final polish and bug fixes. |

## Summary

Following this phased plan will transform the existing reverse‑engineering work into a fully fledged *Premier Manager 99* database editor.  By incrementally improving the parsing logic, linking players to teams, enhancing the GUI and strengthening tests, the project will achieve robust editing capabilities for both players and teams while maintaining data integrity and user‑friendliness.
