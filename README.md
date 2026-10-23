# PM99RE (Research Workspace)

PM99RE is the research/integration repository for Premier Manager 99 reverse engineering.

## Repository Roles

- `upstream/pm99-skezmod-db-editor` is the source of truth for editor product code.
- `upstream/pm99-skezmod-patcher` is the source of truth for shipped patch tooling.
- `upstream/pm99-runner` is the source of truth for runtime/remote runner automation.
- `tools/` contains standalone research/viewer tools that are not product editor or patcher code, including the PKF viewer and browser runtime harness.
- `experiments/` contains source-only prototypes that are not ready to be promoted to `tools/`.
- PM99RE keeps research notes, probes, validation scripts, and local workspace data.

PM99RE must not carry parallel editor implementation code.

## Local Data Policy

- `DBDAT/` exists as a local drop folder.
- `.FDI`, `.PKF`, and `.EXE` files are ignored and must remain local-only.
- Browser runtime assets such as ISO/ZIP/WASM/disk images must remain local-only inside ignored tool asset directories.
- `.local/` remains the primary local game/workspace area.
- `work/`, `worktrees/`, `artifacts/`, `tbc/`, and `FDI-PKF/` are local-only scratch/artifact areas.
- `upstream/` is only for declared submodules. Put alternate checkouts and worker branches in ignored `worktrees/`.

## Daily Workflow

1. Do reverse-engineering and experiments in PM99RE.
2. Implement reusable editor changes in `upstream/pm99-skezmod-db-editor`.
3. Implement reusable patch changes in `upstream/pm99-skezmod-patcher`.
4. Implement reusable runner changes in `upstream/pm99-runner`.
5. Merge upstream repos first.
6. Bump PM99RE submodule pointers to merged commits.

Helper wrappers:
- `scripts/dev_editor.sh`
- `scripts/dev_patcher.sh`

## Guardrails

- `scripts/check_repo_boundary.py` enforces PM99RE repository boundaries.
- `scripts/check_repo_state.py` checks clean root/submodule state for reproducible handoff.
- CI runs this check on pushes and pull requests.
- Local pre-commit hook runs the same check via `.githooks/pre-commit` (hooks path: `.githooks`).

## Key Documents

- Product docs index: `upstream/pm99-skezmod-db-editor/docs/README.md`
- PM99RE docs index: `docs/README.md`

## Historical season source credits

Historical squad and match facts are credited to their original publishers,
including [FootballSquads](https://www.footballsquads.co.uk/),
[Soccerbase](https://www.soccerbase.com/),
[11v11 / Association of Football Statisticians](https://www.11v11.com/),
[Football-Data.co.uk](https://www.football-data.co.uk/),
[National Football Teams](https://www.national-football-teams.com/) and
[Transfermarkt](https://www.transfermarkt.co.uk/). The pinned historical dataset
is credited to the
[Transfermarkt-derived dataset project](https://github.com/jso-w/transfermarkt-datasets-f).
Original player pages and their public person/transfer-history feeds supplement
missing retired-player identities and dated moves; immutable local receipts
retain original URLs and hashes. Current club/position fields and contemporary
profile portraits are not historical season evidence.

The [DFB Datencenter](https://datencenter.dfb.de/) also supplies explicit
player and target-season team facts. [Wikidata](https://www.wikidata.org/) is
credited for a narrowly checked Kharine/Kharin spelling, birth-date and
Soccerbase-ID link; that link is not used to infer nationality or club ownership.

[100 бомбардиров](https://100bombardirov.ru/ru/2002/squad/shn.htm) is credited
for the 2002 Shinnik registration facts; that page attributes its squad details
to the Russian Premier League (RFPL). Its target-year facts are cross-checked
against retained biographies and dated appearances, not treated as a complete
opening-day lineup. The [Russian Football Union](https://www.rfs.ru/cup/players/shtaniuk-siarhei)
also supplies an independently retained Shtanyuk identity/birthday witness.
Original URLs, bodies and hashes remain in local source receipts; these
acknowledgements do not grant redistribution rights to the pages or photographs.

[StatsCrew](https://www.statscrew.com/worldfootball/stats/p-noicelew001) is
credited for an explicitly labelled secondary birthday where the dated
Soccerbase player's original profile omits it. Such a single-publication fact
does not establish independent consensus; competing date leads remain recorded.
Club membership still requires the original dated match and numerical club
career evidence, not the secondary biography's current-club field.

Additional missing-fact witnesses are credited to
[Southport Central's official player archive](https://www.southportcentral.co.uk/players/player-details/?id=696),
[AFC Sudbury's player biographies](https://www.afcsudbury.co.uk/a/a-to-z-the-men-of-afc-sudbury-39173.html?page=10),
[Stalybridge Celtic's official profiles](https://www.stalybridgeceltic.co.uk/play.php?code=PRICC)
and [11v11 / AFS Enterprises](https://www.11v11.com/players/john-norman-9941/).
These supply explicitly labelled secondary birthdays or a missing bench
biographical role, not proof of starting positions or independent consensus.
The 11v11 witness is transparently retained as a minimal extracted factual
excerpt, not mislabelled as original network HTML. Dated numerical match and
career evidence still establishes identity and membership; source credits
do not grant rights to redistribute the publishers' pages or photographs.

The [Eastleigh FC blog / Jamie Montigue's June 2014 Joma launch](https://eastleighfc.blogspot.com/2014/06/eastleigh-fc-and-joma-reveal-new-201415.html)
supplies the retained 2014/15 home-shirt reference. Factory-style renders
simplify commercial logos and fine piping; a shirt-only image does not prove
the shorts. [Sky Sports' dated Eastleigh–Aldershot match record](https://www.skysports.com/football/eastleigh-vs-aldershot-town/319716)
supplies period ground evidence. Source credits do not grant image redistribution rights.

The Barnet 2018/19 correction credits [Barnet FC's original fixture announcement](https://barnetfc.com/news-2018-19-vanarama-national-league-fixtures-released)
for The Hive London, Soccerbase's dated manager history for John Still, and
[Historical Football Kits' Barnet history](https://historicalkits.co.uk/Barnet/Barnet.htm)
for its explicitly labelled 2018/19 home-kit illustration. The factory-style
render approximates the illustrated amber/orange shirt and black shorts; it
does not reproduce the honeycomb graphic, commercial logos or original illustration.
Original reference files remain local-only; acknowledgement does not grant
redistribution rights.

Historical FIFA numerical snapshots are credited to EA Sports and
[SoFIFA](https://sofifa.com/). The locally retained legacy catalogue covers
FIFA15–23; exact published name plus date of birth is required for rating
matches. Later-season proxies and unsourced editorial estimates are labelled
as estimates, not contemporary EA ratings or historical facts. A rating-only
update preserves the known-good game's identities, squads, tactics, managers,
artwork and unrelated native bytes; immutable plans and complete-source replay
receipts make the change reproducible. This acknowledgement does not grant
redistribution rights to the catalogue or images.

Official club sources are also credited: [Maccabi Tel Aviv's player archive](https://www.maccabi-tlv.co.il/en/team/page/52/)
and [FC Viktoria Plzeň's dated match reports](https://www.fcviktoria.cz/zapas.asp?id=2879)
support the two distinct Tal Ben Haim identities in 2015/16. Original URLs and
raw page hashes are retained; this does not imply permission to redistribute
the publishers' text or images.

[Wikipedia contributors](https://en.wikipedia.org/) are also credited for
independently cross-checked player biographies and senior career spans. Original
article URLs and content hashes are retained locally. A year strictly inside an
unambiguous playing spell can support a reserve's club membership; boundary
years, loans, managerial roles and exact transfer dates are not inferred from
those spans. Wikipedia text is licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); individual media
have separate licences. This source adapter is tested, not a claim that every
historical roster or player portrait has been verified.

Hyde's 2013/14 ground and colour review also credits the club's official
26 April 2014 programme, preserved by
[Hatters Heritage](https://cdn.hattersheritage.co.uk/2013-14%2BSeason%2BDONE%2FMatches%2FM5210%2BHyde%2Bv%2BLuton%2BTown%2FProgramme%2FProgramme.pdf),
and Wikipedia's [2013/14 Conference stadium table](https://en.wikipedia.org/wiki/2013%E2%80%9314_Football_Conference).
The generated kit approximates the observed colour families; it does not copy
the programme photographs or commercial artwork. The original scan remains
local-only, and this credit does not grant redistribution permission.

These acknowledgements do not grant redistribution rights to source images or
proprietary game files. Local source snapshots, playable game assets and backups
remain untracked. See the current
[independent roster review](docs/ALL_26_INDEPENDENT_ROSTER_REVIEW_2026-10-05.md)
for verification scope and remaining queues.
