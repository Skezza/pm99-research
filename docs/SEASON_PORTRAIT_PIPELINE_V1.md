# Season portrait pipeline V1

This pipeline produces era-appropriate PM99 minifotos without making portraits
a release blocker. It has been proved on the isolated 2014/15 pilot; it has not
been cascaded into the registered season releases.

## Historical and safety rules

- A player is matched by exact date of birth plus a compatible historical
  name. Club and name aliases help identify a candidate but never override a
  birth-date conflict.
- The image URL is tied to the declared FIFA edition. A current photograph is
  never used as a substitute for an unavailable historical one.
- Ambiguous, conflicting, missing and unavailable images become an explicit
  `native-no-photo` result. The inherited carrier portrait is disabled so that
  it cannot show the wrong person.
- The source CSV, package, plan, converted BMPs, application and validation are
  SHA-256 bound. Failed or incomplete work can be inspected without changing a
  registered release.
- Source images are shared in one cache. The output game uses hard links for
  unchanged files and detaches the portrait archive before modifying it.
- The materialiser checks free space and enforces a configurable local working
  limit. Keep the cache and receipts; previews are optional and disposable.

## Commands

The public entry point is `./pm99-season portraits`:

```bash
./pm99-season portraits plan 2014-15 \
  --edition-csv .local/season-2015-16/fifa15-sofifa-backfill.csv \
  --edition 15 \
  --output .local/season-portrait-pilots-v1/2014-15/portrait-plan.json

./pm99-season portraits fetch \
  --plan .local/season-portrait-pilots-v1/2014-15/portrait-plan.json \
  --minifoto <clean-game>/DBDAT/MINIFOTO.PKF \
  --cache-root .local/season-portrait-cache-v1 \
  --output-root .local/season-portrait-pilots-v1/2014-15/assets \
  --receipt .local/season-portrait-pilots-v1/2014-15/portrait-materialisation.json

./pm99-season portraits apply 2014-15 \
  --materialisation .local/season-portrait-pilots-v1/2014-15/portrait-materialisation.json \
  --output-game .local/season-portrait-pilots-v1/2014-15/game \
  --receipt .local/season-portrait-pilots-v1/2014-15/portrait-application.json

./pm99-season portraits validate \
  --materialisation .local/season-portrait-pilots-v1/2014-15/portrait-materialisation.json \
  --application .local/season-portrait-pilots-v1/2014-15/portrait-application.json \
  --game .local/season-portrait-pilots-v1/2014-15/game \
  --output .local/season-portrait-pilots-v1/2014-15/portrait-validation.json
```

Each command is deliberately resumable as a separate stage. Receipts are
immutable: use a new pilot/run directory when inputs or policy change rather
than overwriting prior evidence.

## 2014/15 proof

The first pilot dispositioned all 11,557 package players:

- 4,084 exact-edition portraits applied;
- 7,473 explicit no-photo outcomes;
- zero pending players;
- 11,557 application operations validated with zero issues.

The large no-photo count is expected at this stage: 6,777 players lacked one
unique exact identity in the FIFA 15 source, 696 exact-edition URLs were
unavailable, and duplicate-source safeguards rejected further unsafe matches.
This is coverage information, not permission to use a present-day or guessed
portrait.

Runtime evidence is under
`.local/runlogs/pm99_runner/portrait_pipeline_2014_15_stoke_profiles_20260915_r1`.
The runner completed successfully and captured ten Stoke City player profiles,
including visible era portraits for Asmir Begovic and Phillip Bardsley.

## Storage observed in the pilot

The shared source cache occupied about 175 MB and converted assets/previews
about 97 MB. The game directory reports a larger apparent size because it is a
complete runnable tree, but unchanged files are hard-linked to the registered
base. On the current filesystem the whole pilot left roughly 11 GB free.

Before scaling, the next candidate season should reuse the same cache and use a
new output directory. Once a second season passes both structural and runtime
validation, immutable source packages and receipts can be archived to the Pi;
local previews and failed HTTP bodies can then be removed safely.
