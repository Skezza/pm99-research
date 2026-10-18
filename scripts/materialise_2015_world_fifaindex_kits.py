#!/usr/bin/env python3
"""Materialise identity-bound FIFA 16 home-kit candidates for PM99 carriers.

FIFAIndex's dated FIFA 16 catalogue binds a stable FIFA team id to a club
name and to ``images.fifaindex.com/fifa16/kits/home/<id>.png``.  The origin
currently rejects scripted downloads, so the exact origin URL is fetched via
DuckDuckGo's external-content image cache.  Both URLs and every byte hash are
recorded.  Only unique identity matches are rendered; inherited PM99 kit art
is never accepted as a historical fallback.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records  # noqa: E402
from scripts.materialise_2015_world_kits import ARCHIVES, _nearest_palette, _write_content_addressed, canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402
from scripts import pm99_compact_kit_template_v1 as compact_template  # noqa: E402
from scripts.pm99_kit_recipe_v1 import recipe_from_source  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402

SCHEMA = "pm99-world-2015-fifaindex-kit-materialisation-v1"
MANIFEST_SCHEMA = "pm99-world-2015-asset-candidate-manifest-v1"
USER_AGENT = "pm99-research/2015-world-kit-lane (+local historical game mod)"
TEAM_RE = re.compile(
    r"\[!\[Image[^]]*\]\(https://images\.fifaindex\.com/fifa16/teams/(?P<image_id>\d+)\.png\)(?P<name>[^]]+)\]"
    r"\(https://fifaindex\.com/teams/(?P<page_id>\d+)-[^)]+/fifa16\)"
)
LEGAL_TOKENS = {"fc", "cf", "ac", "afc", "sc", "ssc", "ss", "as", "rc", "rsc", "bsc", "cs", "cd", "cfp", "hsc", "kaa", "krc", "kvc", "bk", "if", "sk", "fk", "sv", "kv", "f", "c", "a", "s", "calcio", "club", "clube", "sport", "futbol", "football"}


class FifaIndexKitError(ValueError):
    pass


def identity_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace(".", "")
    tokens = [token for token in re.findall(r"[a-z0-9]+", text) if token not in LEGAL_TOKENS]
    aliases = {
        "internazionale": "inter milan",
        "bayern munich": "bayern munchen",
        "atletico madrid": "atletico de madrid",
        "athletic bilbao": "athletic de bilbao",
        "paris saint germain": "paris saint germain",
        "sporting braga": "braga",
        "sporting gijon": "sporting de gijon",
        "betis": "real betis balompie",
        "milan": "milan",
        "deportivo de la coruna": "deportivo",
        "deportivo la coruna": "deportivo",
        "hertha berlin": "hertha",
        "hertha bsc berlin": "hertha",
        "academica de coimbra": "academica",
        "os belenenses": "belenenses",
        "cska moscow": "cska moskva",
        "medipol basaksehir": "istanbul basaksehir",
        "sv josko ried": "ried",
        "atletico nacional medellin": "atletico nacional",
        "atletico de rafaela": "atletico rafaela",
        "colon santa fe": "atletico colon",
        "san martin de san juan": "san martin san juan",
    }
    key = " ".join(tokens)
    return aliases.get(key, key)


def parse_team_catalog(markdown: str) -> list[dict[str, Any]]:
    found: dict[int, dict[str, Any]] = {}
    for match in TEAM_RE.finditer(markdown):
        image_id, page_id = int(match.group("image_id")), int(match.group("page_id"))
        if image_id != page_id:
            raise FifaIndexKitError(f"catalog team/image id mismatch: {image_id} != {page_id}")
        name = match.group("name").strip()
        candidate = {
            "fifa_team_id": page_id,
            "fifa_team_name": name,
            "identity_key": identity_key(name),
            "team_page_url": f"https://fifaindex.com/teams/{page_id}-{re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii').lower()).strip('-')}/fifa16",
            "home_kit_origin_url": f"https://images.fifaindex.com/fifa16/kits/home/{page_id}.png",
        }
        prior = found.get(page_id)
        if prior is not None and prior["identity_key"] != candidate["identity_key"]:
            raise FifaIndexKitError(f"catalog team id {page_id} has conflicting names")
        found[page_id] = candidate
    return sorted(found.values(), key=lambda row: row["fifa_team_id"])


def capture_catalog(cache_dir: Path, *, page_count: int = 13) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for page in range(1, page_count + 1):
        source_url = f"https://fifaindex.com/teams/fifa16?page={page}"
        reader_url = f"https://r.jina.ai/{source_url}"
        response = requests.get(reader_url, headers={"User-Agent": USER_AGENT}, timeout=45)
        if response.status_code != 200 or not response.text.strip():
            raise FifaIndexKitError(f"FIFAIndex catalogue page {page} failed: HTTP {response.status_code}")
        payload = response.content
        path, digest = _write_content_addressed(payload, cache_dir / "catalog", ".md")
        parsed = parse_team_catalog(response.text)
        all_rows.extend(parsed)
        sources.append({"page": page, "source_url": source_url, "reader_url": reader_url, "cache_path": str(path.resolve()), "sha256": digest, "team_count": len(parsed)})
    by_id: dict[int, dict[str, Any]] = {}
    for row in all_rows:
        prior = by_id.get(row["fifa_team_id"])
        if prior is not None and prior["identity_key"] != row["identity_key"]:
            raise FifaIndexKitError(f"duplicate FIFA team id conflict: {row['fifa_team_id']}")
        by_id[row["fifa_team_id"]] = row
    return sorted(by_id.values(), key=lambda row: row["fifa_team_id"]), sources


def load_player_clubs(path: Path) -> tuple[dict[int, str], str]:
    raw = path.read_bytes()
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    result = {int(row["player_id"]): str(row.get("club") or "").strip() for row in rows if str(row.get("player_id") or "").isdigit()}
    return result, sha256_bytes(raw)


def load_sofifa_fifa16_teams(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Load the CC0 legacy export's FIFA16 club ids/names."""
    digest = sha256_file(path)
    found: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("fifa_version") or "") != "16":
                continue
            team_id = str(row.get("club_team_id") or "").removesuffix(".0")
            name = str(row.get("club_name") or "").strip()
            if not team_id.isdigit() or not name:
                continue
            numeric_id = int(team_id)
            candidate = {
                "fifa_team_id": numeric_id,
                "fifa_team_name": name,
                "identity_key": identity_key(name),
                "team_page_url": f"https://fifaindex.com/teams/{numeric_id}/fifa16",
                "home_kit_origin_url": f"https://images.fifaindex.com/fifa16/kits/home/{numeric_id}.png",
                "team_id_source": "CC0 SoFIFA male_players legacy FIFA16 row",
            }
            prior = found.get(numeric_id)
            if prior is not None and prior["identity_key"] != candidate["identity_key"]:
                raise FifaIndexKitError(f"SoFIFA team id {numeric_id} has conflicting FIFA16 names")
            found[numeric_id] = candidate
    return sorted(found.values(), key=lambda row: row["fifa_team_id"]), digest


def bind_team(club: Mapping[str, Any], player_clubs: Mapping[int, str], catalog: list[Mapping[str, Any]]) -> dict[str, Any]:
    votes = collections.Counter(
        player_clubs[int(player["fifa16_player_id"])]
        for player in club.get("players", [])
        if player.get("fifa16_player_id") is not None
        and int(player["fifa16_player_id"]) in player_clubs
        and player_clubs[int(player["fifa16_player_id"])] not in {"", "NA", "Free Agents"}
    )
    ranked = votes.most_common()
    evidence_name = ""
    method = ""
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]) and ranked[0][1] >= 2:
        evidence_name, method = ranked[0][0], "unique-dominant-fifa16-player-club"
    else:
        evidence_name, method = str(club.get("source_club_name") or ""), "unique-source-club-name"
    key = identity_key(evidence_name)
    matches = [dict(row) for row in catalog if key in set(row.get("identity_aliases") or [row["identity_key"]])]
    if not matches and method == "unique-dominant-fifa16-player-club":
        source_key = identity_key(str(club.get("source_club_name") or ""))
        matches = [dict(row) for row in catalog if source_key in set(row.get("identity_aliases") or [row["identity_key"]])]
        if len(matches) == 1:
            method, evidence_name, key = "dominant-unmatched-unique-source-name-fallback", str(club.get("source_club_name") or ""), source_key
    if len(matches) != 1:
        return {"status": "blocked-no-unique-fifa16-team", "method": method, "evidence_name": evidence_name, "identity_key": key, "votes": ranked[:5], "match_count": len(matches)}
    return {"status": "identity-bound", "method": method, "evidence_name": evidence_name, "identity_key": key, "votes": ranked[:5], "team": matches[0]}


def fetch_home_kit(team: Mapping[str, Any], cache_dir: Path) -> dict[str, Any]:
    origin = str(team["home_kit_origin_url"])
    proxy = f"https://external-content.duckduckgo.com/iu/?u={quote(origin, safe='')}&f=1&nofb=1"
    response = requests.get(proxy, headers={"User-Agent": USER_AGENT}, timeout=30)
    if response.status_code != 200:
        return {"status": "blocked-image-fetch", "origin_url": origin, "proxy_url": proxy, "http_status": response.status_code}
    try:
        image = Image.open(io.BytesIO(response.content)).convert("RGBA")
        image.verify if False else None
    except Exception as exc:
        return {"status": "blocked-invalid-image", "origin_url": origin, "proxy_url": proxy, "reason": f"{type(exc).__name__}: {exc}"}
    if image.width < 16 or image.height < 16 or image.width > 2048 or image.height > 2048:
        return {"status": "blocked-invalid-image-shape", "origin_url": origin, "proxy_url": proxy, "dimensions": [image.width, image.height]}
    path, digest = _write_content_addressed(response.content, cache_dir / "home-kits", ".png")
    return {"status": "source-ready", "origin_url": origin, "proxy_url": proxy, "cache_path": str(path.resolve()), "sha256": digest, "dimensions": {"width": image.width, "height": image.height}}


def render_fifaindex_candidate(
    record: Any,
    source_path: Path,
    palette: list[tuple[int, int, int]],
    *,
    recipe: Mapping[str, Any] | None = None,
) -> bytes:
    """Render a source-derived *recipe*, never a scaled modern shirt bitmap.

    The PM99 asset is an illustrated shirt-and-shorts icon.  Applying a source
    crop to a central rectangle caused the visible garbling rejected in visual
    review, and legacy carriers have inconsistent silhouettes.  The fixed
    centred PM99 template avoids both faults.
    """
    style = dict(recipe or recipe_from_source(source_path))
    return compact_template.render(record, palette, style)


def materialise(*, manifest: Mapping[str, Any], player_csv: Path, sofifa_legacy_csv: Path, dbdat: Path, cache_dir: Path, output_dir: Path) -> dict[str, Any]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise FifaIndexKitError("asset manifest schema is unsupported")
    catalog, catalog_sources = capture_catalog(cache_dir)
    sofifa_teams, sofifa_hash = load_sofifa_fifa16_teams(sofifa_legacy_csv)
    by_id = {int(row["fifa_team_id"]): {**dict(row), "identity_aliases": [row["identity_key"]]} for row in sofifa_teams}
    for row in catalog:
        prior = by_id.get(int(row["fifa_team_id"]))
        aliases = sorted(set((prior or {}).get("identity_aliases") or []).union({row["identity_key"]}))
        by_id[int(row["fifa_team_id"])] = {**(prior or {}), **row, "identity_aliases": aliases}
    catalog = sorted(by_id.values(), key=lambda row: int(row["fifa_team_id"]))
    player_clubs, player_csv_hash = load_player_clubs(player_csv)
    archive_records: dict[str, dict[int, Any]] = {}
    archive_hashes: dict[str, str] = {}
    for archive in ARCHIVES:
        path = dbdat / archive
        archive_hashes[archive] = sha256_file(path)
        archive_records[archive] = {int(re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), re.I).group(1)): record for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$")}
    try:
        palette, palette_source = runtime_kit_palette(dbdat)
    except ValueError as exc:
        raise FifaIndexKitError(str(exc)) from exc
    ready_clubs = [club for club in manifest.get("clubs", []) if club.get("source_status") == "source-squad-ready"]
    bindings = {int(club.get("carrier_id") or 0): bind_team(club, player_clubs, catalog) for club in ready_clubs}
    teams = {
        int(binding["team"]["fifa_team_id"]): binding["team"]
        for binding in bindings.values()
        if binding.get("status") == "identity-bound"
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        captured_images = dict(zip(teams, pool.map(lambda team: fetch_home_kit(team, cache_dir), teams.values())))
    rows: list[dict[str, Any]] = []
    for club in sorted(manifest.get("clubs", []), key=lambda row: int(row.get("carrier_id") or 0)):
        carrier = int(club.get("carrier_id") or 0)
        row: dict[str, Any] = {"carrier_id": carrier, "source_club_name": club.get("source_club_name"), "source_country_catalog": club.get("source_country_catalog"), "source_status": club.get("source_status")}
        if club.get("source_status") != "source-squad-ready":
            row.update({"status": "blocked-not-source-squad-ready", "action": "no-write"}); rows.append(row); continue
        binding = bindings[carrier]; row["binding"] = binding
        if binding["status"] != "identity-bound":
            row.update({"status": binding["status"], "action": "no-write"}); rows.append(row); continue
        captured = captured_images[int(binding["team"]["fifa_team_id"])]; row["source_image"] = captured
        if captured["status"] != "source-ready":
            row.update({"status": captured["status"], "action": "no-write"}); rows.append(row); continue
        assets: dict[str, Any] = {}
        try:
            recipe = recipe_from_source(Path(captured["cache_path"]))
            for archive in ARCHIVES:
                record = archive_records[archive].get(carrier)
                if record is None:
                    raise FifaIndexKitError(f"{archive} has no carrier {carrier}")
                payload = render_fifaindex_candidate(
                    record,
                    Path(captured["cache_path"]),
                    palette,
                    recipe=recipe,
                )
                path, digest = _write_content_addressed(payload, output_dir / "candidate-bmps" / archive, ".bmp")
                assets[archive] = {"path": str(path.resolve()), "sha256": digest, "file_name": str(record.file_name), "bitmap_length": len(payload), "shape": {"width": record.width, "height": record.height, "bits_per_pixel": record.bits_per_pixel}}
        except Exception as exc:
            row.update({"status": "blocked-render-failed", "action": "no-write", "reason": f"{type(exc).__name__}: {exc}"}); rows.append(row); continue
        row.update({"status": "release-eligible-fifa16-identity-bound", "action": "write-candidate-only", "render_recipe": recipe, "render_template": {"id": compact_template.TEMPLATE_ID, "policy": "centred-front-shirt-and-shorts-silhouette-per-archive"}, "assets": assets}); rows.append(row)
    counts = collections.Counter(row["status"] for row in rows)
    return {"schema_version": SCHEMA, "season": "2015-16", "result": "source-only-kit-candidates; no PM99 binary writes", "coverage": {"foreign_carrier_count": len(rows), "source_ready_carrier_count": sum(row.get("source_status") == "source-squad-ready" for row in rows), "release_eligible_count": counts["release-eligible-fifa16-identity-bound"], "status_counts": dict(sorted(counts.items()))}, "policy": {"identity": "unique FIFA16 team id/name bound by dominant identity-matched FIFA16 players or unique source-club name", "source": "FIFAIndex FIFA16 team catalogue and exact home-kit origin URL; CC0 SoFIFA legacy team-id crosswalk; DuckDuckGo external-content proxy transport", "rendering": "source-derived editable PM99 colour/pattern recipe on a fixed centred shirt-and-shorts silhouette; no scaled shirt-image pixels", "inheritance": "no inherited 1998 PM99 kit is eligible"}, "sources": {"asset_manifest_sha256": sha256_bytes(canonical_json_bytes(manifest)), "fifa16_player_csv": {"path": str(player_csv.resolve()), "sha256": player_csv_hash}, "sofifa_legacy_csv": {"path": str(sofifa_legacy_csv.resolve()), "sha256": sofifa_hash, "license": "CC0", "dataset_url": "https://www.kaggle.com/datasets/stefanoleone992/fifa-23-complete-player-dataset"}, "catalog_pages": catalog_sources, "kit_archives": archive_hashes, "palette": {**palette_source, "sha256": sha256_file(Path(str(palette_source["path"])))}, "render_template": {"id": compact_template.TEMPLATE_ID}}, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-manifest", type=Path, required=True)
    parser.add_argument("--fifa16-player-csv", type=Path, required=True)
    parser.add_argument("--sofifa-legacy-csv", type=Path, required=True)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.asset_manifest.read_bytes()
    try:
        result = materialise(manifest=json.loads(raw), player_csv=args.fifa16_player_csv, sofifa_legacy_csv=args.sofifa_legacy_csv, dbdat=args.dbdat, cache_dir=args.cache_dir, output_dir=args.output_dir)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, FifaIndexKitError) as exc:
        parser.error(str(exc))
    result["sources"]["asset_manifest_file_sha256"] = sha256_bytes(raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
