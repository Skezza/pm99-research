# Legacy Archive Overview

This directory replaces the abandoned `unsorted/` drop and captures only the
legacy artifacts that are still useful for tracing the reverse-engineering
history of the project. Canonical design and usage notes continue to live under
`docs/`, while these files offer historical context or raw data captures.

* `verify.txt` preserves the original before/after hexdumps that were used to
  confirm the XOR decoding routine. These snapshots remain valid because the
  decoding helper in `pm99_editor.xor` still performs the same length-prefixed
  0x61 transformation that the game uses.【F:pm99_editor/xor.py†L6-L74】
* `breadcrumbs.csv` keeps the RVAs collected from the Windows binaries so that
  future static-analysis passes can be re-run without repeating the initial
  string search effort.【F:docs/archive/breadcrumbs.csv†L1-L5】
* The stand-alone decoder script that earlier notes referenced now lives under
  `scripts/decode_one.py`; it mirrors the helper in the package and is handy for
  one-off validation when reviewing unfamiliar records.【F:scripts/decode_one.py†L1-L118】
* Success summaries for the coach CLI remain relevant and have been rewritten to
  point at the current implementations. Earlier claims about a player editor,
  parser status, and various handovers were out of date; concise stubs now point
  readers back to maintained documentation and the audit below.

For a detailed breakdown of which legacy documents were kept, rewritten or
retired, see [UNSORTED_AUDIT.md](UNSORTED_AUDIT.md).
