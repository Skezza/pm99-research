# Audit of Legacy `unsorted/` Artifacts

The former `unsorted/` directory mixed accurate breakthroughs with AI-generated
status reports that no longer matched the codebase. Each item was reviewed
against the current implementation; the resulting actions are summarised below.

| Original file | Action | Rationale |
| --- | --- | --- |
| `COACH_EDITOR_SUCCESS.md` | Replaced with the updated [SUCCESS_COMPLETE_COACH_EDITOR.md](SUCCESS_COMPLETE_COACH_EDITOR.md) | The legacy note claimed renaming was “framework ready” only, but the CLI already performs the full backup/replace/write flow.【F:scripts/coach_editor.py†L53-L116】 |
| `SUCCESS_COMPLETE_COACH_EDITOR.md` | Kept (rewritten) | Still reflects the working CLI; links were updated to the maintained modules for parsing and writing.【F:pm99_editor/coach_models.py†L40-L139】【F:pm99_editor/file_writer.py†L18-L175】 |
| `PLAYER_EDITOR_SUCCESS.md` | Replaced with a status warning | The earlier claim of a fully working player editor was incorrect because `parse_all_players` still returns a single placeholder record, preventing real edits.【F:pm99_editor/player_models.py†L64-L86】 |
| `COMPLETION_NOTES.md`, `FINAL_FINDINGS.md`, `FINAL_STATUS.md`, `HANDOVER_FINAL.md`, `COMPREHENSIVE_HANDOVER.md`, `PARSER_FINDINGS.md`, `PROJECT_SUMMARY.md`, `README.md`, `LOWER_LEVEL/editor_roadmap.md`, `LOWER_LEVEL/handover.md` | Removed and replaced with stubs pointing to canonical docs | These files insisted the player parser was unfinished even though `PlayerRecord.from_bytes` now implements the field extraction and validation logic used by the editor and tests.【F:pm99_editor/models.py†L560-L760】 |
| `LOWER_LEVEL/pm99_editor/` | Deleted | This snapshot was an outdated copy of the package that predates modules such as `loaders.py` and the Tk GUI; retaining it risked divergence from the maintained `pm99_editor` package.【F:pm99_editor/loaders.py†L1-L340】【F:pm99_editor/gui.py†L48-L288】 |
| `LOWER_LEVEL/schema_players.md`, `LOWER_LEVEL/struct_notes.md`, `LOWER_LEVEL/triangulation.md`, `TERRY_EVANS_PETER_LASA.md` | Archived via stubs that direct readers to maintained specs | The authoritative field mapping now lives in the code and in `docs/DATA_FORMATS.md`, while high-signal summaries exist in `docs/reverse_engineering/REVERSE_ENGINEERING_REPORT.md`. Retaining the raw notes verbatim would duplicate or contradict current references.【F:docs/DATA_FORMATS.md†L1-L212】【F:docs/reverse_engineering/REVERSE_ENGINEERING_REPORT.md†L1-L120】 |
| `decode_one.py` | Moved to `scripts/decode_one.py` | Still useful for ad-hoc validation and consistent with the XOR helper used by the library.【F:scripts/decode_one.py†L1-L118】【F:pm99_editor/xor.py†L6-L74】 |
| `verify.txt`, `breadcrumbs.csv` | Kept in this archive | These raw captures remain accurate reference material for future verification runs.【F:docs/archive/verify.txt†L1-L32】【F:docs/archive/breadcrumbs.csv†L1-L5】 |

For all retired reports, readers are directed to the maintained documentation in
`docs/`, especially the reverse-engineering report and the editor user guide,
which supersede the AI-generated narratives.【F:docs/reverse_engineering/REVERSE_ENGINEERING_REPORT.md†L1-L120】【F:docs/EDITOR_README.md†L1-L160】
