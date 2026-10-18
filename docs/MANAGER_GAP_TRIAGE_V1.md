# Manager-gap triage V1

`season_manager_gap_triage_v1.py` is a read-only bridge between the selected
manager-overlay ledger and allocated-manager capture receipts.  It makes the
manager queue measurable without changing a package, ledger, source cache, or
database.

The receipt validates, per season:

- the current source and carrier-allocation artifacts named by `current.json`;
- the selected immutable overlay ledger and its audit from the overlay index;
- every `opening-manager-supplement*.json` in that season's operations
  directory; and
- that a usable raw capture is bound to exactly the current source hash and
  allocation hash.

For every selected-ledger manager gap that belongs to a fixed carrier, it uses
one exclusive classification:

| Classification | Meaning | Next action |
| --- | --- | --- |
| `already-captured-not-integrated` | One or more hash-bound dated receipts agree on manager and opening-fixture date. | Compose the listed selected-overlay inputs and raw receipt(s) into a *new* manager-overlay version. |
| `existing-dated-conflicting-candidate` | Valid dated receipts disagree on the manager or fixture date. | Make a source decision or recapture; do not automate an overlay. |
| `genuinely-uncaptured` | No valid dated manager is available for the current source/allocation pair. | Capture a dated source; manager fallback is forbidden. |

The report includes the first chronological safe one-season integration tranche
when one exists.  That is an instruction/receipt only: the triage command does
not write an overlay.  Any follow-on must create a new `manager-vN` directory;
it must never rewrite the selected overlay.

```bash
python3 scripts/season_manager_gap_triage_v1.py \
  --output .local/season-manager-gap-triage-v1/manager-gap-triage.json
```

Optional `--season YYYY-YY` arguments restrict the report to explicit current
pointers.  Inputs are reported as paths and SHA-256 values so a changed source,
allocation, overlay, or receipt cannot silently reuse the old conclusion.
