# Reviewed country recipe corrections

`scripts/season_authored_country_delta_v1.py` applies a reviewed country slice
to an immutable playable parent using the existing editor writers. It contains
no season, club or player-specific corrections. The input pins the parent,
child recipe, original evidence and authoring receipt by hash.

The child recipe owns the names, facts, ratings, managers, club identities and
opening selections. Compilation is not historical verification: dated membership
and person sources must be reviewed separately. Original source identities must
remain available when the game's display name needs a published short form.

The adapter retains the country's complete set of player carriers and every
club's squad size. Explicit carrier exchanges within that country can accommodate
long surnames; they must agree with the recipe's ownership and roster links.
Name capacity recovery uses the same record's original factory window and an
exact reversible shrink proof. It cannot borrow another record's opaque fields
or expand beyond proven capacity. Unrelated native records, recipes and kits are
preserved. Replaced identities can have stale portraits disabled; unchanged
portrait declarations remain intact.

Foreign shirt numbers and native tactics remain preserve-only where no proven
writer exists. A source/editorial formation in a mode-1 recipe does not mean its
native tactics were rewritten. Record that distinction in the bound authoring
receipt. Missing physical facts use explicit preserved-value declarations.

Use `prepare` to produce the checked transaction, pass that transaction to the
existing historical-delta publisher, then use SOURCE reconstruction to compare
the complete recipe and game inventory. Validate the affected fields by native
readback and inspect genuine runner captures before promotion. The first corpus
test covers the twelve Irish clubs in the 2017 release; a built candidate is not
automatically an installed release candidate.
