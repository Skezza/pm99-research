# PM99 English league carrier membership contract (2026-08-28)

## Decision

PM99's opening English league membership is **not** an editable field inside a
club's EQ record.  It is the identity of the fixed carrier record onto which
the complete club state is written.

That complete state is the club strings and ground data, roster links, manager
link, kit art, opening lineup/tactics and associated player records.  A club
must therefore be moved as one planned transaction; changing a byte called
"division" is neither necessary nor a safe editor feature.

The native shape is fixed and sufficient for 2015/16:

| Target competition | Clubs | 1998 picker baseline | Game-used non-picker baseline carriers |
| --- | ---: | ---: | --- |
| Premier League | 20 | 20 | none |
| Championship | 24 | 20 | `321`, `328`, `332`, `365` |
| League One | 24 | 20 | `335`, `350`, `355`, `366` |
| League Two | 24 | 20 | `324`, `359`, `371`, `3306` |

The twenty baseline picker carriers in each division are supplied from the
1998 runtime selector map; they are intentionally interleaved EQ record IDs,
not numeric ranges. The full registry is materialised by
`scripts/prepare_2015_english92_native_manifest.py`.

Important qualification: that answers which records formed the original 1998
picker. It does **not** safely predict which twenty rewritten clubs are
offered after a full variable-length historical rebuild. Competition membership
remains correct, but human-manager availability must be captured from the
built output and treated as release data.

## Runtime proof

Fresh 1998 games on `pm99-runner` show the non-picker carriers in their actual
24-club league tables:

| PM99 table | Hidden clubs visibly present | Screenshot |
| --- | --- | --- |
| First Division | QPR, Huddersfield Town, Bradford City, Watford | `league_contract_vanilla_div1_screen_20260828/screens/027_league_tables_inspect.png` |
| Second Division | Oldham Athletic, Luton Town, Wrexham, Burnley | `league_contract_vanilla_div2_screen_20260828/screens/027_league_tables_inspect.png` |
| Third Division | Southend United, Plymouth Argyle, Cambridge United, Halifax Town | `league_contract_vanilla_div3_screen_20260828/screens/027_league_tables_inspect.png` |

The selector control separately provides the 80 visible carriers in
`.local/selector_maps/core80_clean_native_eq_map_20260828.json`.  It is only a
picker map, not the competition model.

The native 2015 candidate is bit-for-bit reproducible after refreshing the
baseline metadata (`JUG98030.FDI`, `EQ98030.FDI` and `ENT98030.FDI` hashes are
identical between native-carrier builds 1 and 2). Fresh runner games prove all
four actual opening tables, rather than merely parsing the database:

| 2015/16 PM99 table | Screenshot |
| --- | --- |
| Premier League | `english92_native_carrier_build1_tables_20260828/screens/027_league_tables_inspect.png` |
| Championship | `english92_native_carrier_build1_div1_table_20260828/screens/027_league_tables_inspect.png` |
| League One | `english92_native_carrier_build1_div2_table_20260828/screens/029_league_tables_inspect.png` |
| League Two | `english92_native_carrier_build1_div3_table_20260828/screens/027_league_tables_inspect.png` |

Two records formerly included by the sequential experimental build are not
native English competition carriers: `377` (Doncaster Rovers) and `381`
(Hereford United) are mode-1 records.  Conversely `3306` (Halifax Town) and
`3311` (Macclesfield Town) are required mode-0 English carriers.  This is why
the earlier `301..392` assumption leaked Macclesfield and could not be a
release shape.

## Implementation and guardrails

`prepare_2015_english92_native_manifest.py` produces a 92-club ledger which:

1. preserves all 80 runner-proven **baseline** picker slots;
2. adds each of the twelve game-used hidden slots to its proven division;
3. insists on a 20/24/24/24 source season and exactly 92 unique carrier IDs;
4. records baseline slot provenance, while requiring a fresh post-build picker
   capture for the actual selectable clubs.

`build_2015_english92_release.py` rejects a 92-club source ledger unless it
uses that exact carrier set.  It no longer accepts the unsafe sequential range.

`audit_2015_english92_runtime_picker.py` is the post-build gate. It resolves
the runner's OCR only against the intended division, rejects weak or ambiguous
matches, and publishes the actual four non-picker clubs per Football League
division. On the native 2015 candidate it proved:

| Division | Actual non-picker clubs in that built database |
| --- | --- |
| Championship | Brentford, Huddersfield Town, Middlesbrough, Wolverhampton Wanderers |
| League One | Burton Albion, Gillingham, Port Vale, Wigan Athletic |
| League Two | Bristol Rovers, Luton Town, Northampton Town, York City |

For the browser editor, "Move club to league" must therefore be a future
**competition-layout transaction** with these validation rules:

- all 92 native carriers must remain occupied exactly once;
- each division must retain its fixed 20/24/24/24 shape;
- player roster, manager, kit and tactics travel with the carrier assignment;
- the UI must disclose the four clubs unavailable to the human manager from
  the generated database's own picker audit, rather than guessing from an
  original carrier ID;
- a fresh-game proof must inspect every picker panel and every league table.

It must not expose an unsupported raw EQ metadata byte as a generic editable
"division" field.
