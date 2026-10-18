# 2015/16 English 92 face-coverage closeout

## Result

The 2015/16 English 92-club build now has an intentional minifoto outcome for
every player.  It no longer leaves any of the seventeen identified gaps showing
an unrelated 1998 carrier portrait.

The release audit for
`english92-2015-16-build36-native-no-photo` reports:

| Outcome | Players |
| --- | ---: |
| Authentic, identity-checked portrait | 2,294 |
| Intentionally no photo | 6 |
| Unresolved | 0 |
| Total dispositioned | 2,300 |

The six no-portrait records deliberately use PM99's native no-photo state. It
is an explicit, per-player decision with review evidence, not an invented face,
a borrowed photo or a synthetic silhouette.

## The seventeen former gaps

Eleven records now use a manually reviewed, sourced portrait.  The source and
crop information is retained in the face receipt and the local source ledger;
the build is reproducible from that ledger.

- Mike Phenix (Barnsley)
- Ryan Jennings (Wigan Athletic)
- Matty Stevens (Barnet)
- Matt Partridge and Lewis Moore (Dagenham & Redbridge)
- Frazer Shaw and Freddy Moncur (Leyton Orient)
- Iffy Allen and Jamie Burrows (Yeovil Town)
- Marvin McCoy and Reece Thompson (York City)

The remaining six records are Ben Ledger, Lee Marshall, Jordan Chiedozie,
Peter Denton, Joe Green and James Needle.  They are explicitly marked
`intentionally-no-photo` in the receipt. No long, speculative web hunt
was used for these marginal historical records.

## Release guardrail

The face builder accepts two—and only two—approved outcomes:

1. `applied`: an identity-checked portrait, optionally with a recorded source
   crop; or
2. `intentionally-no-photo`: a reviewed no-photo decision and a reason.

It rejects an unresolved record when `--require-complete` is used. The release
audit separately reports authentic portraits and reviewed no-photo records, so
a future build cannot quietly turn an unresolved player into a false claim of
full photography coverage.

Focused builder tests and the full release audit both pass.  The final
`MINIFOTO.PKF` SHA-256 is
`3d253b2933dd4539721414b23c005f2e32975e61b7cf5a98c76a61f0a2bf9eae`.

The harder archive case was also proven in a fresh runner game: Swindon Town's
Lee Marshall opens normally with an empty portrait area after his existing
archive directory entry is disabled. The screenshot is retained with the
runner artefacts as `062_profile_open_13.png`.

## One data-quality follow-up

The source ledger for Lee Marshall contains a 1997 date of birth, whereas
contemporaneous and later trusted player profiles indicate 21 November 1996.
That is a player-data correction, not a face-coverage fix, so it has not been
silently changed in this closeout.  It belongs in the normal historical-data
QA queue.
