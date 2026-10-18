#!/usr/bin/env python3
"""Discover and retain revision-pinned Wikipedia home-kit sources by season.

Only exact, mechanically derived season-page titles are queried. A resolved
page is accepted only when its season and normalised club identity match one
carrier allocation. Missing evidence is a gap, never a guessed kit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_kit_catalogue_v1 as catalogue_v1

SCHEMA = "pm99-season-kit-source-capture-v1"
CHUNK_PLAN_SCHEMA = "pm99-season-kit-source-chunk-plan-v1"
USER_AGENT = "pm99-research/season-kit-source-capture-v1 (+local historical game mod)"
LEGAL_TOKENS = {"a", "ac", "afc", "as", "bc", "bk", "calcio", "cd", "cf", "club", "de", "fc", "fk", "football", "fussball", "futbol", "if", "nk", "rc", "rfc", "sc", "sk", "ss", "ssc", "sv", "ud", "vfb"}
LEGAL_FORMS = ("{name}", "{name} F.C.", "{name} FC", "FC {name}", "{name} C.F.", "{name} CF", "CF {name}", "{name} A.F.C.", "{name} AFC", "A.C. {name}", "AC {name}", "A.S. {name}", "S.S. {name}", "S.S.C. {name}", "SC {name}", "{name} SC")


class KitCaptureError(ValueError):
    """Allocation or source resolution does not satisfy the strict contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return catalogue_v1.canonical_json_bytes(value)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _ascii_tokens(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+", folded)


def club_identity(value: str) -> str:
    # Dotted legal suffixes (F.C., A.C., S.S.C.) tokenize into single letters.
    return "".join(token for token in _ascii_tokens(value) if len(token) > 1 and token not in LEGAL_TOKENS)


def season_title_identity(title: str, start_year: int, end_year: int) -> str | None:
    folded = unicodedata.normalize("NFKD", title.replace("–", "-").replace("—", "-"))
    folded = folded.encode("ascii", "ignore").decode("ascii")
    short = str(end_year)[-2:]
    patterns = (
        rf"^\s*{start_year}\s*-\s*{short}\s+(.+?)\s+season\s*$",
        rf"^\s*(.+?)\s+{start_year}\s*-\s*{short}\s+season\s*$",
    )
    for pattern in patterns:
        match = re.match(pattern, folded, flags=re.IGNORECASE)
        if match:
            return club_identity(match.group(1))
    return None


def title_candidates(club_name: str, start_year: int, end_year: int) -> list[str]:
    short = str(end_year)[-2:]
    names = [form.format(name=club_name.strip()) for form in LEGAL_FORMS]
    # English Wikipedia football season articles use the year-first en-dash
    # convention. MediaWiki title normalisation and redirects cover legacy
    # ASCII spellings without multiplying requests.
    return list(dict.fromkeys(f"{start_year}\u2013{short} {name} season" for name in names))


def _season(allocation: Mapping[str, Any]) -> dict[str, Any]:
    label = str((allocation.get("season") or {}).get("label") or "")
    match = re.match(r"^(\d{4})/(\d{2})(?:\s|$)", label)
    if not match:
        raise KitCaptureError("allocation season.label must be YYYY/YY")
    start, end = int(match.group(1)), int(match.group(1)) + 1
    if str(end)[-2:] != match.group(2):
        raise KitCaptureError("allocation season label is not consecutive")
    return {"start_year": start, "end_year": end, "label": f"{start}/{str(end)[-2:]}"}


def _requested_clubs(allocation: Mapping[str, Any]) -> list[dict[str, Any]]:
    assignments = allocation.get("assignments")
    if not isinstance(assignments, list):
        raise KitCaptureError("allocation assignments must be a list")
    rows = []
    for row in assignments:
        carrier, name = row.get("carrier_id"), row.get("club_name")
        if not isinstance(carrier, int) or carrier <= 0 or not isinstance(name, str) or not name.strip():
            raise KitCaptureError("every allocation requires a positive carrier_id and club_name")
        rows.append({"carrier_id": carrier, "club_name": name.strip()})
    rows.sort(key=lambda row: row["carrier_id"])
    if len({row["carrier_id"] for row in rows}) != len(rows):
        raise KitCaptureError("allocation carrier ids must be unique")
    return rows


def fetch_exact_title_batch(language: str, titles: list[str], *, timeout: int = 30) -> list[dict[str, Any]]:
    data = urllib.parse.urlencode({"action": "query", "titles": "|".join(titles), "redirects": "1", "prop": "revisions", "rvslots": "main", "rvprop": "content|ids|timestamp", "format": "json", "formatversion": "2"}).encode("utf-8")
    request = urllib.request.Request(f"https://{language}.wikipedia.org/w/api.php", data=data, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS host
                document = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else float(2 ** (attempt + 1))
            time.sleep(min(delay, 30.0))
    else:  # pragma: no cover - defensive, loop either breaks or raises
        raise KitCaptureError(str(last_error))
    pages = []
    for page in ((document.get("query") or {}).get("pages") or []):
        revisions = page.get("revisions") or []
        if page.get("missing") is True or len(revisions) != 1:
            continue
        revision = revisions[0]
        wikitext = str(((revision.get("slots") or {}).get("main") or {}).get("content") or "")
        if not wikitext.strip():
            continue
        title = str(page.get("title") or "")
        pages.append({"language": language, "page_id": int(page["pageid"]), "page_title": title, "page_url": f"https://{language}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}", "revision_id": int(revision["revid"]), "revision_timestamp": str(revision["timestamp"]), "wikitext": wikitext})
    return pages


def fetch_season_prefix_titles(language: str, start_year: int, end_year: int, *, timeout: int = 30) -> list[str]:
    """List canonical year-prefixed pages without downloading article bodies."""
    prefix = f"{start_year}\u2013{str(end_year)[-2:]}"
    titles: list[str] = []
    continuation: dict[str, str] = {}
    while True:
        params = {"action": "query", "list": "allpages", "apprefix": prefix, "apnamespace": "0", "aplimit": "max", "format": "json", "formatversion": "2", **continuation}
        request = urllib.request.Request(f"https://{language}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS host
                    document = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == 4:
                    raise
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else float(3 * (attempt + 1))
                time.sleep(min(delay, 30.0))
        titles.extend(str(row["title"]) for row in ((document.get("query") or {}).get("allpages") or []) if row.get("title"))
        if "continue" not in document:
            break
        continuation = {key: str(value) for key, value in document["continue"].items()}
    return titles


def _prefix_titles_cache(cache_dir: Path, language: str, start_year: int, end_year: int, titles: list[str] | None = None) -> list[str] | None:
    key = f"{language}-{start_year}-{end_year}"
    index_path = cache_dir / "season-prefix-index" / f"{key}.json"
    if titles is None:
        if not index_path.is_file():
            return None
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            object_path = cache_dir / str(index["relative_path"])
            payload = object_path.read_bytes()
            if sha256_bytes(payload) != index.get("sha256"):
                return None
            value = json.loads(payload.decode("utf-8"))
            return [str(item) for item in value["titles"]]
        except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
            return None
    payload = canonical_json_bytes({"language": language, "start_year": start_year, "end_year": end_year, "titles": list(titles)})
    digest = sha256_bytes(payload)
    object_path = cache_dir / "season-prefixes" / digest[:2] / f"{digest}.json"
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if not object_path.exists():
        object_path.write_bytes(payload)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(canonical_json_bytes({"sha256": digest, "relative_path": str(object_path.relative_to(cache_dir))}))
    return list(titles)


def discover(allocation: Mapping[str, Any], *, allow_network: bool, batch_fetcher: Callable[[str, list[str]], list[dict[str, Any]]] | None = None, chunk_size: int = 40, cache_dir: Path | None = None) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    season, clubs = _season(allocation), _requested_clubs(allocation)
    fetcher = batch_fetcher or fetch_exact_title_batch
    candidates = list(dict.fromkeys(title for club in clubs for title in title_candidates(club["club_name"], season["start_year"], season["end_year"])))
    pages_by_id: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    discovery_complete = False
    if batch_fetcher is None:
        prefix_titles = _prefix_titles_cache(cache_dir, "en", season["start_year"], season["end_year"]) if cache_dir is not None else None
        if prefix_titles is None and allow_network:
            # Listing the canonical year prefix is both more complete and far
            # gentler on MediaWiki than probing thousands of absent variants.
            # Identity is still accepted only by the exact matcher below.
            try:
                prefix_titles = fetch_season_prefix_titles("en", season["start_year"], season["end_year"])
                if cache_dir is not None:
                    _prefix_titles_cache(cache_dir, "en", season["start_year"], season["end_year"], prefix_titles)
            except Exception as exc:
                errors.append(f"prefix-list-{type(exc).__name__}: {exc}")
                prefix_titles = None
        if prefix_titles is not None:
            discovery_complete = True
            try:
                identities = {club_identity(club["club_name"]) for club in clubs}
                matched_titles = [title for title in prefix_titles if season_title_identity(title, season["start_year"], season["end_year"]) in identities]
                uncached_titles = []
                for title in matched_titles:
                    source = {"provider": catalogue_v1.WIKI_PROVIDER, "language": "en", "page_title": title}
                    cached = catalogue_v1._read_cached_wikipedia(cache_dir, source) if cache_dir is not None else None
                    if cached is None:
                        uncached_titles.append(title)
                    else:
                        pages_by_id[int(cached["page_id"])] = cached
                chunks = [uncached_titles[offset : offset + chunk_size] for offset in range(0, len(uncached_titles), chunk_size)] if allow_network else []
            except Exception as exc:
                errors.append(f"prefix-cache-{type(exc).__name__}: {exc}")
                chunks = []
            for chunk in chunks:
                try:
                    for page in fetcher("en", chunk):
                        pages_by_id[int(page["page_id"])] = page
                        if cache_dir is not None:
                            source = {"provider": catalogue_v1.WIKI_PROVIDER, "language": "en", "page_title": page["page_title"]}
                            catalogue_v1._write_cached_wikipedia(cache_dir, source, page)
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                time.sleep(0.5)
    elif allow_network:
        if batch_fetcher is not None:
            discovery_complete = True
            chunks = [candidates[offset : offset + chunk_size] for offset in range(0, len(candidates), chunk_size)]
            for chunk in chunks:
                try:
                    for page in fetcher("en", chunk):
                        pages_by_id[int(page["page_id"])] = page
                        if cache_dir is not None:
                            source = {"provider": catalogue_v1.WIKI_PROVIDER, "language": "en", "page_title": page["page_title"]}
                            catalogue_v1._write_cached_wikipedia(cache_dir, source, page)
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
    selected: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for club in clubs:
        identity = club_identity(club["club_name"])
        matches = [page for page in pages_by_id.values() if season_title_identity(str(page["page_title"]), season["start_year"], season["end_year"]) == identity]
        matches.sort(key=lambda page: (str(page["page_title"]), int(page["page_id"])))
        if len(matches) == 1:
            page = matches[0]
            selected[club["carrier_id"]] = page
            parsed = catalogue_v1._parse_wikipedia_home_kit(str(page["wikitext"]))
            status = "revision-captured-home-fields-ready" if parsed.get("status") == "home-kit-fields-ready" else "revision-captured-home-fields-missing"
            rows.append({**club, "status": status, "page_title": page["page_title"], "page_id": page["page_id"], "revision_id": page["revision_id"], "parse_status": parsed.get("status")})
        elif matches:
            rows.append({**club, "status": "blocked-ambiguous-season-pages", "candidate_page_titles": [page["page_title"] for page in matches]})
        else:
            rows.append({**club, "status": "blocked-no-exact-season-page" if discovery_complete else "blocked-network-disabled"})
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    ledger = {"schema_version": SCHEMA, "season": season, "provenance": {"allocation_sha256": sha256_bytes(canonical_json_bytes(dict(allocation)))}, "policy": {"discovery": "mechanically-derived-exact-titles-only", "identity": "season-and-normalised-club-identity-must-match-exactly", "fallback": "none-for-allocated-carriers", "attribution": "Wikipedia contributors; retained page revision and licence terms apply"}, "coverage": {"allocated_club_count": len(clubs), "candidate_title_count": len(candidates), "unique_page_count": len(pages_by_id), "status_counts": dict(sorted(counts.items())), "batch_error_count": len(errors)}, "batch_errors": errors, "rows": rows}
    return ledger, selected


def materialise(allocation: Mapping[str, Any], *, output_dir: Path, cache_dir: Path, allow_network: bool, batch_fetcher: Callable[[str, list[str]], list[dict[str, Any]]] | None = None, provenance_extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    ledger, selected = discover(allocation, allow_network=allow_network, batch_fetcher=batch_fetcher, cache_dir=cache_dir)
    if provenance_extra:
        ledger["provenance"].update(dict(provenance_extra))
    request_rows = []
    for club in _requested_clubs(allocation):
        page = selected.get(club["carrier_id"])
        source = None
        if page is not None:
            source = {"provider": catalogue_v1.WIKI_PROVIDER, "language": "en", "page_title": page["page_title"]}
            catalogue_v1._write_cached_wikipedia(cache_dir, source, page)
        request_rows.append({**club, "carrier_status": "continuing", "source": source})
    request = {"schema_version": catalogue_v1.REQUEST_SCHEMA, "season": ledger["season"], "clubs": request_rows}
    catalogue = catalogue_v1.build_catalogue(request, cache_dir=cache_dir, allow_network=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kit-source-capture-v1.json").write_bytes(canonical_json_bytes(ledger))
    (output_dir / "kit-catalogue-request-v1.json").write_bytes(canonical_json_bytes(request))
    (output_dir / "kit-catalogue-v1.json").write_bytes(canonical_json_bytes(catalogue))
    return {"capture": ledger["coverage"], "catalogue": catalogue["coverage"]}


def _allocation_paths(path: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    if path.is_file():
        return [(path, {})]
    pointers = sorted(path.glob("*/current.json"))
    if pointers:
        resolved = []
        for pointer_path in pointers:
            pointer_bytes = pointer_path.read_bytes()
            pointer = json.loads(pointer_bytes.decode("utf-8"))
            if pointer.get("schema_version") != "pm99-historical-squad-backfill-current-v1":
                raise KitCaptureError(f"unsupported historical current pointer: {pointer_path}")
            artifact = (pointer.get("artifacts") or {}).get("allocation") or {}
            relative = artifact.get("path")
            expected = artifact.get("sha256")
            if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts or not isinstance(expected, str):
                raise KitCaptureError(f"unsafe allocation pointer: {pointer_path}")
            allocation_path = pointer_path.parent / relative
            actual = hashlib.sha256(allocation_path.read_bytes()).hexdigest()
            if actual != expected:
                raise KitCaptureError(f"allocation pointer hash mismatch: {pointer_path}")
            resolved.append((allocation_path, {"historical_revision_id": pointer.get("revision_id"), "historical_current_sha256": hashlib.sha256(pointer_bytes).hexdigest(), "historical_allocation_file_sha256": actual}))
        return resolved
    return [(item, {}) for item in sorted(path.glob("*/carrier-allocation.json"))]


def _chunk_plan_provenance(plan_path: Path, allocation: Mapping[str, Any]) -> dict[str, Any]:
    """Bind one new source capture to a frozen allocation subset plan.

    This intentionally accepts no generic user-controlled provenance mapping:
    a plan must itself be canonical, hash-bind the exact subset, and retain a
    readable complete allocation.  That makes isolated source chunks safe to
    scale without allowing a later cache to masquerade as a fresh capture.
    """
    try:
        if plan_path.is_symlink() or not plan_path.is_file():
            raise KitCaptureError(f"chunk plan must be a regular file: {plan_path}")
        payload = plan_path.read_bytes()
        plan = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KitCaptureError(f"chunk plan is not valid JSON: {exc}") from exc
    if not isinstance(plan, Mapping) or canonical_json_bytes(plan) != payload or plan.get("schema_version") != CHUNK_PLAN_SCHEMA:
        raise KitCaptureError(f"chunk plan must be canonical {CHUNK_PLAN_SCHEMA}")
    subset = plan.get("subset_allocation")
    full = plan.get("full_allocation")
    selection = plan.get("selection")
    if not isinstance(subset, Mapping) or not isinstance(full, Mapping) or not isinstance(selection, Mapping):
        raise KitCaptureError("chunk plan lacks allocation or selection provenance")
    allocation_sha = sha256_bytes(canonical_json_bytes(dict(allocation)))
    if subset.get("sha256") != allocation_sha:
        raise KitCaptureError("chunk plan does not bind this exact subset allocation")
    selected = selection.get("selected_carrier_ids")
    selected_assignments_sha = selection.get("selected_assignments_sha256")
    requested = _requested_clubs(allocation)
    requested_ids = [row["carrier_id"] for row in requested]
    if not isinstance(selected, list) or selected != requested_ids or selected != sorted(selected) or not isinstance(selected_assignments_sha, str):
        raise KitCaptureError("chunk plan selected carriers do not exactly match subset allocation")
    assignments = allocation.get("assignments")
    if not isinstance(assignments, list) or selected_assignments_sha != sha256_bytes(canonical_json_bytes(assignments)):
        raise KitCaptureError("chunk plan selected assignment hash is stale")
    full_path_text, full_sha = full.get("path"), full.get("sha256")
    if not isinstance(full_path_text, str) or not isinstance(full_sha, str):
        raise KitCaptureError("chunk plan full allocation provenance is malformed")
    full_path = Path(full_path_text)
    try:
        if full_path.is_symlink() or not full_path.is_file() or sha256_bytes(full_path.read_bytes()) != full_sha:
            raise KitCaptureError("chunk plan full allocation is unavailable or hash-stale")
    except OSError as exc:
        raise KitCaptureError(f"chunk plan full allocation is unavailable: {exc}") from exc
    return {
        "full_allocation_path": str(full_path.resolve()),
        "full_allocation_sha256": full_sha,
        "chunk_plan": {"path": str(plan_path.resolve()), "sha256": sha256_bytes(payload)},
        "chunk_assignments_sha256": selected_assignments_sha,
        "chunk_carrier_ids": selected,
        "stale_capture_reuse": "prohibited-fresh-cache-created-for-this-chunk",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("allocation", type=Path, help="one carrier-allocation.json or a season-batch root")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--skip-existing", action="store_true", help="leave seasons with an existing catalogue untouched")
    parser.add_argument("--chunk-plan", type=Path, help="canonical plan binding one exact subset allocation")
    args = parser.parse_args()
    inputs = list(_allocation_paths(args.allocation))
    if not inputs:
        parser.error("no carrier-allocation.json inputs found")
    if args.chunk_plan is not None and len(inputs) != 1:
        parser.error("--chunk-plan requires exactly one allocation input")
    summary = {}
    for path, origin in inputs:
        allocation = json.loads(path.read_text(encoding="utf-8"))
        if args.chunk_plan is not None:
            origin = {**origin, **_chunk_plan_provenance(args.chunk_plan, allocation)}
        label = _season(allocation)["label"].replace("/", "-")
        capture_path = args.output_root / label / "kit-source-capture-v1.json"
        if args.skip_existing and (args.output_root / label / "kit-catalogue-v1.json").is_file() and capture_path.is_file():
            try:
                retained = json.loads(capture_path.read_text(encoding="utf-8"))
                current_hash = sha256_bytes(canonical_json_bytes(dict(allocation)))
                retained_provenance = retained.get("provenance", {})
                if retained_provenance.get("allocation_sha256") == current_hash and all(retained_provenance.get(key) == value for key, value in origin.items()):
                    summary[label] = {"status": "skipped-existing-verified-allocation-hash", "allocation_sha256": current_hash}
                    continue
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        summary[label] = materialise(allocation, output_dir=args.output_root / label, cache_dir=args.cache_dir, allow_network=args.allow_network, provenance_extra=origin)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
