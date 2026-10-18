#!/usr/bin/env python3
"""Provider-scoped source player identity: parsing, validation and screening.

A source identity is the optional object ``{"provider": "transfermarkt",
"player_id": "<digits>"}`` taken literally from a ``/profil/spieler/<id>``
link.  The identifier is only meaningful inside its provider namespace, it is
never inferred from a name, and an absent object means *unknown* (not
"unique").  This module is deliberately dependency-free so that capture,
intake, package-builder and QA code can share one definition.

``audit_entries`` is candidate screening only.  It cannot prove that a roster
is duplicate-free or that a reported candidate is a historical defect.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

AUDIT_SCHEMA = "pm99-player-identity-audit-v1"
IDENTITY_FIELD = "source_identity"
# Provider namespace -> accepted identifier syntax.  Adding a provider is an
# explicit decision (schema enum + this table), not an open-ended string.
PROVIDER_ID_PATTERNS = {"transfermarkt": r"[1-9][0-9]{0,17}"}
_PROFILE_LINK_RE = re.compile(r"/profil/spieler/([0-9]+)(?:/|$)")
_TRANSFERMARKT_DOMAINS = {"transfermarkt.com", "transfermarkt.de", "transfermarkt.co.uk"}
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class IdentityError(ValueError):
    """Identity metadata is malformed or contradicts itself."""


def profile_id_from_href(href: Any) -> str | None:
    """Return the literal Transfermarkt player ID in ``href``, else ``None``.

    A link without a canonical positive integer (including zero-padded forms)
    stays unknown; nothing is repaired or guessed.
    """

    if not isinstance(href, str):
        return None
    try:
        parsed = urlsplit(href)
    except ValueError:
        return None
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc:
        host = (parsed.hostname or "").lower()
        if parsed.username is not None or parsed.password is not None or not any(
            host == domain or host.endswith("." + domain) for domain in _TRANSFERMARKT_DOMAINS
        ):
            return None
    elif parsed.scheme or not parsed.path.startswith("/"):
        return None
    match = _PROFILE_LINK_RE.search(parsed.path)
    if match is None or re.fullmatch(PROVIDER_ID_PATTERNS["transfermarkt"], match.group(1)) is None:
        return None
    return match.group(1)


def validate_source_identity(value: Any, *, label: str = "source_identity") -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"provider", "player_id"}:
        raise IdentityError(f"{label} must contain exactly provider and player_id")
    provider, player_id = value["provider"], value["player_id"]
    pattern = PROVIDER_ID_PATTERNS.get(provider) if isinstance(provider, str) else None
    if pattern is None:
        raise IdentityError(f"{label}.provider is not a supported provider namespace")
    if not isinstance(player_id, str) or re.fullmatch(pattern, player_id) is None:
        raise IdentityError(f"{label}.player_id is not a valid {provider} identifier")
    return {"provider": provider, "player_id": player_id}


def transfermarkt_identity(hrefs: Iterable[Any], *, label: str = "player row") -> dict[str, str] | None:
    """Collapse every profile link of one row to one identity or ``None``.

    Repeated markup for the same ID is one identity.  Two different IDs in one
    row cannot be resolved without choosing arbitrarily, so that is an error.
    """

    ids = sorted({found for href in hrefs if (found := profile_id_from_href(href)) is not None})
    if len(ids) > 1:
        raise IdentityError(f"{label} links several Transfermarkt player IDs: {ids}")
    return {"provider": "transfermarkt", "player_id": ids[0]} if ids else None


def identity_key(identity: Mapping[str, Any]) -> tuple[str, str]:
    return (str(identity["provider"]), str(identity["player_id"]))


def identity_sort_key(row: Mapping[str, Any]) -> tuple[str, int]:
    identity = row.get(IDENTITY_FIELD)
    return ("", 0) if identity is None else (str(identity["provider"]), int(identity["player_id"]))


def collapse_rows(rows: Iterable[Mapping[str, Any]], *, legacy_key: Callable[[Mapping[str, Any]], str]) -> list[dict[str, Any]]:
    """Deduplicate parsed rows, preserving first-seen order.

    Rows with an identity are keyed by (provider, ID) only, so namesakes with
    different IDs stay distinct and identical repeats collapse.  A repeat whose
    facts differ is a conflict.  Rows without an identity keep the legacy
    caller-supplied key and are never merged with an identified row.
    """

    by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    legacy_seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        identity = row.get(IDENTITY_FIELD)
        if identity is None:
            key = legacy_key(row)
            if key not in legacy_seen:
                legacy_seen.add(key)
                result.append(dict(row))
            continue
        key = identity_key(validate_source_identity(identity))
        previous = by_identity.get(key)
        if previous is None:
            by_identity[key] = dict(row)
            result.append(by_identity[key])
        elif previous != dict(row):
            fields = sorted(name for name in set(previous) | set(row) if previous.get(name) != row.get(name))
            raise IdentityError(f"{key[0]} player {key[1]} is repeated with conflicting {fields}")
    return result


def normalise_person_name(value: Any) -> str:
    """Same name key as ``season_package_v2._person_candidate_key``."""

    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char.casefold() for char in decomposed if char.isalnum())


def _entry(ref: Any, club: Any, name: Any, birth_date: Any, identity: Any, shirt: Any, native: bool,
           identity_declared: bool = False) -> dict[str, Any]:
    return {
        "ref": str(ref), "club": None if club is None else str(club),
        "name": name if isinstance(name, str) else None,
        "birth_date": birth_date if isinstance(birth_date, str) and _DATE_RE.fullmatch(birth_date) else None,
        "source_identity": identity, "shirt_number": shirt if isinstance(shirt, int) and not isinstance(shirt, bool) else None,
        "native_preserved": native, "_identity_declared": identity_declared,
    }


def entries_from_package(players: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for player in players:
        facts = player.get("facts") if isinstance(player.get("facts"), Mapping) else {}
        result.append(_entry(
            player.get("id"), player.get("club_id"), player.get("source_name") or player.get("name"),
            facts.get("birth_date"), player.get(IDENTITY_FIELD), None,
            player.get("policy") == "preserve-existing-mode1",
            IDENTITY_FIELD in player,
        ))
    return result


def entries_from_capture(capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for club in capture.get("clubs") or []:
        for index, player in enumerate(club.get("players") or []):
            result.append(_entry(
                f"{club.get('club_name')}#{index}", club.get("club_name"), player.get("name"),
                player.get("birth_date"), player.get(IDENTITY_FIELD), player.get("shirt_number"), False,
                IDENTITY_FIELD in player,
            ))
    return result


def _digest(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _member(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {key: entry[key] for key in ("ref", "club", "name", "birth_date", "shirt_number")}


def audit_entries(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministically screen entries for identity candidates and conflicts.

    Findings are *unreviewed candidates or metadata conflicts*; none is a
    confirmed historical defect, and nothing here selects, drops or resolves a
    row (a loan or transfer is indistinguishable from a duplicate here).
    """

    rows = sorted((dict(entry) for entry in entries), key=lambda row: (row["ref"], row["club"] or ""))
    malformed: list[dict[str, str]] = []
    identified: list[tuple[tuple[str, str], dict[str, Any]]] = []
    for row in rows:
        raw = row.get(IDENTITY_FIELD)
        row["_key"] = None
        if raw is None and not row.get("_identity_declared", False):
            continue
        try:
            row["_key"] = identity_key(validate_source_identity(raw))
        except IdentityError as exc:
            malformed.append({"ref": row["ref"], "error": str(exc)})
            continue
        identified.append((row["_key"], row))

    by_id: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for key, row in identified:
        by_id[key].append(row)
    id_candidates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for key, members in sorted(by_id.items()):
        if len(members) < 2:
            continue
        names = {normalise_person_name(row["name"]) for row in members if row["name"]}
        dates = {row["birth_date"] for row in members if row["birth_date"]}
        fields = [field for field, values in (("name", names), ("birth_date", dates)) if len(values) > 1]
        candidate = {
            "key": f"provider-id:{key[0]}:{key[1]}", "provider": key[0], "player_id": key[1],
            "classification": "strong-duplicate-candidate", "status": "unreviewed",
            "members": [_member(row) for row in members],
            "distinct_clubs": len({row["club"] for row in members}) > 1,
            "distinct_shirt_numbers": len({row["shirt_number"] for row in members if row["shirt_number"] is not None}) > 1,
            "birth_date_known_for_all": all(row["birth_date"] for row in members),
            "metadata_conflict_fields": fields,
        }
        id_candidates.append(candidate)
        if fields:
            conflicts.append({"key": candidate["key"], "provider": key[0], "player_id": key[1], "fields": fields})

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        normalised = normalise_person_name(row["name"])
        if normalised and row["birth_date"]:
            groups[(normalised, row["birth_date"])].append(row)
    fallback_candidates: list[dict[str, Any]] = []
    distinct_namesakes: list[dict[str, Any]] = []
    for (normalised, birth_date), members in sorted(groups.items()):
        involved: dict[str, dict[str, Any]] = {}
        distinct: dict[str, dict[str, Any]] = {}
        for left_index, left in enumerate(members):
            for right in members[left_index + 1:]:
                if left["_key"] is not None and left["_key"] == right["_key"]:
                    continue  # reported as a provider-ID candidate
                if left["_key"] is not None and right["_key"] is not None and left["_key"][0] == right["_key"][0]:
                    distinct.update({left["ref"]: left, right["ref"]: right})
                else:
                    # Missing or cross-provider identity: no proof either way.
                    involved.update({left["ref"]: left, right["ref"]: right})
        key = f"name-birth-date:{_digest(normalised, birth_date)}"
        if involved:
            fallback_candidates.append({
                "key": key, "normalised_name": normalised, "birth_date": birth_date,
                "classification": "name-birth-date-candidate", "status": "unreviewed",
                "members": [_member(involved[ref]) for ref in sorted(involved)],
            })
        if distinct:
            distinct_namesakes.append({
                "key": key, "normalised_name": normalised, "birth_date": birth_date,
                "classification": "distinct-provider-id-namesakes",
                "members": [
                    dict(_member(distinct[ref]), provider=distinct[ref]["_key"][0], player_id=distinct[ref]["_key"][1])
                    for ref in sorted(distinct)
                ],
            })

    missing = [row for row in rows if row["_key"] is None and row.get(IDENTITY_FIELD) is None
               and not row.get("_identity_declared", False)]
    # Neither rule can screen a row lacking both a usable ID and a birth date.
    insufficient = [row for row in rows if row["_key"] is None and not row["birth_date"]]
    provider_counts = Counter(row["_key"][0] for _key, row in identified)
    complete = bool(rows) and not missing and not malformed
    result = {
        "schema_version": AUDIT_SCHEMA,
        "verification": "candidate-screening-only; historical identity is not verified",
        "coverage": {
            "entry_count": len(rows),
            "with_provider_identity": len(identified),
            "malformed_provider_identity": len(malformed),
            "missing_provider_identity": len(missing),
            "missing_provider_identity_native_preserved": sum(1 for row in missing if row["native_preserved"]),
            "provider_identity_counts": dict(sorted(provider_counts.items())),
            "with_birth_date": sum(1 for row in rows if row["birth_date"]),
            "missing_birth_date": sum(1 for row in rows if not row["birth_date"]),
            "missing_identity_and_birth_date": len(insufficient),
            "screening": "complete-provider-identity" if complete else "incomplete",
            "duplicate_free_verified": False,
        },
        "malformed_identities": malformed,
        "same_provider_id_candidates": id_candidates,
        "metadata_conflicts": conflicts,
        "name_birth_date_candidates": fallback_candidates,
        "distinct_provider_id_namesakes": distinct_namesakes,
        "insufficient_identity_facts": [_member(row) for row in insufficient],
    }
    result["counts"] = {
        name: len(result[name]) for name in (
            "malformed_identities", "same_provider_id_candidates", "metadata_conflicts",
            "name_birth_date_candidates", "distinct_provider_id_namesakes", "insufficient_identity_facts",
        )
    }
    return result
