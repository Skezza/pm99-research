#!/usr/bin/env python3
"""Stage hash-bound PM99 name corrections from a provenance sidecar.

Only the tightly defined ``#<number> <name>`` opening-lineup parser defect is
eligible.  The raw captured text remains in the provenance sidecar; this
command stages a replacement for ``player.name`` only, never rewrites a source
package or a PM99 database.  Existing human edits always win: a conflicting
change is an error rather than something this batch can replace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import season_manifest_amendments as amendments  # noqa: E402
from scripts import season_name_provenance_v1 as provenance  # noqa: E402


SCHEMA = "pm99-season-number-label-name-amendment-stage-v1"
REASON = "Remove rendered squad-number label accidentally included in player name."


class NameAmendmentError(ValueError):
    """The provenance evidence cannot safely become an amendment."""


def _read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NameAmendmentError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise NameAmendmentError(f"{label} must be a JSON object")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_rows(sidecar: Mapping[str, Any]) -> list[dict[str, Any]]:
    if sidecar.get("schema_version") != provenance.SCHEMA:
        raise NameAmendmentError(f"provenance must use {provenance.SCHEMA}")
    rows = sidecar.get("players")
    if not isinstance(rows, list):
        raise NameAmendmentError("provenance.players must be a list")
    selected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping) or row.get("status") != "source-row-linked":
            continue
        component = row.get("component_candidate")
        if not isinstance(component, Mapping) or component.get("source_number_label_stripped") is not True:
            continue
        replacement = component.get("proposed_display_name")
        expected = row.get("canonical_name")
        captured = row.get("captured_source")
        if (
            not isinstance(replacement, str)
            or not replacement.strip()
            or not isinstance(expected, str)
            or not expected.strip()
            or not isinstance(captured, Mapping)
            or not isinstance(row.get("player_id"), str)
        ):
            raise NameAmendmentError("number-label candidate is malformed")
        if replacement == expected:
            raise NameAmendmentError("number-label candidate does not change the package name")
        selected.append(dict(row))
    return selected


def stage(
    *, package: Mapping[str, Any], package_sha256: str, manifest_id: str,
    sidecar: Mapping[str, Any], document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Merge strictly compatible generated changes into one amendment document."""

    package_binding = sidecar.get("package")
    if not isinstance(package_binding, Mapping):
        raise NameAmendmentError("provenance lacks package binding")
    if package_binding.get("sha256") != provenance._json_sha256(package):
        raise NameAmendmentError("provenance was built from a different package document")
    season = str(sidecar.get("season") or "")
    if document.get("season") != season:
        raise NameAmendmentError("amendment document targets a different season")
    players = package.get("players")
    if not isinstance(players, list):
        raise NameAmendmentError("package.players must be a list")
    player_index = {
        str(player.get("id")): index
        for index, player in enumerate(players)
        if isinstance(player, Mapping) and isinstance(player.get("id"), str)
    }
    result = dict(document)
    stats = {
        "candidate_count": 0,
        "staged_count": 0,
        "refreshed_evidence_count": 0,
        "already_staged_count": 0,
    }
    sidecar_sha256 = provenance._json_sha256(sidecar)
    for row in _candidate_rows(sidecar):
        stats["candidate_count"] += 1
        player_id = str(row["player_id"])
        if player_id not in player_index:
            raise NameAmendmentError(f"candidate player is not in package: {player_id}")
        index = player_index[player_id]
        expected = str(row["canonical_name"])
        replacement = str(row["component_candidate"]["proposed_display_name"])
        package_player = players[index]
        if not isinstance(package_player, Mapping) or package_player.get("name") != expected:
            raise NameAmendmentError(f"package name changed since provenance capture: {player_id}")
        pointer = f"/players/{index}/name"
        captured = row["captured_source"]
        evidence = (
            f"{provenance.SCHEMA}:{sidecar_sha256}:{player_id}:"
            f"{captured['source_path']}#{captured['source_row_index']}"
        )
        existing = next(
            (
                change for change in result["changes"]
                if change["manifest_id"] == manifest_id and change["json_pointer"] == pointer
            ),
            None,
        )
        if existing is not None:
            if existing["expected"] == expected:
                if (
                    existing["reason"] == REASON
                    and isinstance(existing.get("evidence"), str)
                    and existing["evidence"].startswith(f"{provenance.SCHEMA}:")
                ):
                    # A prior run of this exact generator may only have had
                    # the polluted opening label. A later concrete squad
                    # re-capture can improve case/particle spelling; replace
                    # that generator-owned value, never a human amendment.
                    if existing["set"] != replacement or existing["evidence"] != evidence:
                        existing["set"] = replacement
                        existing["evidence"] = evidence
                        stats["refreshed_evidence_count"] += 1
                        continue
                if existing["set"] == replacement:
                    stats["already_staged_count"] += 1
                    continue
            raise NameAmendmentError(
                f"existing editorial change conflicts with generated repair: {player_id} {pointer}"
            )
        result = amendments.stage_change(
            result,
            manifest_id=manifest_id,
            manifest_sha256=package_sha256,
            json_pointer=pointer,
            expected=expected,
            replacement=replacement,
            reason=REASON,
            evidence=evidence,
        )
        stats["staged_count"] += 1
    return result, stats


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--manifest-id", required=True)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--amendments", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Write the amended working document.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        package = _read(args.package, label="package")
        sidecar = _read(args.provenance, label="provenance")
        season = str(sidecar.get("season") or "")
        document = amendments.load_or_empty(args.amendments, season=season)
        updated, stats = stage(
            package=package,
            package_sha256=_file_sha256(args.package),
            manifest_id=args.manifest_id,
            sidecar=sidecar,
            document=document,
        )
        result = {"schema_version": SCHEMA, "season": season, **stats, "applied": bool(args.apply)}
        if args.apply and (stats["staged_count"] or stats["refreshed_evidence_count"]):
            amendments.write_document(args.amendments, updated)
    except (NameAmendmentError, amendments.AmendmentError) as exc:
        raise SystemExit(f"stage-number-label-name-amendments: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
