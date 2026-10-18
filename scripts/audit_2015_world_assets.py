#!/usr/bin/env python3
"""Build a deterministic, source-only 2015/16 world asset candidate manifest.

The world source draft and player reconciliation are deliberately upstream of
this report.  This command joins their *identity-safe* rows to local compact
kit archive records and to explicitly supplied portrait receipts/caches.  It
does not claim that a base kit is the historic kit, and it never substitutes a
portrait from another carrier.  A FIFA16 URL is therefore a candidate only;
an ``applied`` receipt with a matching FIFA player id is the only portrait
state counted as an approved cached output.  Missing evidence remains an
explicit native-no-photo/needs-source decision for editorial review.

No PM99 file is written or modified.  The output itself is canonical JSON and
contains hashes for all inputs so a later asset stage can be reproduced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records  # noqa: E402


SCHEMA = "pm99-world-2015-asset-candidate-manifest-v1"
RECYCLE_SCHEMA = "pm99-world-2015-mode1-recycle-allocation-v1"
PLAYER_RECONCILIATION_SCHEMAS = {
    "pm99-world-2015-source-player-reconciliation-v1",
    "pm99-world-2015-ntf-integrated-source-package-v1",
}
KIT_ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
KIT_NAME_RE = re.compile(r"^EQ96(?P<id>\d{4})\.BMP$", re.IGNORECASE)
PORTRAIT_RECEIPT_NAME = "face-stage-receipt.json"


class AssetAuditError(ValueError):
    """Input source or cache cannot be represented safely."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetAuditError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise AssetAuditError(f"{label} must be a JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _relative_or_absolute(path: Path, root: Path | None) -> str:
    resolved = path.resolve()
    if root is not None:
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return str(resolved)


def load_kit_records(dbdat: Path) -> tuple[dict[str, dict[int, dict[str, Any]]], dict[str, str]]:
    """Read compact kit records and return metadata keyed by carrier id.

    The archive filename is the only carrier relationship proven by this
    audit.  Raw bitmap hashes make changed local artwork visible without
    storing or rewriting proprietary archive bytes in the report.
    """

    records: dict[str, dict[int, dict[str, Any]]] = {}
    hashes: dict[str, str] = {}
    for archive_name in KIT_ARCHIVES:
        path = dbdat / archive_name
        if not path.is_file():
            raise AssetAuditError(f"missing kit archive: {path}")
        hashes[archive_name] = sha256_file(path)
        by_id: dict[int, dict[str, Any]] = {}
        for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$"):
            match = KIT_NAME_RE.fullmatch(str(record.file_name))
            if match is None:
                raise AssetAuditError(f"unexpected compact kit filename: {record.file_name}")
            carrier_id = int(match.group("id"))
            if carrier_id in by_id:
                raise AssetAuditError(f"duplicate {archive_name} compact kit carrier id {carrier_id}")
            by_id[carrier_id] = {
                "file_name": str(record.file_name),
                "bitmap_length": int(record.bitmap_length),
                "bitmap_sha256": hashlib.sha256(record.raw_bitmap).hexdigest(),
            }
        records[archive_name] = by_id
    return records, hashes


def load_portrait_receipts(paths: Iterable[Path]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Index explicit face-stage receipts by FIFA player id.

    Receipts are accepted only when the row is ``applied`` or explicitly
    ``intentionally-no-photo``.  A receipt's carrier/record id is retained as
    provenance but is never used to map an image to a different player.
    """

    indexed: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for path in sorted({Path(item).resolve() for item in paths}, key=str):
        receipt, digest = _read_json(path, "portrait receipt")
        hashes[str(path)] = digest
        rows = receipt.get("rows")
        if not isinstance(rows, list):
            raise AssetAuditError(f"portrait receipt rows must be a list: {path}")
        for row in rows:
            if not isinstance(row, dict):
                continue
            fifa_id = str(row.get("fifa16_player_id") or row.get("portrait_player_id") or "").strip()
            status = str(row.get("status") or "")
            if not fifa_id or status not in {"applied", "intentionally-no-photo"}:
                continue
            prior = indexed.get(fifa_id)
            candidate = {
                "status": "cached-approved-era" if status == "applied" else "native-no-photo",
                "receipt": _relative_or_absolute(path, None),
                "source_url": str(row.get("source_url") or ""),
                "source_image_path": str(row.get("source_image_path") or ""),
                "preview_path": str(row.get("preview_path") or ""),
                "record_id": row.get("record_id"),
                "storage": row.get("storage"),
            }
            # Keep the strongest identity-safe state deterministically.  A
            # cached output outranks an explicit no-photo note only when both
            # receipts name the same FIFA id and the output is independently
            # applied; duplicate applied rows must still have distinct source
            # receipts so the candidate remains auditable.
            if prior is None or (prior["status"] == "native-no-photo" and status == "applied"):
                indexed[fifa_id] = candidate
    return indexed, hashes


def _kit_manifest_row(
    carrier_id: int, kit_records: Mapping[str, Mapping[int, Mapping[str, Any]]]
) -> dict[str, Any]:
    archives: dict[str, Any] = {}
    present = 0
    for archive_name in KIT_ARCHIVES:
        record = dict((kit_records.get(archive_name) or {}).get(carrier_id) or {})
        if record:
            present += 1
            archives[archive_name] = {"status": "base-art-present-not-era-approved", **record}
        else:
            archives[archive_name] = {"status": "base-art-missing"}
    if present == len(KIT_ARCHIVES):
        status = "needs-era-source"
    elif present:
        status = "base-art-partial-needs-era-source"
    else:
        status = "base-art-missing-needs-era-source"
    return {
        "status": status,
        "policy": "never-inherit-base-kit-as-complete-era-kit",
        "archives": archives,
    }


def _portrait_row(
    row: Mapping[str, Any], portrait_receipts: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    fifa = row.get("fifa16") if isinstance(row.get("fifa16"), dict) else {}
    fifa_id = str(fifa.get("fifa16_player_id") or "").strip()
    url = str(fifa.get("fifa16_headshot_url") or "").strip()
    cached = portrait_receipts.get(fifa_id) if fifa_id else None
    if cached is not None:
        status = str(cached.get("status"))
        candidate = dict(cached)
        if status == "cached-approved-era":
            candidate["source_policy"] = "identity-matched-receipt-only"
        else:
            candidate["source_policy"] = "explicit-native-no-photo-receipt"
    elif url:
        status = "fifa16-url-candidate"
        candidate = {
            "source_url": url,
            "source_policy": "candidate-only-download-and-review-required",
        }
    else:
        status = "needs-identity-safe-era-source"
        candidate = {
            "source_policy": "no-fifa16-identity-safe-source; native-no-photo-review-required",
        }
    return {
        "slot_index": int(row.get("slot_index") or 0),
        "player_carrier_id": int(row.get("player_carrier_id") or 0),
        "name": str((row.get("source_player") or {}).get("name") or ""),
        "source_squad_index": int(row.get("source_squad_index") or 0),
        "fifa16_player_id": int(fifa_id) if fifa_id.isdigit() else None,
        "fifa16_name": str(fifa.get("fifa16_name") or ""),
        "fifa16_match_status": str(fifa.get("status") or ""),
        "portrait": {"status": status, **candidate},
    }


def build_asset_manifest(
    *,
    draft: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    kit_records: Mapping[str, Mapping[int, Mapping[str, Any]]],
    portrait_receipts: Mapping[str, Mapping[str, Any]] | None = None,
    recycle_allocation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if draft.get("schema_version") != "pm99-world-2015-source-carrier-drafts-v1":
        raise AssetAuditError("draft schema is not source-carrier-drafts-v1")
    if reconciliation.get("schema_version") not in PLAYER_RECONCILIATION_SCHEMAS:
        raise AssetAuditError("reconciliation schema is unsupported")
    remaps: dict[tuple[int, int], Mapping[str, Any]] = {}
    if recycle_allocation is not None:
        if recycle_allocation.get("schema_version") != RECYCLE_SCHEMA:
            raise AssetAuditError("recycle allocation schema is unsupported")
        for allocation in recycle_allocation.get("allocations", []):
            if not isinstance(allocation, dict):
                raise AssetAuditError("recycle allocation contains a malformed row")
            key = (int(allocation.get("recycle_team_carrier_id") or 0), int(allocation.get("recycle_team_slot_index") or 0))
            if key in remaps:
                raise AssetAuditError(f"duplicate recycle allocation target {key}")
            remaps[key] = allocation
    proposals = draft.get("proposals")
    plans = reconciliation.get("carrier_plans")
    if not isinstance(proposals, list) or not isinstance(plans, list):
        raise AssetAuditError("draft proposals and reconciliation carrier_plans must be lists")
    by_plan: dict[int, Mapping[str, Any]] = {}
    for plan in plans:
        if not isinstance(plan, dict):
            raise AssetAuditError("reconciliation has malformed carrier plan")
        carrier_id = int(plan.get("carrier_id") or 0)
        if carrier_id in by_plan:
            raise AssetAuditError(f"duplicate reconciliation carrier id {carrier_id}")
        by_plan[carrier_id] = plan

    clubs: list[dict[str, Any]] = []
    portrait_counts: Counter[str] = Counter()
    kit_counts: Counter[str] = Counter()
    selected_slots = 0
    for proposal in sorted((item for item in proposals if isinstance(item, dict)), key=lambda item: int(item.get("carrier_id") or 0)):
        carrier_id = int(proposal.get("carrier_id") or 0)
        source_ready = proposal.get("status") == "source-squad-ready"
        plan = by_plan.get(carrier_id)
        players: list[dict[str, Any]] = []
        if source_ready:
            if plan is None:
                raise AssetAuditError(f"source-ready carrier {carrier_id} has no reconciliation plan")
            raw_rows = plan.get("rows")
            if not isinstance(raw_rows, list):
                raise AssetAuditError(f"carrier {carrier_id} reconciliation rows must be a list")
            expected = int(proposal.get("fixed_roster_slot_count") or 0)
            if len(raw_rows) != expected:
                raise AssetAuditError(f"carrier {carrier_id} reconciliation rows {len(raw_rows)} != fixed slots {expected}")
            players = sorted(
                (_portrait_row(row, portrait_receipts or {}) for row in raw_rows if isinstance(row, dict)),
                key=lambda item: (item["slot_index"], item["player_carrier_id"]),
            )
            for player in players:
                allocation = remaps.get((carrier_id, int(player["slot_index"])))
                if allocation is None:
                    continue
                old_carrier_id = int(player["player_carrier_id"])
                expected_old = int(allocation.get("old_shared_mode1_carrier_id") or 0)
                if old_carrier_id != expected_old:
                    raise AssetAuditError(
                        f"recycle allocation for carrier {carrier_id} slot {player['slot_index']} "
                        f"expects shared player {expected_old}, observed {old_carrier_id}"
                    )
                player["player_carrier_id"] = int(allocation["new_foreign_player_carrier_id"])
                player["recycled_from_shared_player_carrier_id"] = old_carrier_id
                player["recycle_allocation"] = {
                    "mode0_source_team_carrier_id": int(allocation["mode0_source_team_carrier_id"]),
                    "appended_mode0_clone_carrier_id": int(allocation["appended_mode0_clone_carrier_id"]),
                    "required_primary_fine_role_code": int(allocation["required_primary_fine_role_code"]),
                }
            if len(players) != len(raw_rows):
                raise AssetAuditError(f"carrier {carrier_id} has malformed reconciliation player row")
            selected_slots += len(players)
            portrait_counts.update(str(row["portrait"]["status"]) for row in players)
        kit = _kit_manifest_row(carrier_id, kit_records)
        kit_counts.update([kit["status"]])
        clubs.append({
            "carrier_id": carrier_id,
            "baseline_name": str(proposal.get("baseline_name") or ""),
            "group": proposal.get("group"),
            "source_status": proposal.get("status"),
            "source_country_catalog": proposal.get("source_country_catalog"),
            "source_club_name": proposal.get("source_club_name"),
            "source_selector": proposal.get("source_selector"),
            "fixed_roster_slot_count": int(proposal.get("fixed_roster_slot_count") or 0),
            "kit": kit,
            "players": players,
        })

    final_player_ids: dict[int, tuple[int, int]] = {}
    for club in clubs:
        for player in club["players"]:
            player_id = int(player["player_carrier_id"])
            location = (int(club["carrier_id"]), int(player["slot_index"]))
            prior = final_player_ids.get(player_id)
            if prior is not None:
                raise AssetAuditError(
                    f"final player carrier {player_id} remains shared by {prior} and {location}; "
                    "recycle allocation must run before asset materialisation"
                )
            final_player_ids[player_id] = location

    source_ready_count = sum(1 for row in clubs if row["source_status"] == "source-squad-ready")
    return {
        "schema_version": SCHEMA,
        "season": "2015-16",
        "result": "source-only-asset-candidates; not-release-ready",
        "policy": {
            "kit": "base archive presence is not historic identity; no inherited wrong-club kit may satisfy complete carrier",
            "portrait": "approved era-correct identity-matched receipt or explicit native-no-photo; never random carrier substitution",
            "scope": "no EXE, FDI, PKF or release DB writes",
        },
        "coverage": {
            "foreign_carrier_count": len(clubs),
            "source_squad_ready_carrier_count": source_ready_count,
            "source_squad_ready_fixed_slot_count": selected_slots,
            "unique_final_player_carrier_count": len(final_player_ids),
            "recycled_player_carrier_count": len(remaps),
            "kit_status_counts": dict(sorted(kit_counts.items())),
            "portrait_status_counts": dict(sorted(portrait_counts.items())),
            "portrait_candidate_url_count": portrait_counts["fifa16-url-candidate"],
            "portrait_cached_approved_count": portrait_counts["cached-approved-era"],
            "portrait_native_no_photo_count": portrait_counts["native-no-photo"],
            "portrait_needs_identity_safe_source_count": portrait_counts["needs-identity-safe-era-source"],
        },
        "clubs": clubs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--kit-dbdat", type=Path, required=True)
    parser.add_argument("--portrait-receipt", type=Path, action="append", default=[])
    parser.add_argument("--recycle-allocation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        draft, draft_hash = _read_json(args.draft, "source carrier draft")
        reconciliation, reconciliation_hash = _read_json(args.reconciliation, "source player reconciliation")
        recycle_allocation, recycle_allocation_hash = _read_json(args.recycle_allocation, "mode-1 recycle allocation")
        kit_records, kit_hashes = load_kit_records(args.kit_dbdat)
        portrait_records, portrait_hashes = load_portrait_receipts(args.portrait_receipt)
        result = build_asset_manifest(
            draft=draft,
            reconciliation=reconciliation,
            kit_records=kit_records,
            portrait_receipts=portrait_records,
            recycle_allocation=recycle_allocation,
        )
    except AssetAuditError as exc:
        parser.error(str(exc))
    result["sources"] = {
        "draft": {"path": str(args.draft.resolve()), "sha256": draft_hash},
        "reconciliation": {"path": str(args.reconciliation.resolve()), "sha256": reconciliation_hash},
        "recycle_allocation": {"path": str(args.recycle_allocation.resolve()), "sha256": recycle_allocation_hash},
        "kit_archives": {
            archive: {"path": str((args.kit_dbdat / archive).resolve()), "sha256": kit_hashes[archive]}
            for archive in KIT_ARCHIVES
        },
        "portrait_receipts": {
            path: {"sha256": digest} for path, digest in sorted(portrait_hashes.items())
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps({"output": str(args.output), **result["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
