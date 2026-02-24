# Rename Milestones Plan

This document defines the milestone ladder for the bulk rename effort in Premier Manager 99. Each milestone progressively increases complexity and ensures safe editing of the FDI databases.

## Milestone Ladder

- **M1: Bulk rename all players (length preserving, deterministic)**  
  Replace every player name with a deterministic string of the same length. Strings are composed of uppercase letters and digits. Example: `Z000001` for first record. No record resizing is required.

- **M2: Variable‑length rename subset**  
  Rename a controlled subset of players with names that are one or two characters longer or shorter than the original. Verify that offsets and directory entries update correctly.

- **M3: Full variable‑length rename**  
  Rename all players with arbitrary lengths. Produce a full mapping file to allow reverting.

- **M4: Extended renaming**  
  Apply similar techniques to coaches, teams and leagues once the player pipeline is stable.

## Success Criteria

For each milestone:

1. The game still boots and displays updated names in all screens (line‑up, search, transfers).
2. Record count and other binary invariants remain unchanged.
3. Re‑loading the modified FDI files in the editor reproduces exactly the names that were written.
4. A mapping file is generated recording the original and new names along with record index and team id.
5. A revert command can restore the original names.

## Safety Rules

- Always work on a copy of the original FDI files. Do not commit binary assets.
- Keep a `.backup` copy of each FDI file before modifications.
- Do not modify record sizes unless implementing milestones M2+.
- Use only safe characters (A‑Z, 0‑9) in new names.
- Provide a reversible mapping file for any bulk operation.

## Test Protocol

1. **Pre‑Rename State**: Record current player names by exporting them via CLI.
2. **Rename**: Run the bulk rename command. Check that the CLI lists the new names.
3. **Binary Checks**: Verify that the number of records and header offsets match expectations.
4. **In‑Game Smoke Test**: Load the modified database in Premier Manager 99 and confirm the new names appear correctly.
5. **Round‑Trip**: Re‑load the FDI files in the editor and confirm the names are exactly those written.
