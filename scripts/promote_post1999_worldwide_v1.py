#!/usr/bin/env python3
"""Resume-safe promotion of one post-1999 season to a playable candidate.

This is deliberately a coordinator.  The individual source, authoring,
compiler and archive tools remain independently runnable and reviewable.  A
stage is skipped only when its terminal receipt already exists, so an
interrupted batch continues forward without rebuilding completed seasons.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
BASE = LOCAL / "season-pipeline-v2" / "pm99-base-clean"
VERIFIED_BASE = LOCAL / "season-pipeline-v2" / "verified-base.json"
SELECTOR_MAP = LOCAL / "selector_maps" / "core80_clean_native_eq_map_20260828.json"
PATTERN_CACHE = LOCAL / "source-cache" / "wikimedia-kit-patterns-v1"
STAGES = ("compose", "layers", "kits", "author", "merge", "ingress", "kit-archives", "runtime")


class PromotionError(RuntimeError):
    pass


def _run(command: list[str], *, terminal: Path) -> dict[str, object]:
    if terminal.exists():
        return {"status": "reused", "terminal": str(terminal.relative_to(ROOT))}
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    event: dict[str, object] = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "terminal": str(terminal.relative_to(ROOT)),
    }
    if completed.returncode or not terminal.exists():
        raise PromotionError(json.dumps(event, indent=2))
    event["status"] = "built"
    return event


def _require(paths: list[Path]) -> None:
    missing = [str(path.relative_to(ROOT)) for path in paths if not path.exists()]
    if missing:
        raise PromotionError("missing inputs: " + ", ".join(missing))


def promote(season: str, *, revision: str, kit_revision: str | None, through: str, allow_network: bool) -> dict[str, object]:
    end = STAGES.index(through)
    events: list[dict[str, object]] = []
    chain = LOCAL / "season-english-source-chain-v1" / season / revision
    kit_revision = kit_revision or revision
    kit_root = LOCAL / "season-hfk-english-kits-v1" / season / kit_revision
    author = LOCAL / "season-english-authoring-v1" / season / revision
    merged = LOCAL / "season-worldwide-merged-v1" / season / revision
    ingress = LOCAL / "season-static-ingress-v1" / f"{season}-worldwide-source-backed-{revision}"
    renders = LOCAL / "season-kit-renders-v1" / season / f"source-backed-{revision}"
    archives = LOCAL / "season-kit-archives-v1" / season / f"source-backed-{revision}"
    runtime = LOCAL / "season-runtime-candidates-v1" / season / f"worldwide-source-backed-{revision}" / "game"

    preallocation = LOCAL / "transfermarkt-opening-plans-current-v1" / season / "opening-squad-preallocation.json"
    preseason_standings = LOCAL / "season-english-preseason-standings-v1" / season / "preseason-standings.json"
    reconciliation = LOCAL / "season-overlays-v1" / season / "opening-xi-v1" / "opening-lineup-reconciliation.json"
    managers = LOCAL / "season-overlays-v1" / season / "manager-v1" / "opening-manager-ledger.json"
    lineups = [
        LOCAL / "transfermarkt-opening-plans-current-v1" / season / "opening-lineups.json",
        LOCAL / "operations" / season / "opening-lineups.allocated-historic-id-v1.json",
    ]
    source_intake = LOCAL / "season-historical-squad-backfill-v1" / season / "source-intake.json"
    foreign = LOCAL / "season-provisional-compile-packages-v1" / season / "draft-season-package.json"
    calendar = LOCAL / "calendar-v1" / season / "MANAGPRE.EXE"
    _require([preallocation, preseason_standings, reconciliation, managers, *lineups, source_intake, foreign,
              calendar, BASE / "DBDAT", VERIFIED_BASE, SELECTOR_MAP])
    if end >= STAGES.index("kit-archives"):
        # The kit renderer treats a missing cache as per-club unavailable art.
        # The promotion coordinator instead fails closed: its durable cache is
        # a required, hash-bound replay input for this stage.
        _require([PATTERN_CACHE / "pattern-index", PATTERN_CACHE / "patterns"])

    py = sys.executable
    if end >= 0:
        overrides = ROOT / "data" / "season-opening-overrides-v1" / f"{season}.json"
        composed_preallocation = (
            chain / "opening-squad-preallocation.composed.json"
            if overrides.exists() else chain / "opening-squad-preallocation.json"
        )
        command = [py, "scripts/compose_english_opening_evidence_v1.py",
                   "--preallocation", str(preallocation), "--reconciliation", str(reconciliation),
                   "--manager-ledger", str(managers)]
        for lineup in lineups:
            command += ["--lineup-source", str(lineup)]
        command += ["--output-preallocation", str(composed_preallocation),
                    "--output-reconciliation", str(chain / "opening-lineup-reconciliation.json"),
                    "--output-manager-ledger", str(chain / "opening-manager-ledger.json"),
                    "--output-audit", str(chain / "english-opening-evidence-composition-audit.json")]
        events.append(_run(command, terminal=chain / "english-opening-evidence-composition-audit.json"))
        if overrides.exists():
            events.append(_run([
                py, "scripts/apply_opening_preallocation_overrides_v1.py",
                "--preallocation", str(composed_preallocation),
                "--overrides", str(overrides),
                "--output", str(chain / "opening-squad-preallocation.json"),
                "--output-audit", str(chain / "opening-preallocation-override-audit.json"),
            ], terminal=chain / "opening-preallocation-override-audit.json"))

    if end >= 1:
        manager_overrides = ROOT / "data" / "season-manager-overrides-v1" / f"{season}.json"
        manager_layer = (
            chain / "english-manager-layer.composed.json"
            if manager_overrides.exists() else chain / "english-manager-layer.json"
        )
        events.append(_run([
            py, "scripts/materialise_english_opening_manager_layers_v1.py",
            "--preallocation", str(chain / "opening-squad-preallocation.json"),
            "--reconciliation", str(chain / "opening-lineup-reconciliation.json"),
            "--manager-ledger", str(chain / "opening-manager-ledger.json"),
            "--output-openings", str(chain / "english-opening-layer.json"),
            "--output-managers", str(manager_layer),
            "--output-audit", str(chain / "english-opening-manager-audit.json"),
        ], terminal=chain / "english-opening-manager-audit.json"))
        if manager_overrides.exists():
            events.append(_run([
                py, "scripts/apply_english_manager_layer_overrides_v1.py",
                "--layer", str(manager_layer), "--overrides", str(manager_overrides),
                "--output", str(chain / "english-manager-layer.json"),
                "--output-audit", str(chain / "english-manager-override-audit.json"),
            ], terminal=chain / "english-manager-override-audit.json"))
        events.append(_run([
            py, "scripts/materialise_english_rating_layer_v1.py",
            "--preallocation", str(chain / "opening-squad-preallocation.json"),
            "--preseason-standings", str(preseason_standings),
            "--output-ratings", str(chain / "english-rating-layer.json"),
            "--output-audit", str(chain / "english-rating-audit.json"),
        ], terminal=chain / "english-rating-audit.json"))

    if end >= 2:
        command = [py, "scripts/season_hfk_english_kit_layer_v1.py",
                   "--source-intake", str(source_intake),
                   "--cache-dir", str(LOCAL / "hfk-evidence-cache-v1"),
                   "--output-layer", str(kit_root / "kit-layer.json")]
        if allow_network:
            command.append("--allow-network")
        events.append(_run(command, terminal=kit_root / "kit-layer.json"))

    if end >= 3:
        events.append(_run([
            py, "scripts/season_english_fixed_carrier_authoring_v1.py",
            "--source", str(chain / "opening-squad-preallocation.json"),
            "--selector-map", str(SELECTOR_MAP),
            "--openings", str(chain / "english-opening-layer.json"),
            "--managers", str(chain / "english-manager-layer.json"),
            "--kits", str(kit_root / "kit-layer.json"),
            "--ratings", str(chain / "english-rating-layer.json"),
            "--output-audit", str(author / "english-authoring-audit.json"),
            "--output-compiler-input", str(author / "english-compiler-input.json"),
        ], terminal=author / "english-compiler-input.json"))

    if end >= 4:
        events.append(_run([
            py, "scripts/season_english_mode0_package_adapter_v1.py",
            "--english-input", str(author / "english-compiler-input.json"),
            "--foreign-package", str(foreign), "--base-tree", str(BASE),
            "--package-id", f"worldwide-{season}-source-backed-{revision}",
            "--output-package", str(merged / "provisional-season-package.json"),
            "--output-receipt", str(merged / "adapter-receipt.json"),
            "--allow-provisional-duplicates",
        ], terminal=merged / "adapter-receipt.json"))
        events.append(_run([
            py, "scripts/prepare_provisional_compile_package_v1.py",
            "--package", str(merged / "provisional-season-package.json"),
            "--base-tree", str(BASE), "--verified-base", str(VERIFIED_BASE),
            "--output-package", str(merged / "strict-season-package.json"),
            "--output-audit", str(merged / "duplicate-normalisation-audit.json"),
        ], terminal=merged / "duplicate-normalisation-audit.json"))

    if end >= 5:
        events.append(_run([
            py, "scripts/season_static_ingress_v1.py",
            "--package", str(merged / "strict-season-package.json"),
            "--base-tree", str(BASE), "--verified-base", str(VERIFIED_BASE),
            "--output-dir", str(ingress),
        ], terminal=ingress / "static-ingress-receipt.json"))

    if end >= 6:
        events.append(_run([
            py, "scripts/season_kit_render_bindings_v1.py",
            "--english-compiler-input", str(author / "english-compiler-input.json"),
            "--clean-dbdat", str(BASE / "DBDAT"), "--output-dir", str(renders),
            "--pattern-cache-dir", str(PATTERN_CACHE),
        ], terminal=renders / "kit-render-receipt-v1.json"))
        events.append(_run([
            py, "scripts/materialise_season_kit_archives_v1.py",
            "--kit-render-bindings", str(renders / "kit-render-bindings-v1.json"),
            "--kit-render-receipt", str(renders / "kit-render-receipt-v1.json"),
            "--clean-dbdat", str(BASE / "DBDAT"), "--output-dir", str(archives),
        ], terminal=archives / "kit-archive-materialisation-receipt-v1.json"))

    if end >= 7:
        if not runtime.exists():
            shutil.copytree(ingress / "game", runtime)
            for name in ("RIDIESC.PKF", "MINIESC.PKF", "NANOESC.PKF"):
                source = archives / name
                if not source.exists():
                    source = archives / "archives" / name
                shutil.copy2(source, runtime / "DBDAT" / name)
            shutil.copy2(calendar, runtime / "MANAGPRE.EXE")
            status = "built"
        else:
            status = "reused"
        events.append({"status": status, "terminal": str(runtime.relative_to(ROOT))})

    receipt = {
        "schema_version": "pm99-post1999-worldwide-promotion-v1",
        "season": season,
        "revision": revision,
        "kit_revision": kit_revision,
        "through": through,
        "events": events,
        "runtime_game": str(runtime.relative_to(ROOT)) if end >= 7 else None,
        "status": "complete-through-" + through,
    }
    receipt_path = merged / "promotion-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="season key such as 2002-03")
    parser.add_argument("--revision", default="r1")
    parser.add_argument("--kit-revision", help="reuse an independently versioned kit layer")
    parser.add_argument("--through", choices=STAGES, default="runtime")
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    receipt = promote(args.season, revision=args.revision, kit_revision=args.kit_revision, through=args.through,
                      allow_network=args.allow_network)
    print(json.dumps({"season": args.season, "status": receipt["status"],
                      "runtime_game": receipt["runtime_game"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
