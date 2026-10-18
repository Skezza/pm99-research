# World 2015 V2 package projection

`build_2015_world_v2_package_projection.py` converts the enriched 317-carrier
source candidate into a hash-locked V2 feasibility receipt. It joins portrait
materialisation by `(carrier_id, slot_index)`, rather than the stale player ID,
then declares the final remapped player carrier ID. The receipt therefore has
6,819 unique final player IDs, 30 allocation edges, 3,458 applied portraits
and 3,361 explicit native-no-photo decisions.

No non-empty strict `pm99-season-package-v2` is emitted yet. This is a real
current schema/runtime limit, not a missing serialization step:

- V2 requires every `club.manager_id` to resolve to an ENT carrier, and the
  compiler always writes that EQ link. Dated manager names do not identify a
  safe ENT record.
- The compiler always rewrites ground/capacity when compiling a club, despite
  those fields being optional in the metadata schema. Evidence is deliberately
  not promoted to permanent ground/capacity.
- V2 requires a reviewed artifact-backed kit set for every club.
- Six players lack DOB and 26 lack a source shirt number; existing shirt data
  is preserve-only but the V2/player compiler contract has no per-field
  preserve operation.

The projection explicitly reports these blockers and records maximum
compileable scope as zero rather than fabricating manager IDs, grounds,
capacities, kits, dates or shirt numbers. It never writes a PM99 binary.

The V2 contract now has explicit mode-1 preserve forms for manager links,
ground/capacity and kits. The compiler skips those declared lanes (and records
their preservation status) rather than defaulting values. Player fact fields
also accept the explicit preserve object; compiler rejects it on mode 0 or an
unknown policy. It also fails closed until a per-field native reader/writer
plan is registered: it never falls back to preserving an entire player record,
which would discard source-complete name/stat writes. The remaining compiler
work is to split dd6360's coupled role/core setter and prove before/after
field ranges for each preserved value.
