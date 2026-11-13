# JSON storage consumer decisions

The adapter inventory in `data/json-storage-consumers-v2.json` records mechanical
adoption, not certification of every historical workflow. The regression guard
checks direct Path I/O, builtin open, native atomic publication and common
copy/link calls. It does not prove that shell code or external programs accept
logical paths. See `JSON_STORAGE_HANDOVER_2026-11-13.md` for the measured rollout,
activation scope, tests and recovery instructions.

| Consumer | Decision |
| --- | --- |
| Pipeline/package/registry JSON inputs, canonical descriptors and artifact hashes | Logical decoded bytes and original JSON filenames; preserve canonical validation and immutable no-overwrite rules. |
| Workbook recipe discovery, preview, editing and candidate selection | Logical JSON discovery; bounded preview; full decode only when the selected recipe needs parsing. |
| Amendment publisher and SOURCE reconstruction | Logical input recipes, saved plans and inherited artifacts; native game cloning remains physical. Normalize compressed names in prepared-workspace metadata discovery. |
| Physical archive member verification | Use `storage_io.physical_sha256_file` on actual member paths, not registry input hashing (which deliberately decodes JSON frames). Literal logical archive inputs are resolved with `physical_path` before choosing member names. |
| Legacy `rg` retirement guard | Scan both representations with `find_json_reference`, including references across chunk boundaries; unreadable, ambiguous or corrupt metadata aborts retirement. No archive job is run by this rollout. |
| Generic I/O in the 1,082 declared production Python modules | Dispatch `.json` through the shared adapter; other files and ordinary objects retain native calls. Plain-to-plain copying/renaming remains native. |
| Atomic `os.replace`/`os.rename` in those modules | Explicit adapter entry points; preserve the existing compressed representation, leave plain/binary paths native. Mutable control documents stay plain. |
| Optional verified-link dedup of replay artifacts | Compare decoded hashes as before. Skip inode sharing when either side is compressed. Never hardlink a frame into a temporary filename that will be published as plain JSON. |
| Game tree inventories, compiler output trees and archive member inventories | Physical names, sizes and bytes. Explicit `.json.zst` paths in the generic adapter are physical. Do not change an inventory hash to make a logical input pass. |
| Generic `glob('*')`, `os.walk` and directory iteration | Reviewed separately: most are game assets, archive inventories or `/proc`; they remain physical. Workbook and prepared SOURCE metadata discovery normalize JSON explicitly. |
| `archive_superseded_2004_probes_20261017.py` reference guard | Scan both representations logically when checking retained SOURCE references; archive members remain physical. |
| `pm99_hourly_update_v1.sh` | Its direct coverage-matrix-current.json input stays plain under the shared policy. |
| Legacy shell/embedded Python, jq, external tools, upstream products and NAS mirrors | No universal certification. Keep their runtime/control roots outside migration/automatic activation. Audit a concrete new family before enabling it. |

Evidence under `.local/json-storage-rollout-20261113/` includes the remaining
native-I/O audit, generic discovery audit, optional dedup fixes, real-shape
restore rehearsal, Sonnet reviews and the actual batch journals. They are local
evidence and are not repository assets.

The deployment tested here is this laptop's POSIX filesystem. No NAS transfer
or mirror-format change is performed by this work. A future NAS deployment must
verify advisory locking and the codec on its actual filesystem.
