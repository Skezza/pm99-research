# PDF Reconciliation Metrics (All 4 Playable Leagues)

Generated locally on 2026-02-26 from tuned reconciliation outputs.

## Scope

- Data source: PM99 roster-listing PDFs (Premier League, Division 1, Division 2, Division 3)
- Player source: `DBDAT/JUG98030.FDI`
- Reconciler: `python3 -m app.cli roster-reconcile-pdf` (shared `app.roster_reconcile`)
- Outputs are local `/tmp/*.json` exports (not committed) used as validation artifacts

## Methodology

- Parse each PM99 listing PDF into `(name_label, team_label)` rows.
- Normalize PDF team labels to canonical club queries (explicit abbreviation map).
- Generate surname-based candidate sets from `JUG98030.FDI` and score nearby club evidence in decoded FDI entry text.
- Use two windows: default (precision-oriented) and wide (recall-oriented).
- Statuses remain backward-compatible (`isolated_default`, `no_db_candidate`, etc.); `status_detail` adds confidence/review buckets.

## League Summaries (Tuned)

| League | Rows | Teams | isolated_default | isolated_wide_only | ambiguous_total | no_club_evidence | no_db_candidate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Premier League | 530 | 20 | 155 | 92 | 42 | 70 | 171 |
| Division 1 | 559 | 24 | 277 | 77 | 63 | 49 | 93 |
| Division 2 | 541 | 24 | 188 | 58 | 42 | 125 | 128 |
| Division 3 | 496 | 24 | 158 | 70 | 44 | 124 | 100 |

## Aggregate Summary (Tuned, All Leagues)

- Total rows: **2126**
- Total teams: **92**
- `isolated_default`: **778** (36.6%)
- `isolated_wide_only`: **297** (14.0%)
- `db_candidate_no_club_evidence`: **368** (17.3%)
- `no_db_candidate`: **492** (23.1%)
- ambiguous (`default` + `wide_only`): **191** (9.0%)

### `status_detail` Buckets (normalized from row outputs)

- `isolated_default_low_conf`: 598
- `no_db_candidate`: 492
- `candidate_no_club_evidence`: 368
- `isolated_wide_provisional`: 297
- `ambiguous_review`: 191
- `isolated_default_high_conf`: 180

## Baseline vs Tuned Deltas (Where Baselines Were Captured)

### Premier League

- `isolated_default`: 129 -> 155 (+26)
- `isolated_wide_only`: 77 -> 92 (+15)
- `ambiguous_default`: 7 -> 10 (+3)
- `ambiguous_wide_only`: 24 -> 32 (+8)
- `db_candidate_no_club_evidence`: 121 -> 70 (-51)
- `no_db_candidate`: 172 -> 171 (-1)

### Division 1

- `isolated_default`: 139 -> 277 (+138)
- `isolated_wide_only`: 62 -> 77 (+15)
- `ambiguous_default`: 14 -> 29 (+15)
- `ambiguous_wide_only`: 20 -> 34 (+14)
- `db_candidate_no_club_evidence`: 224 -> 49 (-175)
- `no_db_candidate`: 100 -> 93 (-7)

### Division 2

- `isolated_default`: 182 -> 188 (+6)
- `isolated_wide_only`: 62 -> 58 (-4)
- `ambiguous_default`: 18 -> 18 (+0)
- `ambiguous_wide_only`: 23 -> 24 (+1)
- `db_candidate_no_club_evidence`: 128 -> 125 (-3)
- `no_db_candidate`: 128 -> 128 (+0)

### Division 3

- `isolated_default`: 120 -> 158 (+38)
- `isolated_wide_only`: 78 -> 70 (-8)
- `ambiguous_default`: 8 -> 22 (+14)
- `ambiguous_wide_only`: 22 -> 22 (+0)
- `db_candidate_no_club_evidence`: 168 -> 124 (-44)
- `no_db_candidate`: 100 -> 100 (+0)

## Highest/Lowest Team Rates (Tuned)

### Highest `isolated_default` Rate (min 15 rows)

- Division 1 / Norwich C.: 73.1% (19/26)
- Division 1 / Watford: 70.8% (17/24)
- Division 3 / Hartlepool U.: 65.0% (13/20)
- Division 1 / Port Vale: 62.5% (15/24)
- Division 1 / Portsmouth: 61.1% (11/18)
- Division 1 / Bolton W.: 59.1% (13/22)
- Division 1 / Stockport C.: 59.1% (13/22)
- Division 1 / Tranmere Rov.: 59.1% (13/22)
- Premier League / Aston Villa: 57.7% (15/26)
- Division 2 / Lincoln C.: 57.1% (12/21)
- Division 1 / Huddersfield T.: 56.0% (14/25)
- Division 2 / Walsall: 55.0% (11/20)

### Highest Ambiguous Rate (min 15 rows)

- Division 3 / Chester C.: 42.1% (8/19)
- Division 1 / Ipswich: 23.8% (5/21)
- Division 1 / Bradford City: 21.7% (5/23)
- Division 3 / Exeter C.: 21.1% (4/19)
- Division 1 / Huddersfield T.: 20.0% (5/25)
- Division 2 / Stoke C.: 20.0% (4/20)
- Division 3 / Plymouth Arg.: 20.0% (4/20)
- Division 1 / Bristol City: 19.2% (5/26)
- Division 2 / Bristol Rovers: 19.2% (5/26)
- Division 2 / Lincoln C.: 19.0% (4/21)
- Division 1 / Crystal Pal.: 16.7% (4/24)
- Division 1 / Sunderland: 15.4% (4/26)

### Highest `no_db_candidate` Rate (min 15 rows)

- Division 3 / Torquay U.: 50.0% (8/16)
- Premier League / Nottingham F.: 50.0% (14/28)
- Premier League / West Ham: 50.0% (12/24)
- Premier League / Wimbledon: 50.0% (14/28)
- Premier League / Blackburn R.: 46.2% (12/26)
- Division 3 / Scarborough: 45.5% (10/22)
- Premier League / Chelsea: 44.0% (11/25)
- Division 2 / Bournemouth: 43.5% (10/23)
- Division 2 / Manchester C.: 42.3% (11/26)
- Premier League / Leicester: 42.3% (11/26)
- Premier League / Liverpool: 40.7% (11/27)
- Division 2 / Luton T.: 40.0% (8/20)

## Common Review/Error Patterns (Tuned)

### Common Ambiguous Surname Labels

- Rotherham U.: `Scott` (2)
- Arsenal: `Hughes` (1)
- Aston Villa: `Thompson` (1)
- Aston Villa: `Wright` (1)
- Blackburn R.: `Blake` (1)
- Blackburn R.: `Ward` (1)
- Charlton Ath.: `Barnes` (1)
- Charlton Ath.: `Holmes` (1)
- Charlton Ath.: `Hunt` (1)
- Chelsea: `Ferrer` (1)
- Chelsea: `Flo` (1)
- Coventry: `Nilsson` (1)
- Coventry: `Williams` (1)
- Everton: `Collins` (1)
- Everton: `Dunne` (1)
- Everton: `Ward` (1)
- Leeds Utd.: `Jackson` (1)
- Leeds Utd.: `Robertson` (1)
- Leeds Utd.: `Robinson` (1)
- Leicester: `Keller` (1)
- Liverpool: `James` (1)
- Liverpool: `Jones` (1)
- Liverpool: `Thompson` (1)
- Liverpool: `Warner` (1)
- Manchester Utd.: `Berg` (1)

### Common Low-Confidence Default Isolates (review candidates)

- Arsenal: `Anelka` (1)
- Arsenal: `Bergkamp` (1)
- Arsenal: `Grimandi` (1)
- Arsenal: `Manninger` (1)
- Arsenal: `Overmars` (1)
- Arsenal: `Petit` (1)
- Arsenal: `Upson` (1)
- Arsenal: `Vieira` (1)
- Arsenal: `Winterburn` (1)
- Aston Villa: `Ferraresi` (1)
- Aston Villa: `Rachel` (1)
- Blackburn R.: `Konde` (1)
- Charlton Ath.: `Ilic` (1)
- Charlton Ath.: `Mendonca` (1)
- Charlton Ath.: `Mills` (1)
- Charlton Ath.: `Petterson` (1)
- Charlton Ath.: `Royce` (1)
- Chelsea: `Goldbaek` (1)
- Chelsea: `Lambourde` (1)
- Chelsea: `Leboeuf` (1)
- Chelsea: `Morris` (1)
- Chelsea: `Myers` (1)
- Chelsea: `Nicholls` (1)
- Chelsea: `Vialli` (1)
- Coventry: `Boateng` (1)

### Common `no_db_candidate` Labels (likely parser/extraction coverage gaps)

- Arsenal: `Boa Morte` (1)
- Arsenal: `Bould` (1)
- Arsenal: `Garde` (1)
- Arsenal: `Keown` (1)
- Arsenal: `Parlour` (1)
- Arsenal: `Seaman` (1)
- Arsenal: `Vivas` (1)
- Aston Villa: `Ehiogu` (1)
- Aston Villa: `Grayson` (1)
- Aston Villa: `Joachim` (1)
- Aston Villa: `Merson` (1)
- Blackburn R.: `Broomes` (1)
- Blackburn R.: `Corbett` (1)
- Blackburn R.: `Dailly` (1)
- Blackburn R.: `Duff` (1)
- Blackburn R.: `Fettis` (1)
- Blackburn R.: `Filan` (1)
- Blackburn R.: `Flowers` (1)
- Blackburn R.: `Gillespie` (1)
- Blackburn R.: `Kenna` (1)
- Blackburn R.: `Marcolin` (1)
- Blackburn R.: `McAteer` (1)
- Blackburn R.: `McKinlay` (1)
- Charlton Ath.: `Konchesky` (1)
- Charlton Ath.: `Lisbie` (1)
- Charlton Ath.: `Pringle` (1)
- Charlton Ath.: `Redfearn` (1)
- Charlton Ath.: `Tiler` (1)
- Chelsea: `Babayaro` (1)
- Chelsea: `Casiraghi` (1)
- Chelsea: `De Goey` (1)
- Chelsea: `Di Matteo` (1)
- Chelsea: `Duberry` (1)
- Chelsea: `Forssell` (1)
- Chelsea: `Hitchcock` (1)
- Chelsea: `Kharine` (1)
- Chelsea: `Le Saux` (1)
- Chelsea: `Petrescu` (1)
- Chelsea: `Wise` (1)
- Coventry: `Daish` (1)

## Known Limitations

- `no_db_candidate` remains heavily influenced by current player parser/extraction coverage in `JUG98030.FDI`.
- Club-evidence scoring is text-proximity based; wide-window results are recall-oriented and noisy.
- `strict_subrecord_group_byte` is a clustering signal, not a canonical team ID.
- Name-hint support is optional and only modulates existing club evidence; it does not fabricate club links when none are present.

## Recommended Next Use

- Use this document as a Milestone 5 validation artifact and regression baseline for future parser/disambiguation changes.
- Use `status_detail` and review columns in the row CSV to drive targeted manual curation / hint-file iteration.
