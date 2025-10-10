# Coach Editor CLI – Verified Success

The CLI proof-of-concept for editing coaches is still accurate and maps directly
onto maintained code in this repository.

## Capabilities

* Loads and decodes the `ENT98030.FDI` section that stores coach data before
  handing the bytes to the parser.【F:scripts/coach_editor.py†L21-L35】
* Lists parsed coaches with their given and family names extracted from the
  decoded payload.【F:scripts/coach_editor.py†L38-L50】
* Renames a coach safely by enforcing fixed-length replacements, creating a
  backup, applying the substitution, and writing the updated payload back through
  the shared file-writer utilities.【F:scripts/coach_editor.py†L53-L116】【F:pm99_editor/file_writer.py†L18-L175】

## Parser Reference

`pm99_editor.coach_models.parse_coaches_from_record` continues to implement the
pattern-matching logic that recovers coach names from the decoded record while
filtering out false positives such as team names.【F:pm99_editor/coach_models.py†L40-L139】

## Usage

Run the CLI from the repository root:

```bash
python scripts/coach_editor.py list
python scripts/coach_editor.py rename "Terry EVANS" "Robby EVANS"
```

A `.backup` copy is written automatically before any modification so you can
restore the original file if needed.【F:pm99_editor/file_writer.py†L18-L30】
