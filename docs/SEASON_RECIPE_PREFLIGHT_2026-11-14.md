# Reusable season source preflight

This is the first executable step of the reviewed generator plan, not a recipe generator or an RC approval. It measures cached source inputs against all 543 Native slots (451 foreign and 92 English). It never changes a recipe, game, release registry or preferred selection.

```bash
./pm99-season preflight 1990-91 --output-dir .local/my-1990-preflight
./pm99-season preflight 1990-91 --lock .local/my-1990-preflight/input-lock.json \
  --output-dir .local/my-1990-replay
```

Use a new output directory each time. Exit 3 means the measurement succeeded but full D1 remains incomplete; exit 2 means invalid inputs or a failed lock. Exit 3 is not permission to build an historically approved recipe. The lock covers source bytes, scope selectors, explicit parser dependencies, Python/Unicode/BeautifulSoup versions and measured report bytes. Changed inputs require a new unlocked measurement; existing evidence is never overwritten.

Outputs:

- `source-capture.json`: normalized observed squad rows, with provider identities and source provenance. Annual membership does not prove opening ownership.
- `preflight.json`: complete Native slot denominator, separate source/crosswalk/identity gaps, title validation and measured coverage.
- `input-lock.json`: inputs and expected report hash for offline replay.
- `fetch-requests.json`: missing cache keys and source URLs, not an automatic unlimited scraper.

Matching only proposes exact case/spacing-equivalent foreign club names inside the Native family. It never approves historical club identity. English allocations are division-capacity proposals, including all twelve non-picker slots. Provider IDs are retained; same names without identity evidence are not merged. Cross-club annual occurrences are candidates, not proven duplicate bugs.

Optional bounded probes use explicit flags. Manager requests are capped at four, one per sampled country, with time/size bounds, a one-second interval and no access-control bypass or retries. An HTTP error is recorded as an access failure, not evidence that a manager is historically unknowable. A locked replay uses cached successes/failures and does not request the network.

```bash
PM99_PYTHON=.local/venvs/season-pipeline/bin/python ./pm99-season preflight 1990-91 \
  --output-dir .local/my-1990-source-proof \
  --probe-managers 2 --snapshot-date 1990-08-31 \
  --probe-cache-root .local/source-cache/season-preflight-manager-probe-v1 \
  --database .local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb \
  --pinned-receipt .local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json
```

For replay, retain these flags and add `--lock` with a new output directory. DuckDB is optional and read-only, version/hash pinned before and after. This measures source coverage; it does not derive ownership from sparse events. The snapshot date is an explicit source query, not a newly imposed universal August cutoff.

Storage follows the inline JSON contract: logical names/hashes through shared adapters, physical source database hashes, immutable plain new evidence, no compression-root activation or decompressed cache. The 26 preferred games and original 2015 are outside this command's writes.

The next implementation must obtain dated ownership and manager evidence where these measured sources cannot supply it, establish an evidenced club crosswalk, and then author a complete recipe with targeted editable gaps. Do not feed annual transfer-related repeat appearances into an automatic player-removal rule. D2/D3 and historical RC closure remain separate milestones.

Local QA and actual replay evidence: `.local/generator-d1-20261114/`. Sonnet reviewed the scope and implementation; Luna audited source availability; Terra reviewed the contract and implementation. Model agreement is supplementary to executable tests and replay proof.

## Measured 1990/91 result

The completed revised capture is `.local/generator-d1-20261114/accepted-A/`. It contains 154 distinct parsed squad pages, 3,718 player rows, all with provider IDs, representing 3,588 unique player IDs. No page was double counted through repeated scope observations. There are 68 English capacity proposals, one foreign exact-name candidate, 85 explicitly unmatched source-club observations and 19 pending fetch requests. These deliberately conservative matching counts do not mean the other historical clubs lack web data. No historical club identity or opening ownership is certified.

The existing pinned DuckDB has zero transfers in each of 1989, 1990 and 1991 and zero target-season games. It cannot resolve 1990 opening ownership. Two bounded manager samples (Leicester and Lyon) returned HTTP 405, recorded as access failures. Neither observation licenses invented facts or an unavailable-evidence closure.

Initial Sonnet implementation review found three measurement defects: English proposals mixed with foreign matches, unmatched sources not separately exposed, and obsolete alias misses on the fetch list. All three were corrected and regression-tested. Terra's earlier title/dependency-lock concerns were corrected, including a regression for historical competition retirement dates in provider titles. Earlier `measured-A`, `source-proof-A` and `final-A/B` are retained as superseded evidence, not current results. The final handoff in CURRENT_WORK records replay and final QA status.

## Final validation and bounded limitations

`accepted-A` and locked offline `accepted-B` have byte-identical logical hashes for all four outputs. The source script hash matches its lock. Preflight/storage tests: 82 passed; existing squad/calendar/identity tests: 68 passed. Consumer guard and repository boundary pass. Preferred catalogue SHA remains `495789e1691b9c792ddd53e4fb1eedeb107593bef7776a20a1886b44c10efd2b`.

Actual Sonnet 5.5 recheck session `2d6e03d5-a8b3-4c38-a248-be83d95aeb84` accepted this bounded measurement with limitations. Its whole-file read of the large report exceeded its read limit, and it looked for logs in the wrong subdirectory; the lead independently checked the actual logs, parsed counts, locked script hash and complete replay hashes. See `qa-summary.json`, `replay-proof.json`, all three `sonnet-*-report.md` reviews and corresponding raw session events. Do not represent this as Sonnet having inspected every player row.

Remaining nonblocking limitations: unidentified same-name observations can repeat if the same page is referenced by two scopes (all actual captured rows here have provider IDs); matching counts describe slots rather than distinct source clubs; cached HTTP failures require a new cache root to retry; socket timeouts are not a total wall-clock deadline. Malformed optional receipts can produce a traceback; partial output directories are retained and require a new destination. These are not historical facts to infer or reasons to claim D1 complete. The parser uses Python `html.parser`; lxml is not selected dynamically. Replay requires repeating the original flags; the lock is a verification contract rather than a self-running job description.
