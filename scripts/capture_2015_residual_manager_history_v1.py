#!/usr/bin/env python3
"""Close the last 2015/16 target-manager source gaps from dated evidence.

This is a deliberately small, reviewed supplement to the broader manager
capture passes.  Each target has a declared historical club identity.  It
uses either an already-pinned Transfermarkt manager-history page or the
revision of an English Wikipedia club page at the 2015-09-01 season snapshot.
The command is source-only: it produces a hashable receipt and refuses a
different club name, a different published manager, or an ambiguous history.

The two English non-league carriers that are absent from the old foreign
source-candidate package are also explicit targets.  They are not guessed
from the native carrier label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_world_manager_history_v2 as wikipedia  # noqa: E402
from scripts import capture_2015_world_manager_transfermarkt_snapshot_v5 as transfermarkt  # noqa: E402
from scripts import capture_opening_manager_history_supplements_v1 as history  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402


SCHEMA = "pm99-world-2015-residual-manager-history-v1"
# The historical all-source candidate is the output of the deterministic
# editorial-rating composition pass.  It retains carrier drafts verbatim, so
# this source receipt binds to that exact, canonical input rather than a
# hand-copied club list.
CANDIDATE_SCHEMA = "pm99-world-2015-editorial-fallback-ratings-v1"
AS_OF = date(2015, 9, 1)
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


class ResidualManagerError(ValueError):
    """A reviewed residual source can no longer prove its declared fact."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


# ``kind: wikipedia`` declares the expected, historical infobox value.  This
# is not a fallback value: the command reads the dated revision and refuses to
# emit a row when the source differs.  GIF Sundsvall genuinely had joint head
# coaches; retaining both names is more accurate than silently choosing one.
#
# These are the only manager-source gaps left after the dated Wikipedia,
# Transfermarkt pinned-squad, exact-search and source-tail passes.  The
# manager names for Transfermarkt targets are deliberately parsed from the
# page rather than repeated here.
TARGETS: tuple[dict[str, Any], ...] = (
    {"carrier_id": 377, "club_name": "Doncaster Rovers", "kind": "wikipedia", "title": "Doncaster Rovers F.C.", "manager": "Paul Dickov"},
    {"carrier_id": 381, "club_name": "Hereford FC", "kind": "wikipedia", "title": "Hereford F.C.", "manager": "Peter Beadle"},
    {"carrier_id": 961, "club_name": "GIF Sundsvall", "kind": "wikipedia", "title": "GIF Sundsvall", "manager": "Joel Cedergren / Roger Franzén"},
    {"carrier_id": 1352, "club_name": "Start", "kind": "transfermarkt", "slug": "ik-start", "club_id": 267},
    {"carrier_id": 1355, "club_name": "Odd", "kind": "transfermarkt", "slug": "odds-bk", "club_id": 1058},
    {"carrier_id": 1556, "club_name": "Dukla Banska Bystrica", "kind": "transfermarkt", "slug": "dukla-banska-bystrica", "club_id": 4786},
    {"carrier_id": 1652, "club_name": "APOEL Lefkosias", "kind": "transfermarkt", "slug": "apoel-nikosia", "club_id": 2784},
    {"carrier_id": 1653, "club_name": "Omonia Lefkosias", "kind": "wikipedia", "title": "AC Omonia", "manager": "Kostas Kaiafas"},
    {"carrier_id": 1862, "club_name": "St Patrick's Athletic", "kind": "transfermarkt", "slug": "st-patricks-athletic", "club_id": 1189},
    {"carrier_id": 2005, "club_name": "FC Jazz Pori", "kind": "wikipedia", "title": "FC Jazz", "manager": "John Allen"},
    {"carrier_id": 2101, "club_name": "Maccabi Tel-Aviv", "kind": "transfermarkt", "slug": "maccabi-tel-aviv", "club_id": 119},
    {"carrier_id": 2104, "club_name": "Hapoel Tel-Aviv", "kind": "wikipedia", "title": "Hapoel Tel Aviv F.C.", "manager": "César Mendiondo"},
    {"carrier_id": 2753, "club_name": "Sporting Cristal Lima", "kind": "transfermarkt", "slug": "club-sporting-cristal", "club_id": 1450},
    {"carrier_id": 3102, "club_name": "Millonarios FC", "kind": "transfermarkt", "slug": "millonarios-fc", "club_id": 2350},
    {"carrier_id": 3312, "club_name": "Barrow", "kind": "transfermarkt", "slug": "afc-barrow", "club_id": 6168},
    {"carrier_id": 3318, "club_name": "Bromley", "kind": "transfermarkt", "slug": "fc-bromley", "club_id": 8981},
    {"carrier_id": 3323, "club_name": "Chester", "kind": "transfermarkt", "slug": "fc-chester", "club_id": 31367},
    {"carrier_id": 3330, "club_name": "Chorley FC", "kind": "wikipedia", "title": "Chorley F.C.", "manager": "Matt Jansen"},
    {"carrier_id": 4125, "club_name": "Neftchi Baku", "kind": "transfermarkt", "slug": "neftchi-baku", "club_id": 8031},
    {"carrier_id": 9006, "club_name": "Godoy Cruz (Mendoza)", "kind": "transfermarkt", "slug": "club-deportivo-godoy-cruz-antonio-tomba", "club_id": 12574},
    {"carrier_id": 9011, "club_name": "Independiente", "kind": "transfermarkt", "slug": "club-atletico-independiente", "club_id": 1234},
    {"carrier_id": 9013, "club_name": "Colón (Santa Fe)", "kind": "wikipedia", "title": "Club Atlético Colón", "manager": "Javier Lopez"},
    # The last English-Wikipedia revision before the snapshot was old enough
    # to be a weak assertion.  Use the club's dated Transfermarkt history
    # instead: it records Caruso Lombardi from 11 May to 26 November 2015,
    # which unambiguously covers the September opening snapshot.
    {"carrier_id": 9017, "club_name": "Arsenal", "kind": "transfermarkt", "slug": "arsenal-de-sarandi-fc", "club_id": 4673},
    {"carrier_id": 9019, "club_name": "Gimnasia y Esgrima (La Plata)", "kind": "transfermarkt", "slug": "club-de-gimnasia-y-esgrima-la-plata", "club_id": 1106},
    {"carrier_id": 9020, "club_name": "San Martín (San Juan)", "kind": "wikipedia", "title": "San Martín de San Juan", "manager": "Carlos Mayor"},
    {"carrier_id": 9027, "club_name": "Unión (Santa Fe)", "kind": "transfermarkt", "slug": "club-atletico-union", "club_id": 7097},
)


def _load_candidate(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResidualManagerError(f"cannot read source-candidate package: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ResidualManagerError("source-candidate package must be canonical JSON")
    if value.get("schema_version") != CANDIDATE_SCHEMA:
        raise ResidualManagerError(f"source-candidate package must use {CANDIDATE_SCHEMA}")
    return value, hashlib.sha256(raw).hexdigest()


def _candidate_clubs(candidate: Mapping[str, Any]) -> dict[int, str]:
    rows = candidate.get("carrier_drafts")
    if not isinstance(rows, list):
        raise ResidualManagerError("source-candidate package has no carrier drafts")
    result: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("carrier_id"), int):
            raise ResidualManagerError("source-candidate package has malformed carrier drafts")
        club = row.get("club")
        name = str((club or {}).get("source_club_name") or "").strip()
        if not name:
            continue
        result[int(row["carrier_id"])] = " ".join(name.split())
    return result


def _wikipedia_snapshot(target: Mapping[str, Any], cache: opening.SnapshotCache) -> dict[str, Any]:
    title = str(target["title"])
    query = {
        "action": "query", "format": "json", "formatversion": "2",
        "prop": "revisions", "rvprop": "ids|timestamp|content", "rvslots": "main",
        "rvstart": f"{AS_OF.isoformat()}T00:00:00Z", "rvdir": "older", "rvlimit": "1",
        "titles": title, "redirects": "1",
    }
    url = f"{WIKIPEDIA_API}?{urlencode(query)}"
    key = f"wikipedia/{int(target['carrier_id'])}.json"
    payload = cache.get(url, key)
    try:
        document = json.loads(payload.decode("utf-8"))
        pages = document["query"]["pages"]
        page = pages[0]
        revision = page["revisions"][0]
        content = revision["slots"]["main"]["content"]
    except (KeyError, IndexError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResidualManagerError("Wikipedia response has no one historical page revision") from exc
    if not isinstance(content, str):
        raise ResidualManagerError("Wikipedia historical revision has no wikitext")
    template = wikipedia._club_infobox(content)
    raw_manager = wikipedia._top_level_parameter(template or "", {"manager", "head coach", "coach"})
    observed = wikipedia._clean_wikitext(raw_manager or "")
    expected = str(target["manager"])
    if observed != expected:
        raise ResidualManagerError(
            f"Wikipedia historical manager differs from reviewed target: {observed!r} != {expected!r}"
        )
    snapshot = cache.used[key]
    return {
        "manager_name": expected,
        "published_manager_name": expected,
        "pm99_spelling_method": "published-wikipedia-historical-infobox-value",
        "source_name": "English Wikipedia historical club-page revision",
        "source_url": url,
        "source_snapshot_sha256": snapshot["sha256"],
        "source_page_title": str(page.get("title") or ""),
        "source_revision_id": revision.get("revid"),
        "source_revision_timestamp": revision.get("timestamp"),
        "reason": (
            "the declared manager infobox value is present in the latest published "
            f"revision at or before {AS_OF.isoformat()}"
        ),
    }


def _transfermarkt_snapshot(target: Mapping[str, Any], cache: opening.SnapshotCache) -> dict[str, Any]:
    club_id = int(target["club_id"])
    slug = str(target["slug"])
    url = f"{opening.BASE_URL}/{slug}/mitarbeiterhistorie/verein/{club_id}"
    key = f"managers/{int(target['carrier_id'])}-{club_id}.html"
    payload = cache.get(url, key)
    published_name, manager_id = history.manager_at_date(payload, AS_OF)
    if not transfermarkt._safe_manager_name(published_name):
        raise ResidualManagerError("published manager display name requires a reviewed PM99 Latin spelling")
    snapshot = cache.used[key]
    return {
        "manager_name": published_name,
        "published_manager_name": published_name,
        "pm99_spelling_method": "published-transfermarkt-display-name",
        "source_name": "Transfermarkt published club manager history",
        "source_url": url,
        "source_snapshot_sha256": snapshot["sha256"],
        "reason": (
            f"manager id {manager_id} uniquely covers the fixed {AS_OF.isoformat()} "
            "early-season snapshot for the declared historical club identity"
        ),
    }


def capture(*, candidate: Mapping[str, Any], candidate_sha256: str,
            transfermarkt_cache: opening.SnapshotCache,
            wikipedia_cache: opening.SnapshotCache) -> dict[str, Any]:
    candidate_clubs = _candidate_clubs(candidate)
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for target in TARGETS:
        carrier_id = int(target["carrier_id"])
        declared_name = str(target["club_name"])
        candidate_name = candidate_clubs.get(carrier_id)
        # 377/381 were consciously omitted from the foreign source candidate;
        # their target identities are declared above and remain independently
        # sourced.  Every other value must bind to the exact candidate club.
        if candidate_name is not None and candidate_name != declared_name:
            raise ResidualManagerError(
                f"carrier {carrier_id} target club conflicts with source candidate: "
                f"{declared_name!r} != {candidate_name!r}"
            )
        try:
            source = (
                _transfermarkt_snapshot(target, transfermarkt_cache)
                if target["kind"] == "transfermarkt"
                else _wikipedia_snapshot(target, wikipedia_cache)
            )
            rows.append({
                "carrier_id": carrier_id,
                "source_club_name": declared_name,
                "source_candidate_binding": (
                    "exact-source-candidate-club-name"
                    if candidate_name is not None else "declared-english-nonleague-target-not-in-foreign-source-candidate"
                ),
                "snapshot_as_of": AS_OF.isoformat(),
                "source_method": str(target["kind"]),
                **source,
            })
        except (OSError, ValueError, opening.CaptureError, history.ManagerHistoryError, ResidualManagerError) as exc:
            gaps.append({"carrier_id": carrier_id, "source_club_name": declared_name, "reason": str(exc)})
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; reviewed residual target identities only; latest published English Wikipedia "
            "club-page revision at or before 2015-09-01 or a uniquely covering Transfermarkt manager "
            "history at that date; no native/current-manager fallback"
        ),
        "sources": {
            "source_candidate_sha256": candidate_sha256,
            "transfermarkt_cache_files": [transfermarkt_cache.used[key] for key in sorted(transfermarkt_cache.used)],
            "wikipedia_cache_files": [wikipedia_cache.used[key] for key in sorted(wikipedia_cache.used)],
        },
        "coverage": {
            "residual_target_count": len(TARGETS),
            "dated_manager_match_count": len(rows),
            "unresolved_manager_count": len(gaps),
            "source_method_counts": dict(sorted(Counter(row["source_method"] for row in rows).items())),
            "unresolved_reason_counts": dict(sorted(Counter(row["reason"] for row in gaps).items())),
        },
        "rows": sorted(rows, key=lambda row: int(row["carrier_id"])),
        "gaps": sorted(gaps, key=lambda row: int(row["carrier_id"])),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-candidate", required=True, type=Path)
    parser.add_argument("--transfermarkt-cache-root", required=True, type=Path)
    parser.add_argument("--wikipedia-cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ResidualManagerError(f"refusing to overwrite source receipt: {args.output}")
        candidate, candidate_sha = _load_candidate(args.source_candidate)
        result = capture(
            candidate=candidate, candidate_sha256=candidate_sha,
            transfermarkt_cache=opening.SnapshotCache(
                args.transfermarkt_cache_root, offline=args.offline, delay=args.delay,
            ),
            wikipedia_cache=opening.SnapshotCache(
                args.wikipedia_cache_root, offline=args.offline, delay=args.delay,
                validator=lambda payload, _url: json.loads(payload.decode("utf-8")),
            ),
        )
    except (OSError, ResidualManagerError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
