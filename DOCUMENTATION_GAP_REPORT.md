# Legacy Documentation Gap Report

This report summarizes the surviving markdown files from commit `5c3d5a6` whose contents were **not** fully migrated into the consolidated `README.md`. Items marked as “Historical/Outdated” describe approaches that conflict with the current sequential parser; keep them only for provenance.

| Source file | Key information not in README | Relevance |
| --- | --- | --- |
| `BALANCED_FILTERING_FIX.md` | GUI before/after counts (Teams tab 1 → ~50–70, Coaches tab cleanup), detailed garbage categories, manual QA checklist. | Still relevant for regression testing. |
| `FINAL_FILTER_ADJUSTMENTS.md` | ~50-name coach blocklist, rationale for relaxed prefix heuristics, GUI spot-check guidance. | Still relevant; blocklist entries should live near loader code. |
| `GHIDRA_VALIDATION_NOTES.md` | Header table (36-byte header, offsets 0x24/0x26) and note that the coach loader calls `FUN_00677e30` sequentially. | Relevant, supplements current Ghidra summary. |
| `HANDOVER_GUI_LOADING_ISSUES.md` | Counts from sequential scans (4,891 coaches / 2,391 teams), debugging checklist for `load_coaches()` / `populate_coach_tree()`, sample code for directory inspection. | Relevant when tackling GUI “Unknown coach/team” defects. |
| `LEAGUES_TAB_COMPLETE_SUMMARY.md` | Exact English division ID ranges (3712–3731 etc.), proposed Tk layout, Leagues tab testing checklist. | Relevant for GUI backlog. |
| `LEAGUES_TAB_FINAL_PLAN.md` | EQ98030 section offsets (0x201, 0x2f04), hard-coded league dictionary sample, alternative keyword-detection idea. | Relevant for future implementation notes. |
| `LEAGUES_TAB_IMPLEMENTATION_PLAN.md` | Reminder that loaders already read the two XOR sections, ideas like league statistics panel and `team_id` reassignment helper. | Relevant feature backlog. |
| `PERFORMANCE_OPTIMIZATION_SUMMARY.md` | Benchmark (6,076 players in 3.19 s, 70–80% faster), regex snippet, future optimization ideas (lazy load, mmap). | Relevant for performance baselines. |
| `REFACTORING_SUMMARY.md` | Pre/post record counts (teams 2,391→~116; coaches 4,891→~300), mention of helper scripts to retire. | Relevant for historical metrics & cleanup TODOs. |
| `data/README.md` | Mentions `.PKF` assets alongside `.FDI` and `.backup`. | Relevant; README only notes backups. |
| `docs/Bugs/NAME_PARSING_FIXES.md` | Detailed scoring heuristics, before/after name examples, scripts `test_name_fixes.py` & `analyze_player_names.py`. | Relevant background for legacy GUI parser. |
| `docs/Bugs/PLAYER_RECORD_PARSER_BUG.md` | CLI command transcripts (9,086 players listed), outstanding tasks (serializer NotImplemented, nationality mapping, weight field). | Relevant TODO log. |
| `docs/Bugs/UNKNOWN_POSITION.md` | Distinction between “small” vs “biography” records, helper scripts (`analyze_small_record_structure.py`, `validate_known_players.py`). | Relevant context despite marker focus. |
| `docs/EAGER_IMPLEMENTATION_PLAN.md` | Proposed `DataStore`/`PKFFile` APIs, CLI flags (`--db-root`, `--mode`), memory guardrails. | Relevant future project plan. |
| `docs/PLAYER_STATS_TEMPLATE.md` | Template requesting in-game stats (attributes in display order, height/weight in imperial units). | Relevant if correlation work resumes. |
| `docs/enhancement_plans/ENHANCEMENT_PLAN.md` | Multi-phase roadmap (variable-length names, team editor, transfers, batch ops) with effort estimates. | Relevant planning artifact. |
| `docs/enhancement_plans/FULL_EDITOR_ROADMAP.md` | Requirements for full player editor, record-boundary analysis strategies. | Relevant planning artifact. |
| `docs/Investigations/TEAM_FILE_BREAKTHROUGH.md` | Team coverage summary (543 teams, 88 XOR sections, geography list) and script inventory. | Relevant discovery recap. |
| `docs/README.md` | Historical documentation index noting which files were canonical vs archived. | Relevant for provenance. |
| `scripts/README.md` | High-level taxonomy of scripts (`analyze_*`, `debug_*`, etc.). | Relevant orientation aid. |

## Historical / Outdated (retain only for provenance)

These files describe the deprecated marker-based parser (`name_end + 7`) or other superseded heuristics.

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

Most of their factual highlights (double-XOR discovery, metadata offsets, outstanding TODOs) now live in the README, but the surrounding guidance still reflects the retired anchor-first implementation.

## Suggested migration actions

1. **Decide on relevancy:** For each row above, confirm whether the information should be merged into the README, moved into code comments/tests, or archived permanently.
2. **Update live docs:** When adopting an item, fold the precise details (e.g., performance baselines, blocklist members, league ranges) into the appropriate README section.
3. **Archive obsolete guidance:** Keep the “Historical / Outdated” files outside the repo or mark them as superseded to avoid regression to `name_end` heuristics.
