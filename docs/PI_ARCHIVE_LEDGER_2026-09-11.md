# Pi archive ledger

This ledger records PM99RE material copied to the anonymous Raspberry Pi SMB
archive.  A local original is removed only after the destination has been
verified byte-for-byte against the source using `rsync --checksum` and the
entry has been completed below.

| Date | Source | Pi destination | Classification | Files | Source size | Verification | Local disposition |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| 2026-09-11 | `.local/season-preview-builds-v1` | `smb://raspberrypi-2.local/HDD/pm99-archive/packages/historical-preview-builds/season-preview-builds-v1` | historical preview outputs; not referenced by current scripts, docs, or operations status | 11,469 | 9,280,464,393 bytes | `rsync -rltcni` exited 0 with no reported differences, 2026-09-12 | local original removed after verification, 2026-09-12 |

## Pre-existing archive baseline

These locations were already present when the Pi archive was reconnected on
2026-09-11.  They are recorded for discovery and retrieval, but their historic
copy receipts and hashes have **not** yet been revalidated by this ledger.

| Pi location | Classification | Ledger status |
| --- | --- | --- |
| `backups/bentley-sd-20260902` | verified Bentley SD backup lineage | pre-existing; receipt review pending |
| `backups/runlogs` | historical run logs | pre-existing |
| `evidence/repo-artifacts` | repository evidence | pre-existing |
| `evidence/research-probes` | research-probe evidence | pre-existing |
| `incoming/2015-superseded-20260902` | superseded 2015 build intake | pre-existing |
| `incoming/research-probes-20260902` | research-probe intake | pre-existing |
| `incoming/secondary-20260902` | secondary-source intake | pre-existing |
| `packages/2015-superseded-builds` | superseded 2015 builds | pre-existing |
| `packages/upscale-poc` | upscale proof-of-concept package | pre-existing |
| `receipts/2015-superseded-20260902` | 2015 archive receipts | pre-existing |
| `receipts/bentley-sd-20260902` | Bentley SD copy receipts | pre-existing |
| `receipts/overnight-watch-20260902` | historical watch receipts | pre-existing |
| `receipts/research-probes-20260902` | research-probe receipts | pre-existing |
| `receipts/secondary-20260902` | secondary archive receipts | pre-existing |

## Retrieval

Mount the Pi share anonymously with:

```bash
gio mount --anonymous smb://raspberrypi-2.local/HDD
```

The local GVFS path is
`/run/user/1000/gvfs/smb-share:server=raspberrypi-2.local,share=hdd`.
