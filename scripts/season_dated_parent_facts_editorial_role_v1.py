"""Reviewed typed admission: editorial role evidence on an already-adjudicated parent.

The existing first-fixture editorial factory guard remains unchanged. This
separate typed policy composes a verified official-fact layer with either an
exact annual-row/fixture identity proof or a separate target-year dated lineup
pair from the configured provider families. Role 9 is editorial for broad M;
it is not asserted as a historically published fine role.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
from scripts import season_adjudicated_player_facts_v1 as adjudicated
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as common
from scripts.season_editorial_factory_role_projection_v1 import FACTORY_JUG, distinct_factory_identity
from scripts.season_exact_fifa_role_delta_v1 import compatible
from scripts.season_historical_roster_audit_v1 import native_player, normalise
from scripts.season_source_package_builder_v1 import _source_person_id
from scripts.season_within_club_reserve_repair_v1 import native_facts
from scripts.season_opening_order_repair_v1 import native_owners

KIND = "dated-parent-facts-editorial-compatible-fine-role-projection-v3"
ARTIFACT_PREFIX = "season-dated-parent-facts-editorial-role-v3-"
_FACT_REPLAY_CACHE: set[tuple] = set()
INPUT_SCHEMA = common.INPUT_SCHEMA
SCHEMA = common.SCHEMA
PREFIX = common.PREFIX
EDITORIAL_ROLE_BY_BROAD = {"D": 4, "M": 9, "F": 12}
SCOPE = ("Only selected recipe fine_roles and the six exact native fine-role bytes. "
         "Source establishes identity, target-period membership and broad role; assigned fine role is editorial. "
         "Preserve DOB, country, names, broad role, ratings, EQ/ownership/orders, tactics, managers, assets and all other bytes.")


def _sha(path: Path) -> str:
    return registry.sha256_file(path)


def _path(relative: str) -> Path:
    path = registry.ROOT / relative
    if (Path(relative).is_absolute() or path.is_symlink()
            or not path.resolve().is_relative_to(registry.ROOT.resolve()) or not path.is_file()):
        raise ValueError("evidence path must be an existing retained workspace file")
    return path


def _binding(value: dict) -> Path:
    if not isinstance(value, dict) or set(value) not in ({"path", "sha256"}, {"path", "sha256", "url"}):
        raise ValueError("exact retained source path and SHA binding required")
    path = _path(value["path"])
    if _sha(path) != value["sha256"]:
        raise ValueError("retained source body changed")
    return path


def _read_json_binding(value: dict) -> tuple[Path, dict]:
    path = _binding(value)
    return path, pipeline.read_json_file(path)


def _one_source_row(preallocation: dict, row_hash: str):
    found = [(club, row) for club in preallocation["source_clubs"] for row in club["players"]
             if row.get("source_row_sha256") == row_hash]
    if len(found) != 1:
        raise ValueError("exactly one retained annual source row is required")
    return found[0]


def _source_dependency_fingerprints(value: object) -> tuple[tuple[str, str], ...]:
    """Rehash every nested path/SHA binding before using a warm replay cache."""
    found: dict[str, str] = {}
    def walk(node):
        if isinstance(node, dict):
            path, digest = node.get("path"), node.get("sha256")
            if isinstance(path, str) and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
                bound = _path(path)
                observed = _sha(bound)
                if observed != digest:
                    raise ValueError("a nested adjudicated-facts source binding changed")
                found[path] = digest
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(value)
    return tuple(sorted(found.items()))


def _lineup_date_tokens(iso_date: str) -> tuple[str, str]:
    from datetime import date
    parsed = date.fromisoformat(iso_date)
    return parsed.strftime("%d/%m/%Y"), parsed.strftime("%d-%m-%Y")


def _fold(value: str) -> str:
    import unicodedata
    return " ".join(unicodedata.normalize("NFKD", value).casefold().split())


def _label_tokens_in_name(full_name: str, label: str) -> bool:
    full, short = _fold(full_name).split(), _fold(label).split()
    return bool(short) and any(full[index:index + len(short)] == short for index in range(len(full)))


def _verify_dated_lineup_pair(request: dict, annual_row: dict, annual_club: dict,
                              expected_provider_id: int, target_season: str) -> dict:
    evidence = request.get("dated_lineup_evidence")
    expected_keys = {"date", "season", "club_name", "provider_club_id", "selector_source_path",
                     "selector_source_sha256", "club_source_label", "opponent_name", "opponent_source_label", "player_full_name",
                     "provider_player_id", "shirt_number", "lineup_label", "side",
                     "home_score", "away_score", "folha", "globo"}
    if not isinstance(evidence, dict) or set(evidence) != expected_keys:
        raise ValueError("complete typed dated-lineup pair required")
    from datetime import date
    try:
        parsed_date = date.fromisoformat(evidence["date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("dated-lineup evidence requires an exact ISO calendar date") from exc
    selector = annual_club.get("selector", {})
    facts = annual_row.get("facts", {})
    selector_club = selector.get("club_name")
    club_source_label = evidence.get("club_source_label")
    opponent_source_label = evidence.get("opponent_source_label")
    selector_source = selector.get("source_path")
    selector_sha = selector.get("source_sha256")
    row_player_id = annual_row.get("opening_source_player_id")
    full_name = facts.get("name")
    label = evidence.get("lineup_label")
    if not date(int(target_season[:4]), 8, 1) <= parsed_date <= date(int(target_season[:4]), 12, 31):
        raise ValueError("dated lineup outside target-season date window (August through December of start year)")
    if (evidence["season"] != target_season or parsed_date.year != int(target_season[:4])
            or evidence["club_name"] != selector_club
            or not isinstance(club_source_label, str) or not club_source_label
            or _fold(selector_club).split()[:len(_fold(club_source_label).split())] != _fold(club_source_label).split()
            or not isinstance(opponent_source_label, str) or not opponent_source_label
            or _fold(opponent_source_label) == _fold(club_source_label)
            or evidence["selector_source_path"] != selector_source
            or evidence["selector_source_sha256"] != selector_sha
            or evidence["provider_player_id"] != int(expected_provider_id)
            or (row_player_id is not None and str(row_player_id) != str(expected_provider_id))
            or evidence["player_full_name"] != full_name
            or not isinstance(label, str) or not label or label.casefold() not in full_name.casefold().split()
            or type(evidence["provider_club_id"]) is not int
            or type(evidence["shirt_number"]) is not int
            or type(evidence["home_score"]) is not int or type(evidence["away_score"]) is not int
            or evidence["home_score"] < 0 or evidence["away_score"] < 0
            or facts.get("shirt_number") != evidence["shirt_number"]
            or facts.get("position") != "M"
            or evidence["side"] != "home"
            or not isinstance(evidence["opponent_name"], str) or not evidence["opponent_name"]
            or not isinstance(opponent_source_label, str) or not opponent_source_label
            or not _label_tokens_in_name(evidence["opponent_name"], opponent_source_label)
            or _fold(evidence["opponent_name"]) == _fold(evidence["club_name"])):
        raise ValueError("dated lineup request differs from the exact annual source identity/club/year")
    fact_plan_binding = request.get("adjudicated_facts_plan")
    if not isinstance(fact_plan_binding, dict):
        raise ValueError("adjudicated parent fact plan binding required")
    _, fact_plan = _read_json_binding(fact_plan_binding)
    selection = request["changes"][0]
    fact_update = next((u for u in fact_plan.get("updates", [])
                        if u.get("carrier_id") == selection["carrier_id"]), None)
    if fact_update is None:
        raise ValueError("dated lineup carrier absent from adjudicated facts plan")
    witness = fact_update.get("witness", {})
    hist = witness.get("historical_identity", {})
    hist_match = hist.get("match", {})
    hist_fixture = witness.get("historical_fixture", {})
    witnessed_club_id = hist_match.get("provider_club_id", hist_fixture.get("provider_club_id"))
    if witnessed_club_id is None or int(witnessed_club_id) != evidence["provider_club_id"]:
        raise ValueError("requested provider club ID differs from the identity-witnessed club")

    folha_path = _binding(evidence["folha"])
    ge_path = _binding(evidence["globo"])
    folha_url = urlsplit(evidence["folha"].get("url", ""))
    ge_url = urlsplit(evidence["globo"].get("url", ""))
    date_slash, date_dash = _lineup_date_tokens(evidence["date"])
    if (folha_url.scheme != "https" or folha_url.hostname != "aovivo.folha.uol.com.br"
            or not re.search(rf"/{re.escape(parsed_date.strftime('%Y'))}/{parsed_date.strftime('%m')}/{parsed_date.strftime('%d')}/", folha_url.path)
            or ge_url.scheme != "https" or ge_url.hostname != "ge.globo.com"
            or not ge_url.path.startswith("/jogo/") or date_dash not in ge_url.path):
        raise ValueError("dated lineup source family/URL date binding differs")
    folha = BeautifulSoup(folha_path.read_bytes(), "lxml")
    title = " ".join((folha.title.get_text(" ", strip=True) if folha.title else "").split())
    text = " ".join(folha.get_text(" ", strip=True).split())
    title_fold, text_fold = _fold(title), _fold(text)
    club_fold, opponent_fold = _fold(club_source_label), _fold(opponent_source_label)
    if (date_slash not in text or club_fold not in title_fold or opponent_fold not in title_fold
            or f"{club_fold} x {opponent_fold}" not in title_fold
            or f"{club_fold} {evidence['home_score']} x {evidence['away_score']} {opponent_fold}" not in text_fold):
        raise ValueError("Folha match title/date/score does not bind the requested home club and opponent")
    text_raw = " ".join(folha.get_text(" ", strip=True).split())
    club_escaped = re.escape(club_source_label)
    opponent_escaped = re.escape(opponent_source_label)
    sections = re.findall(club_escaped + r" Técnico:\s*.*?(.*?)" + opponent_escaped + r" Técnico:", text_raw, re.I)
    line = re.compile(rf"(?<!\d){evidence['shirt_number']}\.\s*{re.escape(label)}(?!\w)", re.I)
    if len(sections) != 1 or len(line.findall(sections[0])) != 1:
        raise ValueError("Folha lineup label/shirt is not unique inside the requested club's own lineup section")
    ge = BeautifulSoup(ge_path.read_bytes(), "lxml")
    ge_title = _fold(ge.title.get_text(" ", strip=True) if ge.title else "")
    ge_text = " ".join(ge.get_text(" ", strip=True).split())
    if (date_slash not in ge_text or club_fold not in ge_title or opponent_fold not in ge_title
            or _fold(label) not in _fold(ge_text)):
        raise ValueError("Globo body does not bind the requested date, fixture sides and player label")
    midfield_paragraphs = [p.get_text(" ", strip=True) for p in ge.find_all("p")
                           if _fold(label) in _fold(p.get_text(" ", strip=True))
                           and re.search(r"meio[- ]campo", _fold(p.get_text(" ", strip=True)))]
    if not midfield_paragraphs:
        raise ValueError("Globo page must contain a player-bound midfield description")
    return {
        "date": evidence["date"], "club_name": evidence["club_name"],
        "provider_club_id": evidence["provider_club_id"], "club_source_label": club_source_label,
        "opponent_name": evidence["opponent_name"], "opponent_source_label": opponent_source_label,
        "provider_player_id": expected_provider_id, "shirt_number": evidence["shirt_number"],
        "annual_source_row_sha256": annual_row["source_row_sha256"],
        "folha_sha256": evidence["folha"]["sha256"], "globo_sha256": evidence["globo"]["sha256"],
        "published_broad_role": "M", "assigned_fine_role": 9,
        "fine_role_status": "editorial-compatible-default-not-published-source-fact",
    }



def _verification_code_fingerprints() -> tuple[tuple[str, str], ...]:
    import importlib
    module_names = (
        "scripts.season_source_verified_player_changes_v1",
        "scripts.season_adjudicated_player_facts_v1",
        "scripts.season_annual_row_identity_guard_v1",
        "scripts.season_official_career_context_v1",
        "scripts.season_annual_fixture_identity_bridge_v1",
        "scripts.season_opening_identity_exchange_v1",
        "scripts.season_source_package_builder_v1",
        "scripts.season_opening_order_repair_v1",
        "scripts.season_within_club_reserve_repair_v1",
        "scripts.season_historical_roster_audit_v1",
        "scripts.capture_2015_source_tail_squads_v1",
        "scripts.season_exact_fifa_role_delta_v1",
        "scripts.season_editorial_factory_role_projection_v1",
        "scripts.season_package_v2",
        "scripts.season_package_compiler_v2",
        "scripts.season_pipeline_v2",
        "scripts.season_quality_only_delta_v1",
        "scripts.season_soccerbase_secondary_facts_v2",
        "scripts.season_frozen_fixture_reserve_v2",
        "scripts.season_release_registry_v1",
        "app.fdi_indexed",
        "app.editor_actions",
        "app.models",
        "app.xor",
        "app.indexed_jug_identity",
        "app.indexed_jug_roles",
    )
    modules = [(name, _sha(Path(importlib.import_module(name).__file__))) for name in module_names]
    modules.append(("candidate", _sha(Path(__file__))))
    return tuple(sorted(modules))


def _replay_dependency_key(fact_plan: dict) -> tuple:
    # Always invoked before cache membership is checked, so cached success is
    # invalidated by any changed bound body or verification/parser source file.
    return (_source_dependency_fingerprints(fact_plan), _verification_code_fingerprints())


def _verify_fact_parent(base, request: dict):
    locator_path = registry.locator_path(base.season, base.release_id)
    locator = pipeline.read_json_file(locator_path)
    expected_binding = request.get("adjudicated_facts_plan")
    if not isinstance(expected_binding, dict) or locator.get("sourced_profile_assignment_plan_path") != expected_binding.get("path"):
        raise ValueError("exact current parent source-fact plan locator required")
    fact_plan_path, fact_plan = _read_json_binding(expected_binding)
    fact_base = registry.load_registered_release(fact_plan["season"], fact_plan["release_id"])
    # Rehash all dependencies on every call before consulting the cache. The cache
    # stores only a successful equality assertion, never mutable package/plan data.
    current_jug_path = base.game_path / "DBDAT/JUG98030.FDI"
    current_eq_path = base.game_path / "DBDAT/EQ98030.FDI"
    fact_jug_path = fact_base.game_path / "DBDAT/JUG98030.FDI"
    fact_eq_path = fact_base.game_path / "DBDAT/EQ98030.FDI"
    replay_dependency_key = _replay_dependency_key(fact_plan)
    key = (
        base.season, base.release_id, _sha(base.package_path), _sha(base.release_manifest_path),
        _sha(current_jug_path), _sha(current_eq_path), _sha(fact_plan_path),
        _sha(fact_base.package_path), _sha(fact_base.release_manifest_path),
        _sha(fact_jug_path), _sha(fact_eq_path), _sha(Path(__file__)),
        _sha(Path(common.__file__)), _sha(Path(adjudicated.__file__)),
        _sha(Path(packages.__file__)), replay_dependency_key,
    )
    if key not in _FACT_REPLAY_CACHE:
        common.verify(fact_base, fact_plan)
        expected_package = common.bind(pipeline.read_json_file(fact_base.package_path), fact_plan)
        current_package = pipeline.read_json_file(base.package_path)
        expected_jug, expected_eq = common.apply(fact_jug_path.read_bytes(), fact_eq_path.read_bytes(), fact_plan)
        current_jug, current_eq = current_jug_path.read_bytes(), current_eq_path.read_bytes()
        if expected_package != current_package or expected_jug != current_jug or expected_eq != current_eq:
            raise ValueError("current parent is not the exact approved adjudicated-facts layer postimage")
        _FACT_REPLAY_CACHE.add(key)
    return (fact_plan_path, fact_plan, fact_base, pipeline.read_json_file(base.package_path),
            current_jug_path.read_bytes(), current_eq_path.read_bytes())


def _fact_witness(fact_plan: dict, carrier: int):
    rows = [r for r in fact_plan.get("updates", []) if r.get("carrier_id") == carrier]
    if len(rows) != 1:
        raise ValueError("fact plan must contain one exact target identity update")
    update = rows[0]
    witness = update.get("witness")
    if not isinstance(witness, dict) or witness.get("person_id") != update["before"].get("person_id"):
        raise ValueError("official fact layer must retain exact source person identity")
    expected_pid = (witness.get("fixture_provider_player_id")
                    or witness.get("historical_identity", {}).get("provider_player_id")
                    or witness.get("historical_fixture", {}).get("provider_player_id"))
    if witness.get("identity_policy") == "annual-source-row-person-identity-null-dob-v1":
        # The exact registered facts parent has already been independently replayed
        # through common.verify/bind/apply. The annual-row policy intentionally has
        # no provider numeric ID; its stable identity is the exact row hash/person ID.
        if expected_pid is not None or witness.get("historical_fixture") is not None:
            raise ValueError("null-annual-DOB identity branch must not invent a provider player ID")
    elif not expected_pid or adjudicated.verify_historical_identity(witness) != int(expected_pid):
        raise ValueError("approved fact witness failed its original identity/fixture replay")
    return update, witness


def _official_annual_role_context(witness: dict, annual_row: dict, annual_club: dict,
                                  actor: dict, fact_update: dict, row_sha: str,
                                  target_season: str) -> dict:
    """Bind broad role to the exact annual row admitted by the verified facts parent."""
    if witness.get("identity_policy") != "annual-source-row-person-identity-null-dob-v1":
        raise ValueError("explicit null-annual-DOB identity policy required")
    annual = witness.get("annual_identity")
    contexts = witness.get("official_career_contexts")
    selector = annual_club.get("selector", {})
    if (not isinstance(annual, dict) or annual.get("source_row_sha256") != row_sha
            or annual.get("source_row_index") != annual_row.get("source_row_index")
            or annual.get("season") != target_season
            or annual.get("club_id") != actor.get("club_id")
            or not isinstance(annual.get("selector"), dict)
            or any(annual["selector"].get(key) != selector.get(key)
                   for key in ("club_name", "country_catalog", "competition_catalog", "source_path", "source_sha256"))
            or annual_row.get("facts", {}).get("birth_date") is not None
            or annual_row.get("facts", {}).get("name") != witness.get("full_name")
            or annual_row.get("facts", {}).get("position") != "D"
            or witness.get("full_name") != actor.get("source_name")
            or witness.get("person_id") != actor.get("person_id")
            or not isinstance(contexts, list) or not contexts):
        raise ValueError("official-career role branch lacks exact null-DOB annual person and context bindings")
    for context in contexts:
        url_value = context.get("url") if isinstance(context, dict) else None
        url = urlsplit(url_value) if isinstance(url_value, str) else None
        if (not isinstance(context, dict) or not isinstance(context.get("body"), dict)
                or not isinstance(context.get("receipt"), dict)
                or not re.fullmatch(r"[0-9a-f]{64}", str(context.get("sha256", "")))
                or url is None or url.scheme != "https" or url.hostname != "www.uefa.com"):
            raise ValueError("official-career context must bind a retained official UEFA body and receipt")
    if fact_update.get("values", {}).get("birth_date") != actor.get("facts", {}).get("birth_date"):
        raise ValueError("corrected parent DOB differs from the independently admitted facts layer")
    # These contexts are accepted only because _verify_fact_parent replayed the
    # registered source-facts plan. Their exact nested body/receipt bindings are
    # rehashed before the replay cache is consulted.
    return {
        "identity_policy": witness["identity_policy"],
        "source_row_sha256": row_sha,
        "source_row_index": annual_row["source_row_index"],
        "full_name": witness["full_name"],
        "source_birth_date": None,
        "corrected_parent_birth_date": fact_update["values"]["birth_date"],
        "published_broad_role": "D",
        "official_career_contexts": copy.deepcopy(contexts),
        "fine_role_status": "editorial-compatible-default-not-published-source-fact",
    }


def _factory_roles(carrier: int):
    factory = FACTORY_JUG.read_bytes()
    entry = next((e for e in IndexedFDIFile.from_bytes(factory).entries if e.record_id == carrier), None)
    if entry is None:
        raise ValueError("factory role identity is absent")
    payload = entry.decode_payload(factory)
    end, roles = read_indexed_native_roles(payload, carrier)
    return factory, entry, payload, end, roles, native_player(payload, carrier), native_facts(factory, carrier)


def _exclusive_owner(eq: bytes, carrier: int, expected_owner: int) -> bool:
    return native_owners(eq).get(carrier) == {expected_owner}


def _factory_role_seed_guard_ok(factory_name: str, actor_source_name: str,
                                factory_broad: str, target_broad: str,
                                factory_roles: list[int], null_annual_identity: bool) -> bool:
    """Keep legacy M checks; permit the verified D path's incompatible seed."""
    if (not distinct_factory_identity(factory_name, actor_source_name)
            or factory_broad == target_broad or not factory_roles):
        return False
    official_null_d_seed = null_annual_identity and target_broad == "D"
    return official_null_d_seed or compatible(factory_broad, factory_roles[0])


def _assert_role_byte_mask(before: bytes, after: bytes, masks: list[dict]) -> None:
    allowed = {m["file_offset"] for m in masks if m["before"] != m["after"]}
    actual = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    if len(before) != len(after) or actual != allowed:
        raise ValueError("native role writer changed bytes outside the exact six-role field mask")


def prepare(base, request_path: Path):
    request_path = Path(request_path)
    request_rel = registry.relative_workspace_path(request_path)
    request_path = _path(request_rel)
    request = pipeline.read_json_file(request_path)
    if (request.get("schema") != INPUT_SCHEMA or request.get("kind") != KIND
            or request.get("season") != base.season or request.get("release_id") != base.release_id
            or len(request.get("changes", [])) != 1):
        raise ValueError("one explicit target on an exact registered corrected-facts parent required")
    parent_bindings = request.get("parent")
    if not isinstance(parent_bindings, dict) or parent_bindings != {
        "package_sha256": _sha(base.package_path),
        "manifest_sha256": _sha(base.release_manifest_path),
        "jug_sha256": _sha(base.game_path / "DBDAT/JUG98030.FDI"),
        "eq_sha256": _sha(base.game_path / "DBDAT/EQ98030.FDI"),
    }:
        raise ValueError("exact registered parent package and native bindings required")
    fact_path, fact_plan, fact_base, package, jug, eq = _verify_fact_parent(base, request)
    source_dependency_fingerprints, _code_fingerprints = _replay_dependency_key(fact_plan)
    selection = request["changes"][0]
    carrier = selection.get("carrier_id")
    if type(carrier) is not int or selection.get("field_mask") != ["fine_roles"]:
        raise ValueError("only one explicit fine_roles field mask is admitted")
    actor = next((p for p in package["players"] if p.get("carrier_id") == carrier), None)
    if actor is None:
        raise ValueError("selected source-backed actor missing")
    fact_update, witness = _fact_witness(fact_plan, carrier)
    before_actor = fact_update["before"]
    if (actor.get("carrier_id") != before_actor.get("carrier_id")
            or actor.get("id") != before_actor.get("id")
            or actor.get("person_id") != before_actor.get("person_id")
            or actor.get("source_name") != before_actor.get("source_name")
            or any(actor.get("facts", {}).get(k) != value for k, value in fact_update["values"].items())):
        raise ValueError("selected actor does not retain the corrected-facts identity and values")
    annual = witness.get("annual_identity")
    hist = witness.get("historical_identity")
    row_sha = (annual or {}).get("source_row_sha256") or (hist or {}).get("source_row_sha256")
    preallocation_binding = (annual or {}).get("preallocation") or (hist or {}).get("preallocation")
    if not isinstance(row_sha, str) or not isinstance(preallocation_binding, dict):
        raise ValueError("official fact layer must bind an original annual source row")
    allocation_path, allocation = _read_json_binding(preallocation_binding)
    annual_club, annual_row = _one_source_row(allocation, row_sha)
    expected_provider_id = (witness.get("fixture_provider_player_id")
                            or (hist or {}).get("provider_player_id")
                            or (witness.get("historical_fixture") or {}).get("provider_player_id"))
    null_annual_identity = witness.get("identity_policy") == "annual-source-row-person-identity-null-dob-v1"
    row_provider_id = annual_row.get("opening_source_player_id") or expected_provider_id
    common_identity_ok = (_source_person_id(annual_row) == actor.get("person_id")
            and annual_row.get("facts", {}).get("name") == actor.get("source_name")
            and annual_row.get("facts", {}).get("position") == actor["facts"].get("primary_position")
            and actor["facts"].get("birth_date") == fact_update["values"].get("birth_date")
            and actor["facts"].get("fine_roles") == {"policy": "preserve-existing-mode1"})
    # Keep the standard-provider path byte-for-byte in its prior semantic shape;
    # the null-DOB path substitutes only exact annual-row identity and no fake ID.
    if (not common_identity_ok or
            (null_annual_identity and (expected_provider_id is not None or row_provider_id is not None)) or
            (not null_annual_identity and (not expected_provider_id or str(row_provider_id) != str(expected_provider_id)))):
        raise ValueError("corrected source identity, annual broad role or preserved-role preimage differs")
    if selection.get("source_row_sha256") != row_sha:
        raise ValueError("request annual source row hash differs from adjudicated identity proof")
    if null_annual_identity:
        if selection.get("evidence_policy") != "official-career-null-annual-dob-with-corrected-parent-facts-v1":
            raise ValueError("explicit official-career null-annual-DOB role policy required")
        parsed_dated = _official_annual_role_context(witness, annual_row, annual_club, actor,
                                                     fact_update, row_sha, base.season)
        role_broad = "D"
    elif selection.get("evidence_policy") == "dated-lineup-with-adjudicated-parent-facts-v1":
        parsed_dated = _verify_dated_lineup_pair(request, annual_row, annual_club, int(expected_provider_id), base.season)
        role_broad = "M"
    else:
        if selection.get("evidence_policy") != "annual-fixture-role-with-corrected-parent-facts-v1":
            raise ValueError("exact annual-fixture corrected-parent role policy required")
        fixture = witness.get("historical_fixture")
        if (not isinstance(fixture, dict) or fixture.get("date", "")[:4] != base.season[:4]
                or fixture.get("provider_player_id") != int(expected_provider_id)
                or (annual_row.get("opening_source_player_id") is not None
                    and int(annual_row["opening_source_player_id"]) != int(expected_provider_id))
                or annual_row.get("facts", {}).get("position") != "M"):
            raise ValueError("annual fixture must bind the target-year provider identity and source broad role M")
        parsed_dated = {
            "date": fixture["date"], "club_id": fixture["provider_club_id"],
            "match_id": fixture["match_id"], "provider_player_id": fixture["provider_player_id"],
            "source_row_sha256": row_sha, "published_broad_role": "M",
            "source_birth_date": annual_row.get("facts", {}).get("birth_date"),
            "corrected_parent_birth_date": fact_update["values"].get("birth_date"),
            "fine_role_status": "editorial-compatible-default-not-published-source-fact",
        }
        role_broad = "M"
    club = next(c for c in package["clubs"] if c["id"] == actor["club_id"])
    entry = next((e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id == carrier), None)
    if entry is None or not _exclusive_owner(eq, carrier, club["carrier_id"]):
        raise ValueError("selected actor needs one current native record and exclusive owner")
    payload = entry.decode_payload(jug)
    end, before_roles = read_indexed_native_roles(payload, carrier)
    observed = native_player(payload, carrier)
    observed_facts = native_facts(jug, carrier)
    factory, factory_entry, factory_payload, factory_end, factory_roles, factory_native, factory_facts = _factory_roles(carrier)
    if (observed["position"] != role_broad or observed_facts["position"] != role_broad
            or before_roles != factory_roles
            or not _factory_role_seed_guard_ok(
                factory_native["name"], actor["source_name"], factory_facts["position"],
                role_broad, factory_roles, null_annual_identity)
            or observed_facts["birth_date"] == factory_facts["birth_date"]
            or observed_facts["birth_date"] != actor["facts"]["birth_date"]
            or observed["name"].casefold() != actor["name"].casefold()):
        raise ValueError("native identity, current role/factory preimage or broad-role guard differs")
    role = EDITORIAL_ROLE_BY_BROAD[role_broad]
    if not compatible(role_broad, role) or compatible(role_broad, before_roles[0]):
        raise ValueError("target broad-role default must be compatible and correct an incompatible source-byte primary role")
    postjug, masks = rewrite_indexed_native_roles(jug, {carrier: [role]})
    post_entry = next(e for e in IndexedFDIFile.from_bytes(postjug).entries if e.record_id == carrier)
    post_end, post_roles = read_indexed_native_roles(post_entry.decode_payload(postjug), carrier)
    if post_end != end or post_roles != [role, 98, 98, 98, 98, 98]:
        raise ValueError("native fine-role readback differs from the intended editorial projection")
    role_masks = []
    for index in range(6):
        offset = end + 2 + index
        absolute = entry.payload_offset + offset
        after_value = postjug[absolute]
        if jug[absolute] != payload[offset] ^ 0x61:
            raise ValueError("role byte physical boundary does not match decoded native payload")
        role_masks.append({"file": "DBDAT/JUG98030.FDI", "record_offset": offset,
            "file_offset": absolute, "before": jug[absolute], "after": after_value})
    _assert_role_byte_mask(jug, postjug, role_masks)
    update = {
        "carrier_id": carrier, "before": copy.deepcopy(actor), "values": {"fine_roles": [role]},
        "field_mask": ["fine_roles"], "native_masks": role_masks,
        "expected_owner": club["carrier_id"], "before_native_roles": before_roles,
        "after_native_roles": post_roles,
        "evidence": {"adjudicated_facts_plan": {"path": registry.relative_workspace_path(fact_path), "sha256": _sha(fact_path)},
            "annual_source_row_sha256": row_sha, "person_id": actor["person_id"],
            "provider_player_id": int(expected_provider_id) if expected_provider_id is not None else None,
            "dated_role_evidence": parsed_dated,
            "factory": {"sha256": hashlib.sha256(factory).hexdigest(), "identity": factory_native["name"],
                "broad": factory_facts["position"], "fine_roles": factory_roles, "role_end": factory_end},
            "native_preimage": {"name": observed["name"], "birth_date": observed_facts["birth_date"],
                "broad": observed_facts["position"], "fine_roles": before_roles}},
    }
    plan = {
        "schema": SCHEMA, "kind": KIND, "season": base.season, "release_id": base.release_id,
        "source_input": common.binding(request_path), "package_sha256": parent_bindings["package_sha256"],
        "jug_sha256": parent_bindings["jug_sha256"], "eq_sha256": parent_bindings["eq_sha256"],
        "updates": [update], "scope": SCOPE,
        "source_policy": "approved-parent-facts-plus-exact-dated-role-evidence-editorial-fine-role-v1",
        # Code fingerprints guard the in-process cache, not persistent semantic
        # plans. Unrelated implementation updates must not change SOURCE IDs.
        "fact_replay_dependencies": {
            "source_bindings": [list(item) for item in source_dependency_fingerprints],
        },
    }
    plan["transaction_id"] = common.digest(packages.canonical_json_bytes(plan))[:24]
    validate_mask(plan)
    return plan


def validate_mask(plan):
    rows = plan.get("updates", [])
    row = rows[0] if len(rows) == 1 and isinstance(rows[0], dict) else {}
    role_broad = row.get("evidence", {}).get("dated_role_evidence", {}).get("published_broad_role")
    role = EDITORIAL_ROLE_BY_BROAD.get(role_broad)
    if (plan.get("schema") != SCHEMA or plan.get("kind") != KIND or len(rows) != 1
            or not isinstance(row.get("carrier_id"), int) or row.get("field_mask") != ["fine_roles"]
            or role is None or row.get("values") != {"fine_roles": [role]}
            or len(row.get("native_masks", [])) != 6):
        raise ValueError("exact one-player editorial fine-role-only plan required")
    update = row
    masks = update["native_masks"]
    before_roles = update.get("before_native_roles")
    after_roles = update.get("after_native_roles")
    if (not isinstance(before_roles, list) or len(before_roles) != 6
            or not isinstance(after_roles, list) or after_roles != [role, 98, 98, 98, 98, 98]
            or [m.get("record_offset") for m in masks] != list(range(masks[0]["record_offset"], masks[0]["record_offset"] + 6))
            or [m.get("file_offset") for m in masks] != list(range(masks[0]["file_offset"], masks[0]["file_offset"] + 6))
            or any(m.get("file") != "DBDAT/JUG98030.FDI" for m in masks)):
        raise ValueError("six role masks do not describe the exact old-to-editorial role vector")
    offsets = set()
    for mask in masks:
        if (set(mask) != {"file", "record_offset", "file_offset", "before", "after"}
                or type(mask["record_offset"]) is not int or type(mask["file_offset"]) is not int
                or mask["record_offset"] < 0 or mask["file_offset"] < mask["record_offset"]
                or not 0 <= mask["before"] <= 255 or not 0 <= mask["after"] <= 255
                or mask["file_offset"] in offsets):
            raise ValueError("exact nonoverlapping role-byte masks required")
        offsets.add(mask["file_offset"])
    if (not compatible(role_broad, role) or compatible(role_broad, before_roles[0])
            or update.get("expected_owner") is None):
        raise ValueError("broad-role compatibility, changed inherited role and exact owner required")


def filename(plan):
    return "editorial-dated-parent-facts-roles-" + plan["transaction_id"] + ".json"


def verify(base, plan):
    validate_mask(plan)
    path = _path(plan["source_input"]["path"])
    if _sha(path) != plan["source_input"]["sha256"] or prepare(base, path) != plan:
        raise ValueError("dated parent-facts role plan does not independently reproduce")


def bind(package, plan):
    validate_mask(plan)
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    if pipeline.read_json_file(base.package_path) != package or _sha(base.package_path) != plan["package_sha256"]:
        raise ValueError("exact corrected-facts package preimage required")
    result = copy.deepcopy(package)
    actor = next(p for p in result["players"] if p["carrier_id"] == plan["updates"][0]["carrier_id"])
    if actor != plan["updates"][0]["before"]:
        raise ValueError("selected recipe actor preimage changed")
    actor["facts"]["fine_roles"] = list(plan["updates"][0]["values"]["fine_roles"])
    if "fact_fallbacks" in actor:
        actor["fact_fallbacks"] = [item for item in actor["fact_fallbacks"] if item["field"] != "fine_roles"]
    aid = PREFIX + plan["transaction_id"]
    result["artifacts"].append({"id": aid, "kind": "season-input", "relative_path": filename(plan),
        "sha256": common.digest(packages.canonical_json_bytes(plan)), "media_type": "application/json"})
    result["proofs"].append({"id": "proof-" + aid, "grade": "reviewed-editorial", "artifact_id": aid,
        "covers": ["corrected-parent-identity", "dated-target-season-broad-role", "editorial-fine-role-not-published-fact"]})
    for key in ("artifacts", "proofs"):
        result[key].sort(key=lambda row: row["id"])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    validate_mask(plan)
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    original = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    if _sha(base.game_path / "DBDAT/JUG98030.FDI") != plan["jug_sha256"] or _sha(base.game_path / "DBDAT/EQ98030.FDI") != plan["eq_sha256"] or eq != (base.game_path / "DBDAT/EQ98030.FDI").read_bytes():
        raise ValueError("exact corrected-facts native preimage required")
    target = plan["updates"][0]["carrier_id"]
    after, _ = rewrite_indexed_native_roles(original, {target: plan["updates"][0]["values"]["fine_roles"]})
    changed = {i for i, (old, new) in enumerate(zip(original, after)) if old != new}
    expected = {m["file_offset"] for m in plan["updates"][0]["native_masks"] if m["before"] != m["after"]}
    if len(original) != len(after) or changed != expected or jug not in (original, after):
        raise ValueError("role-only apply accepts exact pre/post image and exact changed role bytes")
    for mask in plan["updates"][0]["native_masks"]:
        if original[mask["file_offset"]] != mask["before"] or after[mask["file_offset"]] != mask["after"]:
            raise ValueError("role native mask pre/post mismatch")
    return after, eq


def reject_factory_recipe(package):
    if any(a.get("id", "").startswith(PREFIX) for a in package.get("artifacts", [])):
        raise ValueError("source-backed field recipe requires exact SOURCE reconstruction")
