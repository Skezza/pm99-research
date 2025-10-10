# Legacy Documentation Coverage

This log cross-references the deleted markdown notes (snapshot `5c3d5a6`) with the consolidated `README.md`. Use it as a checklist when verifying that historical discoveries remain documented.

## Migrated into `README.md`

| Source file | Preserved highlights | README anchors |
| --- | --- | --- |
| `BALANCED_FILTERING_FIX.md` | Expected GUI counts, manual QA steps, garbage rejection examples. | *Filtering rules for teams & coaches* → “Manual QA checkpoints”. |
| `FINAL_FILTER_ADJUSTMENTS.md` | Player-name blocklist (~50 entries) plus league/stadium/phrase categories. | *Filtering rules for teams & coaches* → “Blocklist coverage snapshots”. |
| `GHIDRA_VALIDATION_NOTES.md` | Header offsets, XOR routine disassembly, container overview. | *Binary format & reverse-engineering findings* → “Ghidra cross-reference” + “FDI container layout (ASCII map)”. |
| `HANDOVER_GUI_LOADING_ISSUES.md` | Loader counts (4,891 coaches / 2,391 teams) and step-by-step debugging workflow. | *GUI status & outstanding work* → “GUI investigation checklist”. |
| `LEAGUES_TAB_COMPLETE_SUMMARY.md`, `LEAGUES_TAB_FINAL_PLAN.md`, `LEAGUES_TAB_IMPLEMENTATION_PLAN.md` | English division ID ranges, planned notebook layout, section offsets. | *GUI status & outstanding work* → “League metadata reference” + Leagues tab bullet list. |
| `PERFORMANCE_OPTIMIZATION_SUMMARY.md` | Single-pass scanner refactor, benchmark numbers (6,076 players / 3.2 s), future tuning ideas. | *Loader performance & scanning heuristics* → “Optimization highlights”, “Benchmark targets”, “Future tuning ideas”. |
| `REFACTORING_SUMMARY.md` | Shared loader module benefits, duplication removal, test coverage. | *Loader performance & scanning heuristics* (intro bullets) and *Filtering rules* (shared loader expectations). |
| `data/README.md` | `.FDI`, `.PKF`, and `.FDI.backup` file guidance. | *Quick start* → sample data bullet. |
| `docs/Bugs/NAME_PARSING_FIXES.md` | Separator regex, scoring weights, garbage cleanup, dedupe strategy. | *Historical investigations & guardrails* → expanded name-parsing notes. |
| `docs/Bugs/PLAYER_RECORD_PARSER_BUG.md` | Validation commands, outstanding serializer/nationality/weight TODOs. | *Binary format* (player field map + hex walkthrough) and *Roadmap & future enhancements* → serialization/nationality bullets. |
| `docs/Bugs/UNKNOWN_POSITION.md` | Position offset discovery, attribute window, distinction between small vs biography records. | *Player record field map* (ASCII diagram) and *Historical investigations & guardrails* → “Record variants”. |
| `docs/EAGER_IMPLEMENTATION_PLAN.md` | Proposed `DataStore`/`PKFFile` abstractions and CLI flag ideas. | *Roadmap & future enhancements* → “Unified data store”. |
| `docs/PLAYER_STATS_TEMPLATE.md` | Request for in-game stat captures to cross-validate decoded attributes. | *Roadmap & future enhancements* → “Player stats correlation”. |
| `docs/enhancement_plans/ENHANCEMENT_PLAN.md`, `docs/enhancement_plans/FULL_EDITOR_ROADMAP.md` | Multi-phase roadmap: variable-length editing, team editor, transfers, batch ops. | *Roadmap & future enhancements* → “Full editor roadmap”. |
| `docs/Investigations/TEAM_FILE_BREAKTHROUGH.md` | 543-team discovery, 88 XOR sections, global coverage notes. | *Binary format* → “Team record markers” + *GUI status* → “League metadata reference”. |
| `docs/README.md` | Reminder that scripts/docs acted as exploratory scratch pads. | *Repository layout & maintenance* → `scripts/` bullet and maintenance guidance. |
| `scripts/README.md` | Script naming taxonomy (`analyze_*`, `debug_*`, etc.). | *Repository layout & maintenance* → expanded `scripts/` note. |

## Historical / Outdated (retain externally if needed)

The following notes describe superseded marker-based parsers or speculative field guesses. Their core facts now live in the README, but the prose still reflects deprecated approaches:

* `PLAYER_NAME_RENAMING_ANALYSIS.md`, `PLAYER_NAME_RENAMING_IMPLEMENTATION.md`
* `docs/Investigations/SESSION_COMPLETE_SUMMARY.md`
* `docs/Investigations/UNDERSTANDING_DATA_FORMATS.md`
* `docs/TEAM_FIELD_STRUCTURE_GUESS.md`
* `docs/field_mapping/player/FIELD_MAPPING_BREAKTHROUGH.md`
* `docs/field_mapping/player/FIELD_MAPPING_SESSION_REPORT.md`
* `docs/field_mapping/player/PLAYER_FIELD_MAP.md`
* `docs/field_mapping/player/PLAYER_METADATA_FIELDS.md`
* `docs/field_mapping/player/PLAYER_POSITION_FIELD.md`
* `docs/field_mapping/team/TEAM_FIELDS.md`
* `docs/old_incorrect_docs/EDITOR_README.md`
* `docs/reverse_engineering/PLAYER_REVERSE_ENGINEERING.md`
* `docs/reverse_engineering/REVERSE_ENGINEERING_REPORT.md`

## Next verification pass

1. Update the README whenever fresh byte-level discoveries land so this table stays short.
2. When reviving any historical note above, port the actionable facts into the relevant README section rather than restoring the original markdown.
