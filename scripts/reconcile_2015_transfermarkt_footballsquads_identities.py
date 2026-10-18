#!/usr/bin/env python3
"""Reconcile dated Transfermarkt clubs to FootballSquads identities.

Transfermarkt's canonical club names are often legal names, transliterations or
names carrying a later dissolution suffix, while the captured FootballSquads
source uses 2015 display names.  This receipt joins the two sources by country
and by an explicit, reviewable override table.  It never performs similarity
matching and never creates a PM99 carrier assignment.

The override table is intentionally in source so every non-trivial identity
decision is visible in code review.  A future source refresh must fail closed
until its new unmatched names receive an explicit decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_world_2015_source_coverage import strict_club_key  # noqa: E402
from scripts.prepare_2015_world_fifa16_carrier_allocation import group_for_carrier  # noqa: E402
from scripts.prepare_2015_world_source_carrier_drafts import (  # noqa: E402
    GROUP_TO_SOURCE_COMPETITIONS,
    GROUP_TO_SOURCE_COUNTRY,
)

SCHEMA = "pm99-world-2015-transfermarkt-footballsquads-identity-reconciliation-v1"
FS_SCHEMA = "pm99-footballsquads-season-capture-v1"
TM_SCHEMA = "pm99-world-2015-transfermarkt-opening-fixtures-v1"
DRAFT_SCHEMA = "pm99-world-2015-source-carrier-drafts-v1"

# Explicit 2015 identity equivalences.  The country key is mandatory: a name
# alone is never allowed to cross a country family.  Suffixes such as
# "(-2020)" and legal-form words are historical/source-name facts, not fuzzy
# matching rules.
_OVERRIDE_PAIRS: dict[str, tuple[tuple[str, str], ...]] = {
    "belgium": (
        ("RSC Anderlecht", "Anderlecht"), ("Royal Charleroi Sporting Club", "Charleroi"),
        ("KV Mechelen", "Mechelen"), ("Sint-Truidense VV", "Sint-Truiden"),
        ("KSC Lokeren (- 2020)", "Lokeren"), ("KV Kortrijk", "Kortrijk"),
        ("Club Brugge KV", "Club Brugge"), ("SK Beveren", "Waasland-Beveren"),
        ("Royal Excel Mouscron (-2022)", "Royal Mouscron-Péruwelz"),
    ),
    "denmark": (
        ("Odense Boldklub", "Odense"), ("FC Copenhagen", "FC København"),
        ("Bröndby IF", "Brøndby"), ("Aarhus GF", "Aarhus"),
        ("Aalborg BK", "Aalborg"), ("Viborg FF", "Viborg"),
        ("FC Nordsjaelland", "FC Nordsjælland"), ("Esbjerg fB", "Esbjerg"),
        ("Sönderjyske Fodbold", "SønderjyskE"), ("Hobro IK", "Hobro"),
    ),
    "france": (
        ("FC Girondins Bordeaux", "Bordeaux"), ("AS Monaco", "Monaco"),
        ("Olympique Marseille", "Marseille"), ("Stade Rennais FC", "Rennes"),
        ("OGC Nice", "Nice"), ("SC Bastia", "Bastia"),
        ("AS Saint-Étienne", "Saint-Etienne"), ("EA Guingamp", "Guingamp"),
        ("Montpellier HSC", "Montpellier"), ("Olympique Lyon", "Lyon"),
        ("LOSC Lille", "Lille"), ("ESTAC Troyes", "Troyes"),
        ("SM Caen", "Caen"), ("Angers SCO", "Angers"),
        ("Stade Reims", "Reims"), ("GFC Ajaccio", "Gazélec Ajaccio"),
    ),
    "ger": (
        ("Bayer 04 Leverkusen", "Bayer Leverkusen"), ("1.FSV Mainz 05", "FSV Mainz 05"),
        ("Hertha BSC", "Hertha Berlin"), ("SV Werder Bremen", "Werder Bremen"),
        ("TSG 1899 Hoffenheim", "1899 Hoffenheim"),
    ),
    "greece": (
        ("Iraklis Thessaloniki", "Iraklis"), ("AO Xanthi", "Skoda Xanthi"),
        ("Panionios Athens", "Panionios"), ("Panathinaikos Athlitikos Omilos", "Panathinaikos"),
        ("Olympiakos Syndesmos Filathlon Peiraios", "Olympiakos"),
        ("Panthessalonikios Athlitikos Omilos Konstantinoupoliton", "PAOK"),
        ("Athlitiki Enosi Konstantinoupoleos", "AEK"), ("APO Levadiakos Football Club", "Levadiakos"),
        ("APS Atromitos Athinon", "Atromitos"), ("Veria NPS", "Veria"),
        ("Panetolikos Agrinio", "Panetolikos"), ("A.G.S Asteras Tripolis", "Asteras Tripolis"),
        ("AO Platanias", "Platanias"), ("AEL Kalloni", "Kalloni"),
        ("Panthrakikos Komotini", "Panthrakikos"),
    ),
    "italy": (
        ("AC Milan", "Milan"), ("Associazione Sportiva Roma", "Roma"),
        ("Inter Milan", "Internazionale"), ("Genoa CFC", "Genoa"),
        ("Hellas Verona", "Verona"), ("Società Sportiva Lazio S.p.A.", "Lazio"),
        ("ACF Fiorentina", "Fiorentina"), ("Atalanta BC", "Atalanta"),
        ("Bologna Football Club 1909", "Bologna"), ("UC Sampdoria", "Sampdoria"),
        ("AC Carpi", "Carpi"), ("SSC Napoli", "Napoli"), ("US Sassuolo", "Sassuolo"),
    ),
    "netherl": (
        ("SC Cambuur Leeuwarden", "SC Cambuur"), ("Feyenoord Rotterdam", "Feyenoord"),
        ("FC Twente Enschede", "FC Twente"), ("Willem II Tilburg", "Willem II"),
        ("Vitesse Arnhem", "Vitesse"), ("Ajax Amsterdam", "Ajax"),
        ("De Graafschap Doetinchem", "De Graafschap"), ("Excelsior Rotterdam", "Excelsior"),
    ),
    "portugal": (
        ("SL Benfica", "Benfica"), ("CF União Madeira (-2021)", "União da Madeira"),
        ("CD Nacional", "Nacional"), ("SC Braga", "Sporting Braga"),
        ("CS Marítimo", "Marítimo"), ("GD Estoril Praia", "Estoril"),
        ("Vitória Guimarães SC", "Vitória Guimarães"), ("Académica Coimbra", "Académica"),
        ("CD Tondela", "Tondela"), ("CF Os Belenenses", "Belenenses"),
    ),
    "russia": (
        ("FK Dinamo Moskva", "Dynamo Moscow"), ("FK Spartak Moskva", "Spartak Moscow"),
        ('Футбольный клуб "Локомотив" Москва', "Lokomotiv Moscow"),
        ("AO FK Zenit Sankt-Peterburg", "Zenit St. Petersburg"), ("FK Rostov", "FC Rostov"),
        ("PFK CSKA Moskva", "CSKA Moscow"), ("Kuban Krasnodar (-2018)", "Kuban Krasnodar"),
        ("PFK Krylya Sovetov Samara", "Krylia Sovetov"),
        ("Anzhi Makhachkala ( -2022)", "Anzhi Makhachkala"),
        ("Mordovia Saransk (-2020)", "Mordovia Saransk"), ("Ural Yekaterinburg", "FC Ural"),
        ("FK Krasnodar", "FC Krasnodar"), ("FK Ufa", "FC Ufa"),
        ("RFK Akhmat Grozny", "Terek Grozny"),
    ),
    "spain": (
        ("Atlético de Madrid", "Atlético Madrid"), ("Real Betis Balompié", "Betis"),
        ("UD Las Palmas", "Las Palmas"), ("Deportivo de La Coruña", "Deportivo La Coruña"),
        ("Celta de Vigo", "Celta Vigo"), ("RCD Espanyol Barcelona", "Espanyol"),
        ("SD Eibar", "Eibar"), ("Levante UD", "Levante"),
    ),
    "turkey": (
        ("Beşiktaş Jimnastik Kulübü", "Besiktas"), ("Caykur Rizespor", "Rizespor"),
        ("Gaziantepspor (- 2020)", "Gaziantepspor"),
        ("Gençlerbirliği Spor Kulübü", "Gençlerbirligi"), ("Ankaraspor", "Osmanlıspor"),
        ("Mersin Talimyurdu SK", "Mersin Idman Yurdu"), ("Basaksehir FK", "İstanbul Başakşehir"),
        ("Akhisarspor", "Akhisar Belediyespor"), ("Kasimpasa", "Kasımpaşa"),
    ),
    "ukraine": (
        ("Dnipro Dnipropetrovsk (-2020)", "Dnipro Dnipropetrovsk"),
        ("Karpaty Lviv (-2021)", "Karpaty Lviv"), ("Metalist Kharkiv (- 2016)", "Metalist Kharkiv"),
        ("Chornomorets Odesa", "Chornomorets Odessa"),
        ("Metalurg Zaporizhya (-2016)", "Metalurh Zaporizhya"),
        ("Goverla Uzhgorod (- 2016)", "Hoverla Uzhhorod"), ("Zorya Lugansk", "Zorya Luhansk"),
        ("PFK Stal Kamyanske (-2018)", "Stal Dniprodzerzhynsk"),
    ),
}

EXPLICIT_OVERRIDES = {
    (country, transfermarkt_name): footballsquads_name
    for country, pairs in _OVERRIDE_PAIRS.items()
    for transfermarkt_name, footballsquads_name in pairs
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_bytes(value):
        raise ValueError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _identity(country: object, name: object) -> tuple[str, str]:
    key = strict_club_key(name)
    if not str(country or "") or not key:
        raise ValueError("club has no country-scoped strict identity")
    return str(country), key


def _selector(club: Mapping[str, Any]) -> dict[str, str]:
    fields = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")
    value = {field: str(club.get(field) or "") for field in fields}
    if not all(value.values()):
        raise ValueError("FootballSquads club has incomplete source selector")
    return value


def _draft_index(draft: Mapping[str, Any], capture_sha: str) -> dict[tuple[str, str, str, str, str], list[int]]:
    if draft.get("schema_version") != DRAFT_SCHEMA or draft.get("source_capture_sha256") != capture_sha:
        raise ValueError("source draft is not bound to this FootballSquads capture")
    result: dict[tuple[str, str, str, str, str], list[int]] = defaultdict(list)
    for row in draft.get("proposals", []):
        if row.get("status") != "source-squad-ready":
            continue
        selector = _selector(row.get("source_selector") or {})
        result[tuple(selector.values())].append(int(row["carrier_id"]))
    for carriers in result.values():
        carriers.sort()
    return result


def build_reconciliation(
    *, source_capture: Mapping[str, Any], fixture_receipt: Mapping[str, Any], source_draft: Mapping[str, Any],
    source_capture_sha256: str, fixture_receipt_sha256: str, source_draft_sha256: str,
) -> dict[str, Any]:
    if source_capture.get("schema_version") != FS_SCHEMA or not isinstance(source_capture.get("clubs"), list):
        raise ValueError("invalid FootballSquads capture")
    if fixture_receipt.get("schema_version") != TM_SCHEMA or not isinstance(fixture_receipt.get("clubs"), list):
        raise ValueError("invalid Transfermarkt receipt")
    capture_by_identity: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for club in source_capture["clubs"]:
        identity = _identity(club.get("country_catalog"), club.get("club_name"))
        capture_by_identity[identity].append(club)
    draft_by_selector = _draft_index(source_draft, source_capture_sha256)

    seen: set[tuple[str, str]] = set()
    mappings: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    strict_count = 0
    override_count = 0
    for club in sorted(fixture_receipt["clubs"], key=lambda row: (str(row.get("country_catalog")), str((row.get("source_club") or {}).get("name")))):
        source_club = club.get("source_club")
        if not isinstance(source_club, dict):
            raise ValueError("Transfermarkt club has no source_club")
        country = str(club.get("country_catalog") or "")
        tm_name = str(source_club.get("name") or "")
        tm_key = strict_club_key(tm_name)
        tm_identity = (country, tm_key or "non-comparable-under-strict-club-key:" + tm_name.casefold())
        if tm_identity in seen:
            raise ValueError(f"duplicate Transfermarkt identity: {tm_identity}")
        seen.add(tm_identity)
        capture_rows = capture_by_identity.get((country, tm_key), []) if tm_key else []
        fs_club = capture_rows[0] if len(capture_rows) == 1 else None
        method = "strict-country-and-name"
        override = None
        if fs_club is None:
            override = EXPLICIT_OVERRIDES.get((country, tm_name))
            if override is None:
                unresolved.append({"country_catalog": country, "transfermarkt_club_name": tm_name, "strict_identity": tm_identity, "status": "unresolved-no-explicit-override"})
                continue
            target_identity = _identity(country, override)
            target_rows = capture_by_identity.get(target_identity, [])
            fs_club = target_rows[0] if len(target_rows) == 1 else None
            if fs_club is None:
                unresolved.append({"country_catalog": country, "transfermarkt_club_name": tm_name, "strict_identity": tm_identity, "override_target": override, "status": "unresolved-override-target-missing"})
                continue
            method = "explicit-country-scoped-override"
            override_count += 1
        else:
            strict_count += 1
        selector = _selector(fs_club)
        selector_key = tuple(selector.values())
        mappings.append({
            "country_catalog": country,
            "transfermarkt_source_club": {"id": source_club.get("id"), "name": tm_name},
            "transfermarkt_strict_identity": {"country_catalog": tm_identity[0], "strict_club_key": tm_identity[1]},
            "footballsquads_club": {"name": fs_club.get("club_name"), "strict_club_key": strict_club_key(fs_club.get("club_name"))},
            "identity_method": method,
            "explicit_override": {"transfermarkt_name": tm_name, "footballsquads_name": override, "basis": "unambiguous 2015 club identity / legal name / transliteration / historical rename"} if override else None,
            "footballsquads_source_selector": selector,
            "selected_source_draft_carrier_ids": draft_by_selector.get(selector_key, []),
            "opening_fixture_source": {
                "source_game_id": (club.get("opening_fixture") or {}).get("source_game_id"),
                "date": (club.get("opening_fixture") or {}).get("date"),
                "source_url": (club.get("opening_fixture") or {}).get("source_url"),
            },
            "compiler_disposition": "source-identity-receipt-only; no-PM99-assignment-or-write",
        })

    # Every override must be exercised by this exact snapshot.  This prevents
    # stale/typoed override rows from silently becoming authority.
    unmatched_raw_keys: set[tuple[str, str]] = set()
    for club in fixture_receipt["clubs"]:
        source_club = club.get("source_club") or {}
        country = str(club.get("country_catalog") or "")
        name = str(source_club.get("name") or "")
        key = strict_club_key(name)
        identity = (country, key or "non-comparable-under-strict-club-key:" + name.casefold())
        if not key or identity not in capture_by_identity:
            unmatched_raw_keys.add((country, name))
    override_keys = set(EXPLICIT_OVERRIDES)
    stale = sorted(override_keys - unmatched_raw_keys)
    if stale:
        raise ValueError(f"override table contains stale fixture identities: {stale[:3]}")
    missing_overrides = sorted(unmatched_raw_keys - override_keys)
    if missing_overrides:
        raise ValueError(f"unmatched fixture identities lack explicit overrides: {missing_overrides[:3]}")

    # Reconcile the existing 149 source-draft gaps without inventing a new
    # assignment.  An exact full squad can close the identity question, but a
    # selector already consumed by another carrier remains a carrier-level
    # conflict and is reported as such.
    gap_rows: list[dict[str, Any]] = []
    ready_selector_users = draft_by_selector
    fs_by_selector = {
        tuple(_selector(club).values()): club
        for club in source_capture["clubs"]
        if isinstance(club, dict)
    }
    tm_by_selector: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for mapping in mappings:
        selector = mapping["footballsquads_source_selector"]
        tm_by_selector[tuple(selector.values())].append(mapping)
    gap_proposals = [row for row in source_draft.get("proposals", []) if row.get("status") != "source-squad-ready"]
    for proposal in sorted(gap_proposals, key=lambda row: int(row["carrier_id"])):
        carrier_id = int(proposal["carrier_id"])
        group = group_for_carrier(carrier_id)
        baseline = str(proposal.get("baseline_name") or "")
        slots = int(proposal.get("fixed_roster_slot_count") or 0)
        country = GROUP_TO_SOURCE_COUNTRY.get(str(group or ""))
        competitions = sorted(GROUP_TO_SOURCE_COMPETITIONS.get(str(group or ""), set()))
        candidate_selectors = []
        if country and competitions:
            target_identity = (country, strict_club_key(baseline))
            for selector, club in fs_by_selector.items():
                if (
                    selector[0] == country
                    and selector[1] in competitions
                    and _identity(club.get("country_catalog"), club.get("club_name")) == target_identity
                ):
                    candidate_selectors.append(selector)
        candidate_rows = []
        for selector in candidate_selectors:
            club = fs_by_selector[selector]
            capacity = len(club.get("players") or [])
            users = ready_selector_users.get(selector, [])
            candidate_rows.append({
                "source_selector": _selector(club),
                "source_player_row_count": capacity,
                "capacity_sufficient": capacity >= slots,
                "selected_by_ready_carrier_ids": users,
                "transfermarkt_identity_evidence": tm_by_selector.get(selector, []),
            })
        if any(row["capacity_sufficient"] and not row["selected_by_ready_carrier_ids"] for row in candidate_rows):
            status = "exact-source-identity-and-capacity-available"
        elif any(row["capacity_sufficient"] for row in candidate_rows):
            status = "identity-closed-carrier-unresolved-selector-conflict"
        else:
            status = "unresolved"
        gap_rows.append({
            "carrier_id": carrier_id,
            "group": group,
            "baseline_name": baseline,
            "fixed_roster_slot_count": slots,
            "existing_gap_status": proposal.get("status"),
            "source_country_catalog": country,
            "source_competition_catalogs": competitions,
            "carrier_reconciliation_status": status,
            "exact_source_candidates": candidate_rows,
            "guardrail": "Identity/capacity evidence only; no selector reuse, carrier assignment or PM99 write.",
        })
    gap_status_counts = Counter(row["carrier_reconciliation_status"] for row in gap_rows)

    return {
        "schema_version": SCHEMA,
        "season": "2015/16",
        "policy": "country-scoped-selected-2015-club-identity; explicit-overrides-only; no-fuzzy-auto-acceptance; no-pm99-write",
        "sources": {"footballsquads_capture_sha256": source_capture_sha256, "transfermarkt_fixture_receipt_sha256": fixture_receipt_sha256, "source_draft_sha256": source_draft_sha256, "override_table_sha256": hashlib.sha256(canonical_bytes({country: list(pairs) for country, pairs in sorted(_OVERRIDE_PAIRS.items())})).hexdigest()},
        "coverage": {"transfermarkt_club_count": len(fixture_receipt["clubs"]), "strict_name_match_count": strict_count, "explicit_override_match_count": override_count, "resolved_identity_count": len(mappings), "unresolved_identity_count": len(unresolved), "selected_source_draft_carrier_reference_count": sum(bool(row["selected_source_draft_carrier_ids"]) for row in mappings), "unresolved_by_country": dict(sorted(Counter(row["country_catalog"] for row in unresolved).items())), "source_gap_carrier_count": len(gap_rows), "source_gap_identity_closed_count": sum(value for key, value in gap_status_counts.items() if key != "unresolved"), "source_gap_unresolved_carrier_count": gap_status_counts.get("unresolved", 0), "source_gap_unresolved_carrier_ids": [row["carrier_id"] for row in gap_rows if row["carrier_reconciliation_status"] == "unresolved"], "source_gap_status_counts": dict(sorted(gap_status_counts.items()))},
        "mappings": mappings,
        "unresolved": unresolved,
        "source_gap_reconciliation": gap_rows,
        "guardrails": ["A mapping joins dated source identities only; it is not a PM99 carrier assignment.", "A selected source-draft carrier reference is informational and may be absent or already consumed by another carrier.", "No source from another country, similarity score or inferred alias is accepted."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--footballsquads-capture", type=Path, required=True)
    parser.add_argument("--opening-fixture-receipt", type=Path, required=True)
    parser.add_argument("--source-draft", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        capture, capture_sha = read_json(args.footballsquads_capture, "FootballSquads capture")
        receipt, receipt_sha = read_json(args.opening_fixture_receipt, "Transfermarkt receipt")
        draft, draft_sha = read_json(args.source_draft, "source draft")
        result = build_reconciliation(source_capture=capture, fixture_receipt=receipt, source_draft=draft, source_capture_sha256=capture_sha, fixture_receipt_sha256=receipt_sha, source_draft_sha256=draft_sha)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps({"output": str(args.output), **result["coverage"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
