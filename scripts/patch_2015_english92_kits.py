#!/usr/bin/env python3
"""Render and apply the 2015/16 English home-kit layer.

PM99 stores a team's shirt artwork separately from its EQ record.  This
script applies a deliberately small, source-led visual description to every
one of the five kit archives, retaining the game-native silhouette, palette,
bitmap dimensions and record offsets.  It does *not* download or redistribute
third-party kit images: the low-resolution PM99 artwork is rendered from the
documented contemporary home-kit colours/patterns.

The output receipt is intentionally suitable for a later browser-editor asset
workflow: every rendered kit has a carrier EQ id, a season reference page and
a rendering description.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the battle-tested PM99 archive/palette writer.  It preserves the
# obfuscated bitmap container instead of attempting to reconstruct it.
import patch_english80_reference_kits_v2 as renderer  # noqa: E402


KIT_SOURCES = {
    "Premier League": "https://www.footballkitarchive.com/premier-league-kits-2015-16-l224/",
    "Championship": "https://www.footballkitarchive.com/championship-kits-2015-16-l61/",
    "League One": "https://www.footballkitarchive.com/league-one-kits-2015-16-l156/",
    "League Two": "https://www.footballkitarchive.com/league-two-kits-2015-16-l157/",
}


def kit(
    pattern: str,
    colors: tuple[str, ...],
    *,
    shorts: str = "white",
    trim: str | None = "white",
    sleeves: str | None = None,
    stripe_count: int | None = None,
    band_count: int | None = None,
    accent: str | None = None,
    side_panel: str | None = None,
    yoke: str | None = None,
) -> dict[str, Any]:
    """Return one PM99-scale rendering contract.

    This is intentionally a conservative visual description.  Details which
    cannot survive the tiny PM99 silhouette (sponsors, manufacturers, seams)
    are not pretended to be faithfully rendered.
    """

    return {
        "pattern": pattern,
        "colors": list(colors),
        "shorts": shorts,
        "trim": trim,
        "sleeves": sleeves,
        "stripe_count": stripe_count,
        "band_count": band_count,
        "accent": accent,
        "side_panel": side_panel,
        "yoke": yoke,
        "reference_basis": "2015/16 home kit: manually rendered at PM99 scale from season kit reference",
    }


# The descriptions below retain the era's recognisable home identity.  They
# are intentionally data, not one-off byte patches, so the editor can present
# the same asset contract and a future season can provide another ledger.
STYLES: dict[str, dict[str, Any]] = {
    # Premier League
    "Arsenal": kit("sleeves", ("red",), sleeves="white", shorts="white", trim="white", accent="gold"),
    "Aston Villa": kit("sleeves", ("claret",), sleeves="sky", shorts="white", trim="sky"),
    "Bournemouth": kit("vertical_stripes", ("red", "black"), shorts="black", trim="black", stripe_count=6),
    "Chelsea": kit("solid", ("royal",), shorts="royal", trim="white"),
    "Crystal Palace": kit("vertical_stripes", ("blue", "red"), shorts="blue", trim="white", stripe_count=6),
    "Everton": kit("solid", ("royal",), shorts="white", trim="white"),
    "Leicester City": kit("solid", ("royal",), shorts="royal", trim="gold"),
    "Liverpool": kit("solid", ("deep_red",), shorts="deep_red", trim="white"),
    "Manchester City": kit("solid", ("sky",), shorts="white", trim="white"),
    "Manchester United": kit("solid", ("red",), shorts="white", trim="black"),
    "Newcastle United": kit("vertical_stripes", ("black", "white"), shorts="black", trim="black", stripe_count=6),
    "Norwich City": kit("solid", ("yellow",), shorts="green", trim="green"),
    "Southampton": kit("vertical_stripes", ("red", "white"), shorts="black", trim="black", stripe_count=6),
    "Stoke City": kit("vertical_stripes", ("red", "white"), shorts="white", trim="blue", stripe_count=6),
    "Sunderland": kit("vertical_stripes", ("red", "white"), shorts="black", trim="black", stripe_count=6),
    "Swansea City": kit("solid", ("white",), shorts="white", trim="black", side_panel="black"),
    "Tottenham Hotspur": kit("solid", ("white",), shorts="navy", trim="navy"),
    "Watford": kit("solid", ("yellow",), shorts="black", trim="black"),
    "West Bromwich Albion": kit("vertical_stripes", ("navy", "white"), shorts="white", trim="navy", stripe_count=6),
    "West Ham United": kit("sleeves", ("claret",), sleeves="sky", shorts="white", trim="sky"),
    # Championship
    "Birmingham City": kit("solid", ("royal",), shorts="royal", trim="white"),
    "Blackburn Rovers": kit("halves", ("blue", "white"), shorts="white", trim="blue"),
    "Bolton Wanderers": kit("solid", ("white",), shorts="navy", trim="navy"),
    "Brentford": kit("vertical_stripes", ("red", "white"), shorts="black", trim="black", stripe_count=6),
    "Brighton & Hove Albion": kit("vertical_stripes", ("blue", "white"), shorts="blue", trim="white", stripe_count=6),
    "Bristol City": kit("solid", ("red",), shorts="white", trim="white"),
    "Burnley": kit("sleeves", ("claret",), sleeves="sky", shorts="white", trim="sky"),
    "Cardiff City": kit("solid", ("blue",), shorts="blue", trim="white"),
    "Charlton Athletic": kit("solid", ("red",), shorts="white", trim="white"),
    "Derby County": kit("solid", ("white",), shorts="black", trim="black"),
    "Fulham": kit("solid", ("white",), shorts="black", trim="black", side_panel="black"),
    "Huddersfield Town": kit("vertical_stripes", ("blue", "white"), shorts="white", trim="blue", stripe_count=6),
    "Hull City": kit("vertical_stripes", ("amber", "black"), shorts="black", trim="black", stripe_count=6),
    "Ipswich Town": kit("solid", ("blue",), shorts="white", trim="red"),
    "Leeds United": kit("solid", ("white",), shorts="white", trim="blue", accent="yellow"),
    "Middlesbrough": kit("chest_band", ("red", "white"), shorts="red", trim="white"),
    "Milton Keynes Dons": kit("solid", ("white",), shorts="white", trim="red", side_panel="red"),
    "Nottingham Forest": kit("solid", ("red",), shorts="white", trim="white"),
    "Preston North End": kit("solid", ("white",), shorts="navy", trim="navy"),
    "Queens Park Rangers": kit("hoops", ("white", "royal"), shorts="white", trim="royal", band_count=6),
    "Reading": kit("hoops", ("royal", "white"), shorts="white", trim="royal", band_count=6),
    "Rotherham United": kit("sleeves", ("red",), sleeves="white", shorts="white", trim="white"),
    "Sheffield Wednesday": kit("vertical_stripes", ("royal", "white"), shorts="black", trim="white", stripe_count=6),
    "Wolverhampton Wanderers": kit("solid", ("gold",), shorts="black", trim="black"),
    # League One
    "Barnsley": kit("solid", ("red",), shorts="white", trim="white"),
    "Blackpool": kit("solid", ("tangerine",), shorts="white", trim="white"),
    "Bradford City": kit("vertical_stripes", ("claret", "amber"), shorts="black", trim="black", stripe_count=6),
    "Burton Albion": kit("solid", ("yellow",), shorts="black", trim="black"),
    "Bury": kit("solid", ("white",), shorts="navy", trim="navy"),
    "Chesterfield": kit("vertical_stripes", ("blue", "white"), shorts="blue", trim="white", stripe_count=6),
    "Colchester United": kit("vertical_stripes", ("blue", "white"), shorts="blue", trim="white", stripe_count=6),
    "Coventry City": kit("solid", ("sky",), shorts="sky", trim="white"),
    "Crewe Alexandra": kit("solid", ("red",), shorts="white", trim="white"),
    "Doncaster Rovers": kit("hoops", ("red", "white"), shorts="black", trim="black", band_count=6),
    "Fleetwood Town": kit("solid", ("red",), shorts="white", trim="white"),
    "Gillingham": kit("solid", ("blue",), shorts="white", trim="white"),
    "Millwall": kit("solid", ("navy",), shorts="white", trim="white"),
    "Oldham Athletic": kit("solid", ("blue",), shorts="blue", trim="white"),
    "Peterborough United": kit("solid", ("royal",), shorts="white", trim="white"),
    "Port Vale": kit("solid", ("white",), shorts="black", trim="black"),
    "Rochdale": kit("solid", ("blue",), shorts="white", trim="white"),
    "Scunthorpe United": kit("sleeves", ("claret",), sleeves="blue", shorts="blue", trim="blue"),
    "Sheffield United": kit("vertical_stripes", ("red", "white"), shorts="black", trim="black", stripe_count=6),
    "Shrewsbury Town": kit("solid", ("blue",), shorts="blue", trim="yellow"),
    "Southend United": kit("solid", ("blue",), shorts="white", trim="white"),
    "Swindon Town": kit("solid", ("red",), shorts="white", trim="white"),
    "Walsall": kit("solid", ("red",), shorts="white", trim="white"),
    "Wigan Athletic": kit("vertical_stripes", ("blue", "white"), shorts="blue", trim="white", stripe_count=6),
    # League Two
    "Accrington Stanley": kit("solid", ("red",), shorts="red", trim="white"),
    "AFC Wimbledon": kit("solid", ("blue",), shorts="blue", trim="yellow"),
    "Barnet": kit("solid", ("yellow",), shorts="navy", trim="navy"),
    "Bristol Rovers": kit("quarters", ("royal", "white"), shorts="white", trim="royal"),
    "Cambridge United": kit("solid", ("amber",), shorts="black", trim="black"),
    "Carlisle United": kit("solid", ("blue",), shorts="blue", trim="white"),
    "Crawley Town": kit("solid", ("red",), shorts="red", trim="white"),
    "Dagenham & Redbridge": kit("solid", ("red",), shorts="red", trim="white"),
    "Exeter City": kit("vertical_stripes", ("red", "white"), shorts="black", trim="black", stripe_count=6),
    "Hartlepool United": kit("solid", ("blue",), shorts="white", trim="white"),
    "Leyton Orient": kit("solid", ("red",), shorts="red", trim="white"),
    "Luton Town": kit("solid", ("orange",), shorts="navy", trim="navy"),
    "Mansfield Town": kit("solid", ("amber",), shorts="blue", trim="blue"),
    "Morecambe": kit("solid", ("red",), shorts="white", trim="white"),
    "Newport County": kit("solid", ("orange",), shorts="black", trim="black"),
    "Northampton Town": kit("solid", ("claret",), shorts="white", trim="white"),
    "Notts County": kit("vertical_stripes", ("black", "white"), shorts="black", trim="black", stripe_count=6),
    "Oxford United": kit("solid", ("yellow",), shorts="blue", trim="blue"),
    "Plymouth Argyle": kit("solid", ("green",), shorts="white", trim="white"),
    "Portsmouth": kit("solid", ("royal",), shorts="white", trim="white"),
    "Stevenage": kit("sleeves", ("red",), sleeves="white", shorts="red", trim="white"),
    "Wycombe Wanderers": kit("quarters", ("navy", "light_blue"), shorts="navy", trim="light_blue"),
    "Yeovil Town": kit("solid", ("green",), shorts="white", trim="white"),
    "York City": kit("solid", ("red",), shorts="white", trim="white"),
}


def load_assignments(manifest_path: Path) -> tuple[list[dict[str, Any]], str]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    teams = list(payload.get("teams") or [])
    team_count = len(teams)
    if team_count not in {80, 92}:
        raise RuntimeError(f"expected a native 80 or experimental 92-team season manifest, got {team_count}")
    missing = sorted(str(row.get("club")) for row in teams if str(row.get("club")) not in STYLES)
    # A Core80 release deliberately omits 12 clubs.  The wider style ledger is
    # retained so the same source-controlled kit layer can serve either build;
    # only an absent style for a selected club is an error.
    if missing:
        raise RuntimeError(f"kit style contract mismatch; selected clubs without styles={missing}")
    ids = [int(row["record_id"]) for row in teams]
    if len(set(ids)) != len(ids):
        raise RuntimeError("team manifest has duplicate carrier EQ ids")
    # The shared renderer's gallery helpers predate the season compiler and
    # use these neutral names.  Keep this adapter at the boundary instead of
    # making the season manifest mimic an unrelated tool's schema.
    assignments = [
        {
            **row,
            "slot": slot,
            "target_display_name": str(row["club"]),
            "target_pm99_division": str(row["division"]),
            "target_club_key": str(row["club"]),
            "carrier_eq_record_id": int(row["record_id"]),
        }
        for slot, row in enumerate(teams, start=1)
    ]
    return assignments, str(payload.get("release_profile") or f"english-{team_count}")


def styles_by_carrier(assignments: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in assignments:
        club = str(row["club"])
        style_row = dict(STYLES[club])
        style_row.update({
            "name": club,
            "slot": int(row["slot"]),
            "target_pm99_division": str(row["division"]),
            "carrier_eq_record_id": int(row["record_id"]),
            "source_url": KIT_SOURCES[str(row["division"])],
        })
        result[int(row["record_id"])] = style_row
    return result


def write_receipt(
    output_dir: Path,
    assignments: list[dict[str, Any]],
    styles: dict[int, dict[str, Any]],
    patched: list[dict[str, Any]],
    release_profile: str,
) -> Path:
    counts: dict[str, int] = {}
    for row in patched:
        counts[str(row["archive_name"])] = counts.get(str(row["archive_name"]), 0) + 1
    receipt = {
        "schema": "pm99-english-2015-16-home-kit-render-v2",
        "release_profile": release_profile,
        "scope": f"2015/16 English four divisions, {len(assignments)} home kits",
        "asset_policy": "manually rendered PM99-scale derivative; no third-party kit image is embedded",
        "sources": KIT_SOURCES,
        "team_count": len(assignments),
        "styles_by_carrier": {str(key): styles[key] for key in sorted(styles)},
        "patched_counts_by_archive": counts,
        "patched_record_count": len(patched),
        "patched": patched,
    }
    path = output_dir / f"2015-16-{release_profile}-kit-receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--season-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--verify-existing",
        action="store_true",
        help="Do not rewrite kit archives; verify an already-rendered five-archive set and emit review artifacts.",
    )
    values = parser.parse_args()

    game_root = values.game_root.expanduser().resolve()
    manifest_path = values.season_manifest.expanduser().resolve()
    output_dir = values.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "per_team_miniesc").mkdir(parents=True, exist_ok=True)

    assignments, release_profile = load_assignments(manifest_path)
    styles = styles_by_carrier(assignments)
    palette = renderer.load_dat_palette(game_root)
    mapper = renderer.PaletteMapper(palette)
    patched: list[dict[str, Any]] = []
    for archive_name in renderer.ARCHIVES:
        archive_path = game_root / "DBDAT" / archive_name
        if not archive_path.is_file():
            raise FileNotFoundError(f"missing kit archive: {archive_path}")
        if values.verify_existing:
            records = renderer.iter_obfuscated_bmp_records(archive_path, file_name_pattern=r"^EQ96\d{4}\.BMP$")
            by_team = {renderer.team_id_from_record(record): record for record in records}
            missing = sorted(set(styles) - set(by_team))
            # MINIESC is the canonical in-game squad/menu shirt.  The other
            # archive families predate some league carriers and have genuine
            # holes in the original payload; absence there is recorded rather
            # than fabricated with a differently sized bitmap.
            if archive_name == "MINIESC.PKF" and missing:
                raise RuntimeError(f"{archive_name}: missing 2015 carrier kit records {missing}")
            for team_id in sorted(set(styles) & set(by_team)):
                record = by_team[team_id]
                patched.append({
                    "archive": str(archive_path),
                    "archive_name": archive_name,
                    "team_id": team_id,
                    "target_name": styles[team_id]["name"],
                    "slot": styles[team_id]["slot"],
                    "file_name": record.file_name,
                    "bitmap_offset": int(record.bitmap_offset),
                    "bitmap_length": int(record.bitmap_length),
                    "verification": "parsed-after-render",
                })
        else:
            patched.extend(renderer.patch_archive(archive_path, output_dir, palette, mapper, styles))

    renderer.build_contact_sheet(
        game_root,
        output_dir / f"2015-16-{release_profile}-home-kits-contact-sheet.png",
        palette,
        assignments,
        styles,
    )
    renderer.write_gallery(output_dir / f"2015-16-{release_profile}-home-kits-gallery.html", assignments, styles)
    receipt = write_receipt(output_dir, assignments, styles, patched, release_profile)
    print(json.dumps({
        "teams": len(assignments),
        "patched_records": len(patched),
        "receipt": str(receipt),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
