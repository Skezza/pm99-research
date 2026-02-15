# Technical Considerations for the PM99 Database Editor

This document collects the key technical details, assumptions and risks involved in building a database editor for *Premier Manager 99*.  It is meant to provide developers and reverse engineers with a concise reference of the file formats, record structures, encoding schemes and other implementation considerations.  For a detailed project roadmap, see `project_plan.md`.

## FDI File Format Overview

* **File structure** – Each `.FDI` file begins with a 0x20‑byte header followed by a directory table of 8‑byte entries.  The directory points to variable‑length payload sections that contain encoded records【147127789726051†L16-L48】.  The header includes a `max_offset` field representing the end of the last record, which must be updated when record sizes change.
* **Record encoding** – Payloads are length‑prefixed XOR‑encoded blobs; each byte is encoded as `byte ^ 0x61`【147127789726051†L18-L24】.  After decoding, the payload contains a stream of records separated by a `dd 63 60` marker【147127789726051†L65-L69】.  Strings are encoded in Windows‑1252 and terminated by sentinel bytes【147127789726051†L75-L79】.  Numeric fields are little‑endian.
* **Backups and modification safety** – When modifying an FDI file, the writer must create a `.backup` file of the original and update the directory and header offsets to reflect new record sizes【287299873348376†L87-L100】.  Only modify copies of your original game files【856983054510079†L95-L99】.

## Player Record Layout

The player FDI (`JUG98030.FDI`) stores each player as a variable‑length record.  Known fields include:

| Offset (relative to start or sentinel) | Field | Notes |
| --- | --- | --- |
| `0 – 2` | Separator (`dd 63 60`) | Marks the start of a record【147127789726051†L65-L69】. |
| `3 – 4` | Team ID | Two‑byte little‑endian ID; used to link players to teams【147127789726051†L66-L69】. |
| `5` | Squad number | Player’s number within the team. |
| `7` | Primary position code | Stored relative to the sentinel; 0 = GK, 1 = DF, 2 = MF, 3 = FW【147127789726051†L75-L76】. |
| `8 – ?` | Name (variable) | Encoded in CP1252; terminated by sentinel bytes (`00 00 61 61`) or similar【147127789726051†L75-L79】. |
| `name_end + 7` | Secondary position and nationality | Additional byte(s) after the sentinel encode secondary position and nationality; mapping to country names requires a lookup table【147127789726051†L75-L79】. |
| `name_end + 9..12` | Birth date (DD MM YYYY) | Day and month bytes followed by a two‑byte year.  Validate plausible ranges to avoid overflow【139643134576101†L739-L783】. |
| `name_end + 13` | Height | In centimetres【147127789726051†L75-L79】. |
| `name_end + 14` | Weight | Not yet identified – suspected near height; needs investigation【168315694872327†L50-L53】. |
| `…` | Unknown/extended fields | Six bytes near the record end remain unexplained; may relate to contracts or other metadata【168315694872327†L50-L53】. |
| `len - 19.. -7` | 10 skill attributes | Each skill appears twice; values range 0–100 after double XOR【147127789726051†L80-L83】.  Identify the meaning of each pair (e.g., stamina, shooting, dribbling) through pattern analysis and in‑game testing【434420577726803†L100-L139】. |

### Variable‑Length Names

Names can vary in length.  When renaming a player:

* **Shorter names** – Pad the remaining space with `0x60` bytes (the filler used in the original records)【168315694872327†L36-L40】.  Do not remove bytes, as this would shift subsequent fields.
* **Longer names** – Create a new buffer of adequate size and recalculate directory offsets and the file header’s `max_offset` when writing【287299873348376†L95-L100】.  All subsequent directory entries must be shifted accordingly.

### Position and Nationality Codes

Positions and nationalities are encoded as single bytes relative to the sentinel offset【147127789726051†L75-L79】.  Build lookup tables mapping numeric codes to position descriptions (GK/DF/MF/FW) and country names.  Unknown codes should be left intact but editable.  Research the game’s internal mapping or deduce by cross‑referencing known players.

### Birth Date Encoding

The birth date consists of one byte each for day and month, followed by a two‑byte year in little‑endian.  Years appear to be offset by 1900 (e.g., 99 = 1999).  Ensure parsed dates fall within plausible ranges to avoid invalid dates (e.g., day 0 or month 13).  Convert dates to a human‑readable format in the UI.

## Team Record Layout

Team data lives in `EQP08030.FDI` and is parsed by `TeamRecord`.  Known fields include:

* **Team ID** – Two‑byte ID that should match the ID in player records【147127789726051†L66-L69】.  Confirm there is no offset (e.g., adding 3000) when linking to players.
* **Team name** – Extracted by scanning for sentinel‑terminated strings starting at a probable offset; encoded in CP1252.
* **Stadium details** – The function `_parse_stadium_details` in `TeamRecord` decodes a line into stadium capacity, car park size and pitch quality【139643134576101†L50-L58】.  Each subfield may be separated by whitespace or sentinel bytes.
* **Other metadata** – Division, budget, and short name fields are present but not yet decoded.  Locate these by comparing multiple team records and using heuristics.

## File Writing and Integrity

When saving modifications:

* Always create a backup of the original FDI file with a `.backup` extension【287299873348376†L87-L100】.
* Recalculate each record’s length, update directory entries, and adjust `max_offset` in the header accordingly.  The existing `file_writer.write_fdi_record()` function handles these updates.
* Preserve unknown fields by copying them unmodified unless explicitly edited.  Avoid removing any bytes, as this can misalign subsequent fields.

## Testing Considerations

* **Unit tests** – Use `pytest` to run existing tests and extend them when adding new parsing logic.  Tests ensure that decoded fields match expected values and that written files round‑trip correctly【287299873348376†L60-L72】.
* **Integration tests** – Build higher‑level tests that perform a full load‑modify‑save cycle, then reload the file to confirm that all changes persist and that the game can read the modified file without crashing.  Consider using a sample of real FDI files for regression.
* **Manual verification** – Because some fields’ meanings remain unknown, validate changes in the actual game when possible.  For example, modify a player’s weight and check if the change is reflected in the game.

## Risks and Unknowns

* **Unverified fields** – Several bytes (e.g., weight and contract data) are still unidentified【168315694872327†L50-L53】.  Editing these blindly may corrupt the save; they should be preserved or reverse‑engineered further.
* **Record resizing** – Extending a record to accommodate longer names or new fields requires recalculating directory offsets and shifting subsequent payloads.  Mistakes in offset calculation may corrupt the file.  Extensive testing is necessary after implementing resizing.
* **Cross‑version differences** – Different language editions or releases may have slight variations in FDI format or field offsets.  Keep version information in mind and test across multiple copies when possible.
* **Encoding anomalies** – Although most strings use CP1252, there may be exceptions or corrupt names.  Implement fallback mechanisms to handle invalid byte sequences without crashing.

## Summary

Understanding the FDI file structure, record encoding, and field layout is essential for safely editing *Premier Manager 99* databases.  By adhering to the encoding rules, updating directory offsets correctly, preserving unknown fields and thoroughly testing, developers can build a robust editor that extends beyond name changes to full control over players and teams.
