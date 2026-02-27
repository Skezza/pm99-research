# Player Rename Design

This document describes how to perform deterministic, length‑preserving renaming of player names in Premier Manager 99.

## Record Identification

Players are identified in the FDI files by their position in the directory and by internal fields:

- **Record index**: the zero‑based index of the record in the FDI directory.
- **Team ID**: stored at bytes 3–4 of the decoded record, little‑endian.
- **Squad number**: byte 5 of the record.
- **Original name**: bytes starting at offset 8 until a sentinel, encoded in CP1252.

For milestone M1, the mapping now stores both:

- **Offset** (`offset` / `offset_hex`) as the primary locator for revert (preferred)
- **Record index** as a compatibility fallback if offset is unavailable

Notes from real-data validation:

- Some scanner-derived player lists can contain multiple discovered names at the same file offset (false-positive duplicates from the same decoded blob).
- The bulk rename pipeline now treats **offset** as the integrity key for writes/reverts and skips duplicate offsets deterministically, recording warnings in per-file results.
- This preserves reversible mappings on real `JUG98030.FDI` data without disabling integrity checks.

For later milestones we may also use a composite key `(team_id, squad_no, original_name)` to improve resilience.

## Rename String Format

We generate a deterministic token for each record index:

1. Compute `index` as the integer position of the player record (0‑based).
2. Create a base token string as `Z` followed by zero‑padded digits of the index, e.g. `Z0000005` for record 5.
3. Adjust the token to match the length of the original name:
   - If the token is longer than the original name, truncate it.
   - If it is shorter, pad with `Z` characters.

This produces a new name of exactly the same length, avoiding record resizing.

## Mapping File

The bulk rename operation writes a mapping file (CSV) with the following columns:

- `record_index`: zero‑based index of the player record.
- `offset`: integer file offset used by `FDIFile.save()` / name-only writes.
- `offset_hex`: hexadecimal representation of the same offset (for readability).
- `team_id`: original team identifier.
- `squad_no`: original squad number.
- `original_name`: the name before renaming.
- `new_name`: the deterministic new name.
- `file`: the source FDI filename.

Example:

```
record_index,offset,offset_hex,team_id,squad_no,original_name,new_name,file
0,4660,0x1234,3712,1,Keen,Z0000000,JUG0001.FDI
```

## Revert Process

To revert a bulk rename, read the mapping file and, for each entry:

1. Locate the record in the corresponding FDI file by `offset` (preferred), falling back to `record_index` if needed.
2. Replace the current name with `original_name` (which has the same length).
3. Write the record back; since lengths match, directory offsets do not change.

This design ensures that the rename and revert operations are deterministic, reversible and safe.
