# Division 2 PDF Reconciliation (Bulk Roster Investigation)

Date: 2026-02-25

## Input

- PDF: `/home/joe/Documents/2nd div.pdf`
- Source type: PM99 "LISTING OF ALL PALYERS" export (surname + team listing)
- Pages: 10
- Parsed rows: 541
- Teams: 24 (full Division 2 roster list)

## New Tooling

Added:

- `scripts/reconcile_division_roster_pdf.py`

Capabilities:

- Parse PM99 roster listing PDFs (`NAME` + `TEAM` columns) page-by-page
- Normalize PM99 team abbreviations (e.g. `Stoke C.` -> `Stoke City`)
- Scan `JUG98030.FDI` once (heuristic + strict sources)
- Reconcile PDF surname rows to DB player candidates
- Score club-association evidence using nearby team mentions (default + wide window)
- Export:
  - detailed row-level reconciliation CSV/JSON
  - team summary CSV
  - preliminary strict subrecord group-byte hints

## Outputs Generated (local)

- Detailed JSON: `/tmp/2nd_div_reconcile.json`
- Detailed rows CSV: `/tmp/2nd_div_reconcile_rows.csv`
- Team summaries CSV: `/tmp/2nd_div_reconcile_teams.csv`
- Strict-only group-byte scan summary: `/tmp/2nd_div_strict_groups.json`

## Bulk Reconciliation Results (All 24 Teams)

Status counts across 541 PDF rows:

- `isolated_default`: 182
- `isolated_wide_only`: 62
- `ambiguous_default`: 18
- `ambiguous_wide_only`: 23
- `db_candidate_no_club_evidence`: 128
- `no_db_candidate`: 128

Interpretation:

- ~34% (`182/541`) of surname rows can already be isolated to a single DB candidate at the default context window.
- An additional ~11% (`62/541`) can be recovered only with a wider context window (lower precision).
- ~24% have DB surname candidates but no current club-evidence link.
- ~24% currently have no DB candidate under present parsing/search heuristics.

## Stoke City (Target Club) — Current Bulk Surname Reconciliation

Team label in PDF: `Stoke C.` (normalized query: `Stoke City`)

Summary:

- roster rows: 20
- `isolated_default`: 10
- `any_default_match`: 11
- `any_wide_match`: 14
- `no_db_candidate`: 3
- `db_candidate_no_club_evidence`: 3

Using the separately reconstructed matchday squad (8 Aug 1998 lineup screenshot + external context), the Stoke row-level results show:

- `10` default isolated surname matches
- `9/10` of those are correct full-name matches
- 1 false isolation (surname ambiguity):
  - `Robinson` -> picked `Les ROBINSON` (expected `Phil ROBINSON`)

Examples of true default isolations:

- `Muggleton` -> `Carl MUGGLETON`
- `Forsyth` -> `Richard FORSYTH`
- `Keen` -> `Kevin KEEN`
- `Lightbourne` -> `Kyle LIGHTBOURNE`
- `Sigurdsson` -> `Larus SIGURDSSON`
- `Sturridge` -> `Simon STURRIDGE`
- `Thorne` -> `Peter THORNE`
- `Wallace` -> `Ray WALLACE`
- `Petty` -> `Ben PETTY`

Examples still problematic:

- `Clarke` (wide-only ambiguous; `Nicky CLARKE` vs `Clive CLARKE`)
- `Fraser` (wide-only ambiguous)
- `Heath` (default ambiguous; `Robert` vs `Seamus`/`Richard`)
- `Robinson` (wrong isolated match)
- `Kavanagh`, `Short`, `Small` (DB candidates found, but no club evidence in current windows)
- `Crowe`, `McKenzie`, `Oldfield` (no DB candidate under current parser/search path)

## Parser-Side Investigation (Strict Subrecord Group Bytes)

A strict-only `club-investigate` sweep was run across all 24 Division 2 clubs (using normalized team queries).

Observed:

- Strict hits exist for many clubs, but group-byte distributions are **not one-to-one** with clubs.
- Some group bytes appear strongly associated with a club in the current evidence, but several are shared across multiple clubs.

Examples:

- `0x4B`: seen in `Stoke C.` (8), `Bristol Rovers` (4), `Macclesfield T.` (4)
- `0x54`: seen in `Stoke C.` (7), `Burnley` (4)
- `0x7F`: seen in `York City` (9), `Chesterfield` (2)
- `0x55`: only observed in `Blackpool` (6) in this sweep
- `0x6C`: only observed in `Manchester C.` (4) in this sweep

Working interpretation:

- The strict subrecord `group byte` is useful as a clustering signal but is **not yet a direct team ID**.
- It may represent a higher-level group, container partition, or partially-shared codebook rather than a unique club key.

## Practical Value of the Division PDF (What It Enables)

This PDF is highly useful even without first names:

1. It gives a club-grounded surname truth set for 24 teams.
2. It lets us measure extraction quality (recall / ambiguity / false isolation) at scale.
3. It provides supervised signals for improving:
   - club association heuristics,
   - candidate disambiguation,
   - parser/search coverage,
   - strict subrecord reverse engineering.

## Immediate Next Improvements (Informed by These Results)

1. Add a **roster-guided disambiguation layer** (surname + club + optional lineup position/shirt number) to reduce wrong isolates like `Robinson`.
2. Add per-row confidence thresholds / filters to split:
   - default-safe isolates,
   - wide-context provisional matches,
   - manual-review rows.
3. Expand player parsing coverage for currently missed names (`no_db_candidate`) before increasing heuristic window further.
4. Continue strict subrecord reverse engineering with a larger labeled set (more leagues/PDFs).
