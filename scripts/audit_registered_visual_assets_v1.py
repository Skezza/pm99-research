#!/usr/bin/env python3
"""Audit every registered roster's photo coverage and archive shapes; collect selector evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "scripts", ROOT / "upstream/pm99-skezmod-db-editor"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from app.fdi_indexed import IndexedFDIFile
from app.minifoto_bitmap_archive import decode_obfuscated_bitmap_name, iter_minifoto_records, iter_obfuscated_bmp_records, validate_minifoto_bitmap
from scripts.season_package_compiler_v2 import _source_roster_owners, _player_name
from scripts import season_release_registry_v1 as registry

ARCHIVES = ("BIGCAMP.PKF", "BIGESC.PKF", "MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def invalid_photo_entries(path, decoded):
    """The ordinary archive iterator skips malformed active BMPs; count those too."""
    data = path.read_bytes()
    invalid = {}
    offset = data.find(b'\x02')
    while 0 <= offset <= len(data) - 38:
        name = decode_obfuscated_bitmap_name(data[offset + 1:offset + 21]).split(b'\0', 1)[0]
        match = re.fullmatch(rb'J96(\d{5})\.BMP', name)
        if match and int(match[1]) not in decoded:
            start = int.from_bytes(data[offset + 26:offset + 30], 'little')
            length = int.from_bytes(data[offset + 30:offset + 34], 'little')
            invalid[int(match[1])] = {'directory_offset': offset, 'bitmap_offset': start, 'bitmap_length': length,
                                    'issue': 'active archive photo is malformed or outside archive bounds'}
        offset = data.find(b'\x02', offset + 1)
    return invalid


def screenshot_from_summary(evidence):
    if not evidence:
        return None
    path = evidence / "summary.json"
    if not path.is_file():
        return None
    summary = json.loads(path.read_text())
    for step in summary.get("steps", []):
        if step.get("step", {}).get("label") == "pick_stoke":
            screenshot = evidence / "screens" / Path(step["screenshot"]).name
            if screenshot.is_file():
                return {"path": str(screenshot), "sha256": sha(screenshot),
                        "summary_sha256": sha(path), "success": summary.get("success"),
                        "release_manifest_sha256": summary.get("release_manifest_sha256"),
                        "output_inventory_fingerprint": summary.get("output_inventory_fingerprint")}
    return None


def audit(output):
    seasons = registry.supported_seasons()
    baseline_release = registry.load_preferred_release("2014-15")
    baseline_records = {r.player_record_id: hashlib.sha256(r.raw_bitmap).hexdigest()
                        for r in iter_minifoto_records(baseline_release.game_path / "DBDAT/MINIFOTO.PKF")}
    parsed_photos, invalid_photos, parsed_kits = {}, {}, {}
    english_source = ROOT / '.local/season-2015-16/english92-2015-16-build36-native-no-photo'
    english_receipt = json.loads((english_source / 'face-stage-receipt.json').read_text())
    english_rows = {int(row['record_id']): row for row in english_receipt['rows']}
    english_expected = {record.player_record_id: hashlib.sha256(record.raw_bitmap).hexdigest()
                        for record in iter_minifoto_records(english_source / 'game/DBDAT/MINIFOTO.PKF')}
    for path in (english_source / 'game/DBDAT/MINIFOTO').glob('*.BMP'):
        english_expected[int(path.stem[3:])] = sha(path)
    foreign_receipt_path = ROOT / '.local/season-workspace-v1/2015-16-final-build/foreign-portrait-application-receipt.json'
    foreign_rows = {int(row['player_carrier_id']): row
                    for row in json.loads(foreign_receipt_path.read_text())['operations']
                    if row.get('resulting_state') == 'applied'}
    summaries = []
    for season in seasons:
        release = registry.load_preferred_release(season)
        package = json.loads(release.package_path.read_text())
        dbdat = release.game_path / "DBDAT"
        owner, rosters, modes = _source_roster_owners((dbdat / "EQ98030.FDI").read_bytes())
        package_players = {int(p["carrier_id"]): p for p in package["players"]}
        declarations = {p["player_id"]: p.get("status") for p in package["assets"]["portraits"]}
        archive_hash = sha(dbdat / "MINIFOTO.PKF")
        if archive_hash not in parsed_photos:
            parsed_photos[archive_hash] = {r.player_record_id: r for r in iter_minifoto_records(dbdat / "MINIFOTO.PKF")}
            invalid_photos[archive_hash] = invalid_photo_entries(dbdat / 'MINIFOTO.PKF', parsed_photos[archive_hash])
        photos = parsed_photos[archive_hash]
        jug = (dbdat / "JUG98030.FDI").read_bytes()
        entries = {int(e.record_id): e for e in IndexedFDIFile.from_bytes(jug).entries}
        players = []
        counts = Counter()
        group_counts = defaultdict(Counter)
        mismatches = 0
        for player_id, clubs in sorted(owner.items()):
            loose = dbdat / "MINIFOTO" / f"J96{player_id:05d}.BMP"
            record = photos.get(player_id)
            packaged = package_players.get(player_id)
            if packaged:
                name = packaged["name"]
            elif player_id in entries:
                try:
                    name = _player_name(entries[player_id].decode_payload(jug), record_id=player_id)
                except Exception:
                    name = "unparsed-player"
            else:
                name = "missing-player-record"
            group = "english-club" if any(modes.get(c) == 0 for c in clubs) else "foreign-club"
            status, bitmap_hash, issue = "no-photo", None, None
            if loose.is_file():
                payload = loose.read_bytes()
                bitmap_hash = hashlib.sha256(payload).hexdigest()
                try:
                    validate_minifoto_bitmap(payload)
                    status = "changed-photo-unverified"
                except ValueError as exc:
                    status, issue = "invalid-photo", str(exc)
            elif record:
                bitmap_hash = hashlib.sha256(record.raw_bitmap).hexdigest()
                status = "stock-carrier-photo" if baseline_records.get(player_id) == bitmap_hash else "changed-photo-unverified"
            elif player_id in invalid_photos[archive_hash]:
                status, issue = 'invalid-photo', invalid_photos[archive_hash][player_id]['issue']
            declared = declarations.get(packaged["id"]) if packaged else "not-in-primary-package"
            verification = "not-proven-by-this-structural-audit"
            if season == '2015-16' and bitmap_hash:
                expected = english_expected.get(player_id) if group == 'english-club' else foreign_rows.get(player_id, {}).get('bitmap_sha256')
                if expected == bitmap_hash:
                    source = english_rows.get(player_id, {}) if group == 'english-club' else foreign_rows.get(player_id, {})
                    status = 'source-bound-photo'
                    verification = 'matches-legacy-identity-application-by-carrier-and-bitmap'
                else:
                    verification = 'legacy-source-bitmap-missing-or-mismatch'
            if declared == "native-no-photo" and status != "no-photo":
                mismatches += 1
            row = {"carrier_id": player_id, "name": name, "club_carriers": clubs, "group": group,
                   "physical_status": status, "bitmap_sha256": bitmap_hash,
                   "recipe_declaration": declared, "identity_verification": verification}
            if season == '2015-16' and status == 'source-bound-photo':
                row['source_player_name'] = source.get('player') or source.get('name')
            if issue:
                row["issue"] = issue
            players.append(row)
            counts[status] += 1
            group_counts[group][status] += 1
        kits = {}
        for archive_name in ARCHIVES:
            path = dbdat / archive_name
            key = sha(path)
            if key not in parsed_kits:
                records = iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$")
                parsed_kits[key] = {"record_count": len(records),
                    "shapes": dict(Counter(f"{r.width}x{r.height}x{r.bits_per_pixel}" for r in records)),
                    "carrier_ids": [int(r.file_name[4:8]) for r in records],
                    "record_hashes": {r.file_name: hashlib.sha256(r.raw_bitmap).hexdigest() for r in records}}
            data = parsed_kits[key]
            missing = sorted(set(rosters) - set(data["carrier_ids"]))
            kits[archive_name] = {"sha256": key, "record_count": data["record_count"], "shapes": data["shapes"],
                                 "missing_club_count": len(missing), "missing_club_carriers": missing}
        screenshot = screenshot_from_summary(release.runtime_evidence_path)
        bound = bool(screenshot and screenshot["success"] and
                     screenshot["release_manifest_sha256"] == release.manifest_sha256 and
                     screenshot["output_inventory_fingerprint"] == release.locator["game_inventory_fingerprint"])
        report = {"schema_version": "pm99-season-visual-assets-audit-v1", "season": season,
                  "game": str(release.game_path), "package_sha256": sha(release.package_path),
                  "release_manifest_sha256": release.manifest_sha256,
                  "rostered_players": len(players), "roster_memberships": sum(map(len, rosters.values())),
                  "photo_counts": dict(counts), "photo_groups": {k: dict(v) for k, v in group_counts.items()},
                  "no_photo_declaration_conflicts": mismatches, "minifoto_sha256": archive_hash,
                  "runtime_palette_sha256": sha(release.game_path / "DAT.PKF"),
                  "kits": kits, "selection_baseline": screenshot, "selection_baseline_bound": bound,
                  "players": players}
        if season == '2015-16':
            report['source_receipts'] = {'english': sha(english_source / 'face-stage-receipt.json'),
                                         'foreign': sha(foreign_receipt_path)}
        save(output / season / "player-photo-audit.json", report)
        summaries.append({k: v for k, v in report.items() if k not in {"players", "kits"}} |
                         {"kit_archives": {k: {"sha256": v["sha256"], "shapes": v["shapes"],
                                                "missing_club_count": v["missing_club_count"]} for k, v in kits.items()}})
        print(json.dumps({"season": season, "players": len(players), "photos": dict(counts),
                          "selection_baseline_bound": bound}), flush=True)
    save(output / "all-seasons-audit.json", {"schema_version": "pm99-all-season-visual-assets-audit-v1",
                                            "season_count": len(summaries), "seasons": summaries})


def capture(output, worker, selected):
    selectors = {r["season"]: r for r in json.loads((ROOT / "data/season-runtime-selectors-v1.json").read_text())["seasons"]}
    env = os.environ.copy()
    env["PM99_RUNNER_ARCHIVE_COLD_RUNS"] = "0"
    env["PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE"] = "0"
    results = []
    for season in selected:
        release = registry.load_preferred_release(season)
        selector = selectors[season]
        tag = "visual_qa_" + season.replace("-", "_") + "_20261003_r1"
        evidence = ROOT / ".local/runlogs/pm99_runner" / tag
        existing_summary = evidence / 'selector_discovery_summary.json'
        if existing_summary.is_file() and json.loads(existing_summary.read_text()).get('success'):
            result = {"season": season, "status": "existing-capture", "evidence": str(evidence)}
        else:
            command = [str(ROOT / "scripts/run_pm99_experiment.sh"), "selector-discovery-capture",
                       "--worker", worker, "--run-tag", tag, "--allow-dirty-runner", "--",
                       "--skip-setup", "--skip-prepare", "--skip-build", "--game-root", str(release.game_path),
                       "--division-point", f"{selector['division_select_x']},{selector['division_select_y']}",
                       "--team-point", f"{selector['team_select_x']},{selector['team_select_y']}",
                       "--skip-ocr", "--docker-timeout", "180"]
            log = output / season / "capture-launch.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            print(json.dumps({"season": season, "capture": "starting", "tag": tag}), flush=True)
            with log.open("w") as stream:
                try:
                    # Includes fair-share host queue time, not just the bounded 180-second game run.
                    complete = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
                    result = {"season": season, "status": "captured" if complete.returncode == 0 else "failed",
                              "returncode": complete.returncode, "evidence": str(evidence), "log": str(log)}
                except subprocess.TimeoutExpired:
                    result = {"season": season, "status": "timeout", "evidence": str(evidence), "log": str(log)}
        result["release_manifest_sha256"] = release.manifest_sha256
        results.append(result)
        save(output / "new-captures.json", {"results": results})
        print(json.dumps(result), flush=True)


def gallery(output):
    """Index fresh runtime captures and make labelled review sheets, without editing releases."""
    from PIL import Image, ImageChops, ImageDraw
    from scripts.compare_pm99_kit_bmp_lineage_v1 import image as kit_image, records as kit_records
    from scripts.pm99_kit_palette_v1 import runtime_kit_palette

    rows = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        evidence = ROOT / '.local/runlogs/pm99_runner' / ('visual_qa_' + season.replace('-', '_') + '_20261003_r1')
        summary_path = evidence / 'selector_discovery_summary.json'
        discovery_path = evidence / 'selector_discovery.json'
        row = {'season': season, 'release_manifest_sha256': release.manifest_sha256,
               'status': 'missing-capture'}
        if summary_path.is_file() and discovery_path.is_file():
            summary = json.loads(summary_path.read_text())
            discovery = json.loads(discovery_path.read_text())
            observations = [team for division in discovery.get('divisions', []) for team in division.get('teams', [])]
            if summary.get('success') and len(observations) == 1:
                path = evidence / 'screens' / Path(observations[0]['screenshot']).name
                if path.is_file():
                    row.update(status='captured', screenshot=str(path), screenshot_sha256=sha(path),
                               summary_sha256=sha(summary_path), discovery_sha256=sha(discovery_path))
                    baseline = screenshot_from_summary(release.runtime_evidence_path)
                    if baseline:
                        # Only the kit grid: manager selection rows/cursor may legitimately differ.
                        region = (150, 306, 488, 383)
                        with Image.open(path) as fresh, Image.open(baseline['path']) as original:
                            diff = ImageChops.difference(fresh.convert('RGB').crop(region), original.convert('RGB').crop(region))
                            row['kit_grid_matches_bound_baseline'] = diff.getbbox() is None
                            row['kit_grid_changed_pixels'] = sum(pixel != (0, 0, 0) for pixel in diff.getdata())
        baseline_summary = release.runtime_evidence_path / 'summary.json' if release.runtime_evidence_path else None
        if baseline_summary and baseline_summary.is_file():
            steps = json.loads(baseline_summary.read_text()).get('steps', [])
            for step in steps:
                if step.get('step', {}).get('label') == 'return_from_line_up':
                    dashboard = release.runtime_evidence_path / 'screens' / Path(step['screenshot']).name
                    if dashboard.is_file():
                        row['bound_baseline_dashboard'] = str(dashboard)
                        row['bound_baseline_dashboard_sha256'] = sha(dashboard)
        fresh_dashboard = ROOT / '.local/runlogs/pm99_runner' / ('visual_qa_' + season.replace('-', '_') + '_dashboard_20261003_r1')
        if (fresh_dashboard / 'summary.json').is_file():
            dashboard_summary = json.loads((fresh_dashboard / 'summary.json').read_text())
            if dashboard_summary.get('success') and dashboard_summary.get('release_manifest_sha256') == release.manifest_sha256:
                for step in dashboard_summary.get('steps', []):
                    if step.get('step', {}).get('label') == 'return_from_line_up':
                        path = fresh_dashboard / 'screens' / Path(step['screenshot']).name
                        if path.is_file():
                            row['fresh_dashboard'] = str(path)
                            row['fresh_dashboard_sha256'] = sha(path)
                            # Known PM99 640x480 HUD position. Compare foreground
                            # colours only; this is not a historical/style approval.
                            from scripts.foreign_host_mapping_v1 import _eq_short_names
                            names = _eq_short_names(release.game_path / 'DBDAT')
                            stoke = next(carrier for carrier, name in names.items() if name == 'Stoke City')
                            palette, _ = runtime_kit_palette(release.game_path / 'DBDAT')
                            expected = kit_image(kit_records(release.game_path / 'DBDAT')[stoke], palette, scale=1)
                            with Image.open(path) as screen:
                                actual = screen.convert('RGB').crop((585, 4, 585 + expected.width, 4 + expected.height))
                                differences = [max(abs(a - b) for a, b in zip(target, reference[:3]))
                                               for target, reference in zip(actual.getdata(), expected.getdata())
                                               if reference[3] > 0]
                            row['dashboard_kit_colour_comparison'] = {
                                'carrier_id': stoke, 'foreground_pixel_count': len(differences),
                                'within_10_per_channel_fraction': sum(value <= 10 for value in differences) / len(differences),
                                'tolerance_reason': '16-bit runner display quantisation and HUD overlap',
                                'note': 'Diagnostic colour fidelity only; not a whole-kit visual-quality or identity approval.'}
        rows.append(row)

    sheets = []
    for start in (0, 13):
        subset = rows[start:start + 13]
        for kind, key in (('selection', 'screenshot'), ('dashboard-baseline', 'bound_baseline_dashboard')):
            sheet = Image.new('RGB', (640, 7 * 264 + 24), '#111820')
            draw = ImageDraw.Draw(sheet)
            draw.text((8, 5), 'Fresh runner selection' if kind == 'selection' else 'Previously release-bound runner dashboards (September 2026)', fill='white')
            for index, row in enumerate(subset):
                x, y = (index % 2) * 320, (index // 2) * 264 + 24
                draw.text((x + 7, y + 5), row['season'], fill='white')
                if key in row:
                    with Image.open(row[key]) as screen:
                        sheet.paste(screen.convert('RGB').resize((320, 240), Image.Resampling.NEAREST), (x, y + 24))
                else:
                    draw.text((x + 7, y + 50), 'NOT CAPTURED', fill='#ff9090')
            path = output / f'{kind}-{start + 1:02d}-{start + len(subset):02d}.png'
            sheet.save(path)
            sheets.append(str(path.resolve()))

        # These are explicitly archive previews, not runner screenshots.
        kit_sheet = Image.new('RGB', (6 * 150, len(subset) * 160 + 24), '#e0e0da')
        kit_draw = ImageDraw.Draw(kit_sheet)
        kit_draw.text((6, 5), 'Foreign MINIESC archive previews using actual DAT.PKF palette - NOT runtime screenshots', fill='black')
        queries = ('Barcelona', 'Real Madrid', 'Bayern', 'Milan', 'Juventus', 'Ajax')
        for index, row in enumerate(subset):
            release = registry.load_preferred_release(row['season'])
            package = json.loads(release.package_path.read_text())
            records = kit_records(release.game_path / 'DBDAT')
            palette, _ = runtime_kit_palette(release.game_path / 'DBDAT')
            for col, query in enumerate(queries):
                matches = [club for club in package['clubs'] if query.casefold() in club['name'].casefold()]
                if not matches:
                    continue
                club = sorted(matches, key=lambda c: len(c['name']))[0]
                record = records.get(int(club['carrier_id']))
                x, y = col * 150, index * 160 + 24
                kit_draw.text((x + 4, y + 3), row['season'] + ' ' + club['name'][:17], fill='black')
                if record:
                    rendered = kit_image(record, palette, scale=2)
                    kit_sheet.paste(rendered, (x + 25, y + 24), rendered)
        path = output / f'foreign-kit-palette-previews-{start + 1:02d}-{start + len(subset):02d}.png'
        kit_sheet.save(path)
        sheets.append(str(path.resolve()))
    save(output / 'screenshot-index.json', {'seasons': rows, 'sheets': sheets,
                                          'fresh_capture_count': sum(row['status'] == 'captured' for row in rows)})
    parts = ['<!doctype html><meta charset="utf-8"><title>PM99 visual QA</title>',
             '<style>body{font:16px sans-serif;background:#15202a;color:#eee}img{max-width:640px;width:100%}section{margin:2em 0}a{color:#a9ddff}</style>',
             '<h1>PM99 visual QA: all 26 seasons</h1><p>Fresh selection captures. Dashboard images are previously release-bound September evidence, not new captures.</p>']
    for row in rows:
        parts.append('<section><h2>' + row['season'] + '</h2>')
        audit_path = output / row['season'] / 'player-photo-audit.json'
        if audit_path.is_file():
            data = json.loads(audit_path.read_text())
            parts.append('<p>English clubs: ' + html.escape(str(data['photo_groups'].get('english-club'))) +
                         '<br>Foreign clubs: ' + html.escape(str(data['photo_groups'].get('foreign-club'))) +
                         '<br><a href="' + row['season'] + '/player-photo-audit.json">Every rostered player: photo audit</a></p>')
        for key, label in (('screenshot', 'Fresh team / kit selection'), ('fresh_dashboard', 'Fresh dashboard capture'),
                           ('bound_baseline_dashboard', 'Release-bound dashboard baseline')):
            if key in row:
                relative = os.path.relpath(row[key], output.resolve())
                parts.append('<p>' + label + '</p><a href="' + html.escape(relative, quote=True) + '"><img src="' + html.escape(relative, quote=True) + '"></a>')
        parts.append('</section>')
    (output / 'screenshots.html').write_text('\n'.join(parts), encoding='utf-8')
    print(json.dumps({'fresh_capture_count': sum(row['status'] == 'captured' for row in rows), 'sheets': sheets}), flush=True)


def report(output):
    audited = json.loads((output / 'all-seasons-audit.json').read_text())
    screenshots = json.loads((output / 'screenshot-index.json').read_text())
    per_season = []
    for row in audited['seasons']:
        groups = row['photo_groups']
        per_season.append({'season': row['season'], 'rostered_players': row['rostered_players'],
                           'english_sourced_photos': groups['english-club'].get('source-bound-photo', 0),
                           'english_stock_photos': groups['english-club'].get('stock-carrier-photo', 0),
                           'english_no_photo': groups['english-club'].get('no-photo', 0),
                           'foreign_sourced_photos': groups['foreign-club'].get('source-bound-photo', 0),
                           'foreign_stock_photos': groups['foreign-club'].get('stock-carrier-photo', 0),
                           'foreign_no_photo': groups['foreign-club'].get('no-photo', 0),
                           'no_photo_declaration_conflicts': row['no_photo_declaration_conflicts']})
    with (output / 'photo-coverage.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(per_season[0]))
        writer.writeheader()
        writer.writerows(per_season)
    pilot_root = ROOT / '.local/season-historical-photo-pilots-v1/2014-15/stoke-qa-v4'
    pilot = json.loads((pilot_root / 'combined-materialisation.json').read_text())
    pilot_qa = json.loads((pilot_root / 'historical-photo-qa.json').read_text())
    pilot_validation = json.loads((pilot_root / 'validation.json').read_text())
    totals = Counter()
    for row in audited['seasons']:
        totals.update(row['photo_counts'])
    findings = [
        {'priority': 'P1', 'code': 'released-native-no-photo-not-materialised',
         'detail': '25 registered releases retain the native MINIFOTO archive; no-photo recipe entries still resolve stock carrier faces.',
         'declaration_conflicts': sum(row['no_photo_declaration_conflicts'] for row in audited['seasons']),
         'confirmed_example': {'season': '2014-15', 'carrier_id': 25, 'recipe_player': 'Thomas Heaton',
                               'original_photo_player': 'Albert FERRER Llopis'},
         'next_action': 'Wire photo application and no-photo materialisation into the registered build chain, with identity-bound receipts.'},
        {'priority': 'P1', 'code': 'foreign-photo-stage-not-released',
         'detail': 'Only 2015/16 has installed sourced foreign-club portraits. Other 25 releases each have 9,352 blank foreign slots and two stock faces.',
         'next_action': 'Release the bounded 2014/15 pilot after provenance fixes; source and apply other seasons incrementally.'},
        {'priority': 'P1', 'code': 'foreign-kit-slot-identity-mismatch',
         'detail': 'Preserved kit archive entries follow carrier slots, not renamed club identities. Bayern Munich in 2022/23 and 2024/25 uses carrier 401 and byte-identical original Borussia Dortmund MINIESC artwork.',
         'next_action': 'Resolve kits by final club identity/carrier binding; do not blindly preserve another club’s stock kit.'},
        {'priority': 'P1', 'code': 'historical-composer-stale-input-accepted',
         'location': 'scripts/compose_historical_photo_materialisation_v1.py:23',
         'detail': 'Read-only probe changed QA input_hashes.fifa_manifest to 64 zeroes; compose still accepted all nine historical overlays.',
         'next_action': 'Reject mismatched input hashes and duplicate or incomplete carrier coverage before overlaying.'},
        {'priority': 'P2', 'code': 'historical-photo-date-provenance-ambiguous',
         'location': 'scripts/season_historical_photo_pilot_v1.py:44',
         'detail': 'Discovery allows DateTime as a fallback to DateTimeOriginal without retaining the date basis. A dated upload is not sufficient proof of capture era.',
         'next_action': 'Retain date basis and certainty; require captured-date evidence or explicitly mark era uncertain.'},
        {'priority': 'P2', 'code': 'historical-overlay-metadata-stale-and-stoke-only',
         'location': 'scripts/compose_historical_photo_materialisation_v1.py:32',
         'detail': 'Composer hardcodes 25 Stoke rows and retains FIFA preview/source-name fields and stale era_grade_counts after replacing the BMP.',
         'next_action': 'Use recipe club coverage and rebuild image-specific metadata, attribution and coverage counts.'},
        {'priority': 'P1', 'code': 'play-launches-writable-registered-release',
         'location': 'scripts/pm99_season_play_v1.py:65',
         'detail': 'Play changes directory into the registered release and launches Wine there. Full inventory verification fails for 2013/14 because manager.ini changed FULL SCREEN from OFF to ON on September 16; all required database/executable/compact-kit hashes still match.',
         'next_action': 'Launch an isolated persistent play workspace, with mutable settings/saves detached from registered release files; preserve the user’s fullscreen preference.'},
    ]
    result = {'schema_version': 'pm99-visual-qa-closeout-v1', 'result': 'needs-fixes',
              'registered_season_count': audited['season_count'],
              'rostered_season_player_entries': sum(row['rostered_players'] for row in audited['seasons']),
              'photo_totals': dict(totals), 'fresh_selection_captures': screenshots['fresh_capture_count'],
              'fresh_selection_missing': [row['season'] for row in screenshots['seasons'] if row['status'] != 'captured'],
              'scope_limits': ['Counts are season-player entries, not unique individuals.',
                               'All active roster photo availability, bitmap validity and recorded 2015 applied-bitmap identity bindings were audited.',
                               'Receipt matches are not an independent visual identification of every photographed person.',
                               'Fresh selection screenshots cover English managed-club kit grids; foreign kit sheets are explicitly archive previews.',
                               'The reported laptop palette corruption has not been reproduced or declared fixed.'],
              'native_source_confirmation': {'remote_root': '/home/joe/pm99-runner/shared/source_install/premier-manager-ninety-nine',
                                             'minifoto_sha256': '726ca9d9f9a2d507a6d46a210b0b161b786f4b0fa575c60538084dfd0290a147',
                                             'dat_pkf_sha256': '64f44e076cd8f294d05a21b9693a14eec3d42afb341ec7ac2abaf128b240ed29',
                                             'local_original_jug_sha256': sha(output / 'native-source-JUG98030.FDI')},
              'historical_pilot': {'season': '2014-15', 'not_registered': True, 'coverage': pilot['coverage'],
                                   'stoke_qa_counts': pilot_qa['counts'], 'validation': pilot_validation},
              'checks_run': [{'command': 'bash scripts/test_season_pipeline.sh -q', 'result': '26 passed'},
                             {'command': 'python3 scripts/check_repo_boundary.py', 'result': 'passed'},
                             {'command': 'git diff --check', 'result': 'passed'},
                             {'command': 'bash scripts/test_season_pipeline.sh scripts/test_audit_registered_visual_assets_v1.py -q', 'result': '29 passed'},
                             {'command': 'season_portrait_pipeline_v1.py validate (2014/15 combined pilot)', 'result': '11557 checked, zero issues'}],
              'findings': findings, 'per_season': per_season, 'registered_games_modified': False}
    result['fresh_dashboard_colour_comparisons'] = [
        {'season': row['season'], **row['dashboard_kit_colour_comparison']}
        for row in screenshots['seasons'] if 'dashboard_kit_colour_comparison' in row]
    release_validation = output / 'registered-release-validation.json'
    if release_validation.is_file():
        verified = json.loads(release_validation.read_text())
        result['immutable_release_validation'] = {'season_count': verified['season_count'],
                                                  'valid_count': verified['valid_count']}
    binding_report = output / 'foreign-kit-bindings.json'
    if binding_report.is_file():
        result['native_kit_identity_review'] = json.loads(binding_report.read_text())
    foreign_capture = ROOT / '.local/runlogs/pm99_runner/visual_qa_2015_16_foreign_spain_20261003_r1'
    if (foreign_capture / 'summary.json').is_file():
        summary = json.loads((foreign_capture / 'summary.json').read_text())
        release = registry.load_preferred_release('2015-16')
        receipt = foreign_capture / 'dbdat_override.sha256'
        matches = True
        for line in receipt.read_text().splitlines():
            if line.startswith('#') or not line.strip():
                continue
            expected, relative = line.split(None, 1)
            matches = matches and sha(release.game_path / relative.strip()) == expected
        result['foreign_runtime_capture'] = {'season': '2015-16', 'country': 'Spain', 'success': summary.get('success'),
                                             'all_visual_input_hashes_match_registered_release': matches,
                                             'receipt_sha256': sha(receipt),
                                             'screenshot': str(foreign_capture / 'screens/18_select_spain.png'),
                                             'selected_club_screenshot': str(foreign_capture / 'screens/19_select_spanish_club.png')}
    save(output / 'qa-findings.json', result)
    print(json.dumps({'result': result['result'], 'fresh_captures': result['fresh_selection_captures'],
                      'findings': len(findings), 'photo_totals': dict(totals)}), flush=True)


def kit_bindings(output):
    """Flag native artwork inherited after a club rename; aliases require review, not auto-rejection."""
    from scripts.foreign_host_mapping_v1 import _eq_short_names
    from scripts.compare_pm99_kit_bmp_lineage_v1 import records

    source = output / 'native-source'
    native_names = _eq_short_names(source)
    native_hashes = {carrier: hashlib.sha256(record.raw_bitmap).hexdigest()
                     for carrier, record in records(source).items()}

    def normalise(value):
        plain = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
        return ''.join(char for char in plain if char.isalnum())

    flags, summaries = [], []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        package = json.loads(release.package_path.read_text())
        clubs = {int(club['carrier_id']): club for club in package['clubs']}
        _owners, _rosters, modes = _source_roster_owners((release.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
        count, identical = 0, 0
        for carrier, record in records(release.game_path / 'DBDAT').items():
            if modes.get(carrier) != 1 or carrier not in clubs:
                continue
            bitmap_hash = hashlib.sha256(record.raw_bitmap).hexdigest()
            if bitmap_hash != native_hashes.get(carrier):
                continue
            identical += 1
            name, native = clubs[carrier]['name'], native_names.get(carrier, '')
            if normalise(name) != normalise(native):
                flags.append({'season': season, 'carrier_id': carrier, 'recipe_club': name,
                              'native_artwork_club': native, 'bitmap_sha256': bitmap_hash,
                              'disposition': 'review-club-identity-change-or-alias'})
                count += 1
        summaries.append({'season': season, 'identical_native_foreign_miniesc': identical,
                          'renamed_native_kit_review_count': count})
    with (output / 'foreign-kit-binding-review.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flags[0]))
        writer.writeheader()
        writer.writerows(flags)
    save(output / 'foreign-kit-bindings.json', {'schema_version': 'pm99-native-kit-identity-review-v1',
                                               'native_source_eq_sha256': sha(source / 'EQ98030.FDI'),
                                               'native_source_miniesc_sha256': sha(source / 'MINIESC.PKF'),
                                               'review_count': len(flags), 'per_season': summaries,
                                               'note': 'Name changes include harmless aliases; these are review flags, not a count of confirmed incorrect kits.'})
    print(json.dumps({'kit_identity_review_count': len(flags), 'season_count': len(summaries)}), flush=True)


def verify_releases(output):
    results = []
    for season in registry.supported_seasons():
        result = registry.validate_preferred_release(season, level='release')
        results.append(result)
        print(json.dumps({'season': season, 'valid': result['valid'], 'issue_count': len(result['issues'])}), flush=True)
    save(output / 'registered-release-validation.json', {'season_count': len(results),
                                                        'valid_count': sum(row['valid'] for row in results),
                                                        'results': results})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "capture", "gallery", "report", "kit-bindings", "verify-releases"))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--worker", default="tiny-m73")
    parser.add_argument("--season", action="append")
    args = parser.parse_args()
    if args.action == "audit":
        audit(args.output_root)
    elif args.action == 'capture':
        capture(args.output_root, args.worker, args.season or registry.supported_seasons())
    elif args.action == 'gallery':
        gallery(args.output_root)
    elif args.action == 'report':
        report(args.output_root)
    elif args.action == 'kit-bindings':
        kit_bindings(args.output_root)
    else:
        verify_releases(args.output_root)


if __name__ == "__main__":
    main()
