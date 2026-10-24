"""Opt-in source-hash continuity guard for a season carrier allocation.

A preferred carrier is continued only when its package roster overlaps one
unique, template-pinned opening-preallocation source row by at least ten exact
player-row hashes and the target source selector retains the same country and
provider club ID. This proves allocation continuity only; it does not certify
historical correctness, roster completeness, or source-content authenticity.
"""
from __future__ import annotations
import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA = "pm99-season-source-hash-continuity-evidence-v1"
METHOD = "continuing-club-source-row-hash-identity"
PREALLOCATION_SCHEMA = "pm99-opening-squad-preallocation-v1"
INTAKE_SCHEMA = "pm99-season-source-intake-v1"
MIN_EXACT_ROW_OVERLAP = 10
_HEX = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_ID = re.compile(r"(?:^|/)(\d+)\.html$")


class SourceHashContinuityError(ValueError):
    """The requested continuation cannot be proven from pinned inputs."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def document_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _provider_id(source_path: Any, label: str) -> str:
    if not isinstance(source_path, str):
        raise SourceHashContinuityError(f"{label} source_path is missing")
    match = _PROVIDER_ID.search(source_path)
    if match is None:
        raise SourceHashContinuityError(f"{label} source_path has no terminal numeric club ID")
    return match.group(1)


def _selector(value: Any, label: str) -> dict[str, str]:
    fields = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")
    if not isinstance(value, Mapping):
        raise SourceHashContinuityError(f"{label} selector is malformed")
    result = {key: value.get(key) for key in fields}
    if any(not isinstance(result[key], str) or not result[key].strip() for key in fields):
        raise SourceHashContinuityError(f"{label} selector fields are incomplete")
    if not _HEX.fullmatch(result["source_sha256"]):
        raise SourceHashContinuityError(f"{label} source SHA-256 is malformed")
    return result


def _carrier_group(carrier_id: int) -> str | None:
    from scripts.prepare_2015_world_fifa16_carrier_allocation import group_for_carrier
    return group_for_carrier(carrier_id)


def _country_group(country_catalog: str) -> str | None:
    from scripts.season_carrier_allocation_v1 import COUNTRY_GROUPS
    return COUNTRY_GROUPS.get(country_catalog)


def _pinned_preallocation_artifact(template: Mapping[str, Any], preallocation_sha256: str) -> str:
    artifacts = template.get("artifacts")
    if not isinstance(artifacts, list):
        raise SourceHashContinuityError("template package has no artifact list")
    matches = [row for row in artifacts if isinstance(row, Mapping)
               and isinstance(row.get("id"), str)
               and row["id"].startswith("opening-squad-preallocation-")
               and row.get("kind") == "season-input"
               and row.get("sha256") == preallocation_sha256]
    if len(matches) != 1:
        raise SourceHashContinuityError("full old opening preallocation SHA is not uniquely pinned by the template artifact")
    return str(matches[0]["id"])


def _package_source_hashes(template: Mapping[str, Any], carrier_id: int) -> tuple[Mapping[str, Any], set[str]]:
    clubs = [row for row in template.get("clubs", []) if isinstance(row, Mapping) and row.get("carrier_id") == carrier_id]
    if len(clubs) != 1:
        raise SourceHashContinuityError(f"template must contain exactly one club for carrier {carrier_id}")
    club = clubs[0]
    players_by_id = {str(row.get("id")): row for row in template.get("players", []) if isinstance(row, Mapping)}
    ids = club.get("roster_player_ids")
    if not isinstance(ids, list) or not ids:
        raise SourceHashContinuityError(f"template carrier {carrier_id} has no roster player IDs")
    hashes: set[str] = set()
    for player_id in ids:
        player = players_by_id.get(str(player_id))
        if player is None or player.get("club_id") != club.get("id"):
            raise SourceHashContinuityError(f"template carrier {carrier_id} roster has a missing or misowned player")
        person_id = player.get("person_id")
        if isinstance(person_id, str) and person_id.startswith("person-source-"):
            source_hash = person_id[len("person-source-"):]
            if not _HEX.fullmatch(source_hash):
                raise SourceHashContinuityError(f"carrier {carrier_id} has malformed source-person hash")
            hashes.add(source_hash)
    return club, hashes


class SourceHashContinuityContext:
    """One-time hash/selector index for a single immutable builder invocation."""
    def __init__(self, *, template: Mapping[str, Any], original_template_sha256: str,
                 old_preallocation: Mapping[str, Any], source_intake: Mapping[str, Any],
                 registry: Mapping[str, Any], source_capture: Mapping[str, Any] | None,
                 source_assignment: Mapping[str, Any] | None):
        self.template = template
        self.old_preallocation = old_preallocation
        self.source_intake = source_intake
        self.registry = registry
        self.template_sha256 = document_sha256(template)
        if self.template_sha256 != original_template_sha256:
            raise SourceHashContinuityError("template package changed after original hash was captured")
        if old_preallocation.get("schema_version") != PREALLOCATION_SCHEMA:
            raise SourceHashContinuityError("old opening preallocation schema is unsupported")
        self.old_preallocation_sha256 = document_sha256(old_preallocation)
        self.old_preallocation_artifact_id = _pinned_preallocation_artifact(template, self.old_preallocation_sha256)
        if source_intake.get("schema_version") != INTAKE_SCHEMA:
            raise SourceHashContinuityError("source intake schema is unsupported")
        if source_intake.get("registry_sha256") != document_sha256(registry):
            raise SourceHashContinuityError("source intake targets a different fixed-carrier registry")
        if source_capture is None or source_assignment is None:
            raise SourceHashContinuityError(
                "source-hash continuity requires source capture and assignment for intake validation"
            )
        try:
            from scripts import season_source_intake_v1
            season_source_intake_v1.validate_intake(
                intake=source_intake,
                registry=registry,
                source_capture=source_capture,
                assignment=source_assignment,
            )
        except Exception as exc:
            raise SourceHashContinuityError(
                f"source intake is not validated by its capture and assignment: {exc}"
            ) from exc
        self.source_capture_sha256 = source_intake.get("source_capture_sha256")
        if not isinstance(self.source_capture_sha256, str) or not _HEX.fullmatch(self.source_capture_sha256):
            raise SourceHashContinuityError("source intake lacks a valid bound source-capture SHA")
        self.source_intake_sha256 = document_sha256(source_intake)
        source_rows = old_preallocation.get("source_clubs")
        if not isinstance(source_rows, list):
            raise SourceHashContinuityError("old opening preallocation has no source-club rows")
        self.old_rows_by_group: dict[str, list[tuple[dict[str, str], set[str]]]] = {}
        for row in source_rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("selector"), Mapping):
                raise SourceHashContinuityError("old preallocation contains malformed selector row")
            old_selector = _selector(row["selector"], "old preallocation")
            group = _country_group(old_selector["country_catalog"])
            if group is None:
                continue
            player_rows = row.get("players")
            if not isinstance(player_rows, list):
                raise SourceHashContinuityError("old preallocation source row has no players")
            hashes = set()
            for player in player_rows:
                if not isinstance(player, Mapping) or not _HEX.fullmatch(str(player.get("source_row_sha256") or "")):
                    raise SourceHashContinuityError("old preallocation has malformed source-row hash")
                hashes.add(str(player["source_row_sha256"]))
            self.old_rows_by_group.setdefault(group, []).append((old_selector, hashes))
        self.carriers_by_id = {int(row["carrier_id"]): row for row in registry.get("carriers", [])
                               if isinstance(row, Mapping) and isinstance(row.get("carrier_id"), int)}
        self._carrier_proofs: dict[int, tuple[Mapping[str, Any], dict[str, str], list[str], int, int]] = {}

    def _carrier_proof(self, carrier_id: int) -> tuple[Mapping[str, Any], dict[str, str], list[str], int, int]:
        cached = self._carrier_proofs.get(carrier_id)
        if cached is not None:
            return cached
        carrier = self.carriers_by_id.get(carrier_id)
        if carrier is None:
            raise SourceHashContinuityError(f"carrier {carrier_id} is absent from fixed registry")
        expected_group = _carrier_group(carrier_id)
        if expected_group is None:
            raise SourceHashContinuityError(f"carrier {carrier_id} is not a foreign country carrier")
        old_club, current_hashes = _package_source_hashes(self.template, carrier_id)
        registry_capacity = len(carrier.get("roster_slots") or [])
        package_capacity = len(old_club.get("roster_player_ids") or [])
        if package_capacity != registry_capacity:
            raise SourceHashContinuityError("preferred template roster capacity disagrees with fixed-carrier registry")
        candidates=[]
        for old_selector, old_hashes in self.old_rows_by_group.get(expected_group, []):
            overlap=sorted(current_hashes & old_hashes)
            candidates.append((len(overlap),old_selector,overlap))
        candidates.sort(key=lambda item:(-item[0],item[1]["source_path"]))
        if not candidates or candidates[0][0] < MIN_EXACT_ROW_OVERLAP:
            raise SourceHashContinuityError(f"carrier {carrier_id} has fewer than {MIN_EXACT_ROW_OVERLAP} exact source-row overlaps")
        if len(candidates)>1 and candidates[1][0]==candidates[0][0]:
            raise SourceHashContinuityError(f"carrier {carrier_id} matches multiple old preallocation rows equally")
        count, old_selector, overlap = candidates[0]
        result=(old_club,old_selector,overlap,count,registry_capacity)
        self._carrier_proofs[carrier_id]=result
        return result

    def derive(self, *, carrier_id: int, target_source_club: Mapping[str, Any]) -> dict[str, Any]:
        old_club,old_selector,overlap_hashes,overlap_count,capacity=self._carrier_proof(carrier_id)
        target_selector=_selector(target_source_club.get("selector"),"target source")
        if target_selector["country_catalog"] != old_selector["country_catalog"]:
            raise SourceHashContinuityError("target source country differs from pinned old identity source")
        old_provider_id=_provider_id(old_selector["source_path"],"old preallocation")
        target_provider_id=_provider_id(target_selector["source_path"],"target source")
        if target_provider_id != old_provider_id:
            raise SourceHashContinuityError("target provider club ID differs from pinned old identity")
        expected_group=_carrier_group(carrier_id)
        if _country_group(target_selector["country_catalog"]) != expected_group:
            raise SourceHashContinuityError("target source country does not match fixed carrier country family")
        target_count=len(target_source_club.get("players") or [])
        if target_count < capacity:
            raise SourceHashContinuityError("target source roster is smaller than native fixed-carrier capacity")
        target_rows=[]
        for candidate in self.source_intake.get("source_clubs", []):
            if not isinstance(candidate,Mapping) or not isinstance(candidate.get("selector"),Mapping):
                raise SourceHashContinuityError("source intake contains malformed source-club row")
            if _selector(candidate["selector"],"source intake") == target_selector:
                target_rows.append(candidate)
        if len(target_rows)!=1:
            raise SourceHashContinuityError("target selector is not unique in the bound source intake")
        if len(target_rows[0].get("players") or []) != target_count:
            raise SourceHashContinuityError("target source player count disagrees with bound source intake row")
        intake_carriers=[row for row in self.source_intake.get("carriers",[]) if isinstance(row,Mapping) and row.get("carrier_id")==carrier_id]
        if len(intake_carriers)!=1:
            raise SourceHashContinuityError("source intake does not contain exactly one target carrier")
        assignment=intake_carriers[0].get("assignment")
        if not isinstance(assignment,Mapping) or assignment.get("status")=="unassigned":
            raise SourceHashContinuityError("source intake has no candidate assignment for this carrier")
        if _selector(assignment.get("source_selector"),"source intake assignment") != target_selector:
            raise SourceHashContinuityError("source intake assigns a different source club to this carrier")
        return {
            "schema_version":SCHEMA,
            "template_package_sha256":self.template_sha256,
            "old_preallocation_sha256":self.old_preallocation_sha256,
            "old_preallocation_artifact_id":self.old_preallocation_artifact_id,
            "carrier_id":carrier_id,
            "country_group":expected_group,
            "old_source_selector":dict(old_selector),
            "old_provider_club_id":old_provider_id,
            "target_source_capture_sha256":self.source_capture_sha256,
            "target_source_intake_sha256":self.source_intake_sha256,
            "target_source_selector":target_selector,
            "target_provider_club_id":target_provider_id,
            "overlap_source_row_sha256s":list(overlap_hashes),
            "overlap_count":overlap_count,
            "native_roster_capacity":capacity,
            "target_source_player_count":target_count,
        }


def derive_source_hash_continuity_evidence(
    *, template: Mapping[str, Any], original_template_sha256: str,
    old_preallocation: Mapping[str, Any], source_intake: Mapping[str, Any],
    registry: Mapping[str, Any], carrier_id: int,
    source_capture: Mapping[str, Any] | None = None,
    source_assignment: Mapping[str, Any] | None = None,
    target_source_club: Mapping[str, Any], context: SourceHashContinuityContext | None = None,
) -> dict[str, Any]:
    """Derive one reproducible proof; a builder may reuse its validated context."""
    ctx=context or SourceHashContinuityContext(template=template,
        original_template_sha256=original_template_sha256,old_preallocation=old_preallocation,
        source_intake=source_intake,registry=registry,
        source_capture=source_capture,source_assignment=source_assignment)
    if (ctx.template is not template or ctx.old_preallocation is not old_preallocation
            or ctx.source_intake is not source_intake or ctx.registry is not registry
            or ctx.template_sha256 != original_template_sha256):
        raise SourceHashContinuityError("continuity validation context does not match the current immutable inputs")
    return ctx.derive(carrier_id=carrier_id,target_source_club=target_source_club)


def validate_source_hash_continuity_allocation_row(
    *, method: str, row: Mapping[str, Any], template: Mapping[str, Any],
    original_template_sha256: str, old_preallocation: Mapping[str, Any] | None,
    source_intake: Mapping[str, Any], registry: Mapping[str, Any],
    source_capture: Mapping[str, Any] | None = None,
    source_assignment: Mapping[str, Any] | None = None,
    target_source_club: Mapping[str, Any], context: SourceHashContinuityContext | None = None,
) -> dict[str, Any]:
    """Fail closed unless the new method carries a reproducible exact proof."""
    if method != METHOD:
        raise SourceHashContinuityError("source-hash proof validator only accepts its dedicated continuation method")
    if old_preallocation is None:
        raise SourceHashContinuityError("new continuation method requires the template-pinned old preallocation input")
    evidence=row.get("source_identity_evidence")
    if not isinstance(evidence,Mapping):
        raise SourceHashContinuityError("new continuation method is missing source_identity_evidence")
    if row.get("source_identity_evidence_sha256") != document_sha256(evidence):
        raise SourceHashContinuityError("source identity evidence digest is missing or altered")
    if row.get("carrier_id") != evidence.get("carrier_id"):
        raise SourceHashContinuityError("source identity evidence names a different carrier")
    allocation_selector=row.get("source_selector")
    source_selector=target_source_club.get("selector")
    if not isinstance(allocation_selector,Mapping) or not isinstance(source_selector,Mapping):
        raise SourceHashContinuityError("allocation or source-intake selector is missing")
    for key in ("country_catalog","competition_catalog","source_path","source_sha256"):
        if allocation_selector.get(key) != source_selector.get(key):
            raise SourceHashContinuityError("allocation selector differs from exact source-intake selector")
    if row.get("club_name") != source_selector.get("club_name"):
        raise SourceHashContinuityError("allocation club name differs from exact source-intake selector")
    expected=derive_source_hash_continuity_evidence(
        template=template,original_template_sha256=original_template_sha256,
        old_preallocation=old_preallocation,source_intake=source_intake,
        registry=registry,carrier_id=int(row["carrier_id"]),
        source_capture=source_capture,source_assignment=source_assignment,
        target_source_club=target_source_club,
        context=context)
    if dict(evidence) != expected:
        raise SourceHashContinuityError("source identity evidence does not reproduce from pinned inputs")
    return expected
