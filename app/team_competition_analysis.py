from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

SECONDARY_SIGNATURE_OFFSETS = (8, 10)
TERTIARY_CANDIDATE_OFFSETS = tuple(rel for rel in range(1, 12) if rel not in SECONDARY_SIGNATURE_OFFSETS)
FAMILY_METADATA_SCAN_OFFSETS = tuple(range(1, 24))
COUNTRY_SUBGROUP_SCAN_OFFSETS = tuple(range(1, 48))


@dataclass
class CompetitionCodeCluster:
    code: int
    team_count: int
    competition_count: int
    country_count: int
    dominant_country: str
    dominant_country_count: int
    dominant_competition: str
    dominant_competition_count: int
    inferred_kind: str
    sample_competitions: list[str] = field(default_factory=list)
    secondary_signature_count: int = 0
    secondary_strong_competition_count: int = 0
    secondary_average_competition_purity: float = 0.0
    secondary_inferred_kind: str = "unresolved"
    sample_secondary_signatures: list[str] = field(default_factory=list)
    tertiary_offset: int | None = None
    tertiary_signature_count: int = 0
    tertiary_strong_competition_count: int = 0
    tertiary_average_competition_purity: float = 0.0
    tertiary_inferred_kind: str = "unresolved"
    sample_tertiary_signatures: list[str] = field(default_factory=list)
    family_metadata_offset: int | None = None
    family_metadata_non_text_ratio: float = 0.0
    family_metadata_distinct_dominants: int = 0
    family_metadata_average_competition_purity: float = 0.0
    family_metadata_strong_competition_count: int = 0
    family_metadata_inferred_kind: str = "unresolved"
    sample_family_metadata_values: list[str] = field(default_factory=list)
    dominant_country_subgroup_offset: int | None = None
    dominant_country_subgroup_non_text_ratio: float = 0.0
    dominant_country_subgroup_average_competition_purity: float = 0.0
    dominant_country_subgroup_strong_competition_count: int = 0
    dominant_country_subgroup_distinct_dominants: int = 0
    dominant_country_subgroup_inferred_kind: str = "unresolved"
    sample_dominant_country_subgroup_values: list[str] = field(default_factory=list)


@dataclass
class CompetitionCodebookSummary:
    assigned_team_count: int
    clusters: list[CompetitionCodeCluster] = field(default_factory=list)
    cluster_by_code: dict[int, CompetitionCodeCluster] = field(default_factory=dict)


@dataclass
class LeagueAssignmentProbe:
    primary_code: int
    method: str
    signal_name: str
    signal_offset: int | None
    signal_value_display: str
    candidate_competition: str
    candidate_country: str
    candidate_league: str
    purity: float
    support_count: int
    total_count: int
    confidence: str
    assigned_competition: str
    matches_assigned_competition: bool


@dataclass
class LeagueAssignmentResolution:
    source: str
    country: str
    league: str
    confidence: str
    status: str
    promoted: bool = False
    promoted_from_source: str = ""
    promoted_method: str = ""
    promoted_probe_confidence: str = ""


PROMOTABLE_LEAGUE_PROBE_METHODS = {
    "secondary_signature",
    "tertiary_signature",
    "family_metadata_byte",
    "dominant_country_subgroup_byte",
}


def _team_competition_code(team: Any) -> int | None:
    candidate = getattr(team, "competition_code_candidate", None)
    if candidate is None and hasattr(team, "get_competition_code_candidate"):
        try:
            candidate = team.get_competition_code_candidate()
        except Exception:
            candidate = None
    if candidate is None:
        return None
    try:
        return int(candidate)
    except Exception:
        return None


def _team_competition_probe_byte(team: Any, relative_offset: int) -> int | None:
    try:
        rel = max(0, int(relative_offset))
    except Exception:
        return None
    if hasattr(team, "get_competition_probe_byte"):
        try:
            return team.get_competition_probe_byte(rel)
        except Exception:
            pass
    if hasattr(team, "get_competition_probe_bytes"):
        try:
            probe = bytes(team.get_competition_probe_bytes(rel + 1))
        except Exception:
            probe = b""
        if rel < len(probe):
            return int(probe[rel])
    raw = bytes(getattr(team, "raw_data", b"") or b"")
    if not raw:
        return None
    anchor = 0
    if hasattr(team, "get_known_text_anchor"):
        try:
            anchor = int(team.get_known_text_anchor())
        except Exception:
            anchor = 0
    index = anchor + rel
    if 0 <= index < len(raw):
        return int(raw[index])
    return None


def _team_probe_signature(
    team: Any,
    offsets: tuple[int, ...],
) -> tuple[int, ...] | None:
    values: list[int] = []
    for rel in offsets:
        value = _team_competition_probe_byte(team, rel)
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _team_secondary_signature(
    team: Any,
    offsets: tuple[int, ...] = SECONDARY_SIGNATURE_OFFSETS,
) -> tuple[int, ...] | None:
    return _team_probe_signature(team, offsets)


def format_probe_signature(signature: tuple[int, ...] | None) -> str:
    if not signature:
        return "unavailable"
    return "-".join(f"{int(value):02X}" for value in signature)


def format_secondary_signature(signature: tuple[int, ...] | None) -> str:
    return format_probe_signature(signature)


def _team_country(team: Any) -> str:
    try:
        value = team.get_country()
    except Exception:
        value = getattr(team, "country", "") or ""
    text = str(value or "").strip()
    return text or "Unknown"


def _team_league(team: Any) -> str:
    text = str(getattr(team, "league", "") or "").strip()
    return text or "Unknown League"


def _team_competition_label(team: Any) -> str:
    return f"{_team_country(team)} / {_team_league(team)}"


def _is_text_like_probe_byte(value: int) -> bool:
    try:
        byte = int(value)
    except Exception:
        return False
    return 0x20 <= byte <= 0x7E


def _infer_cluster_kind(
    team_count: int,
    competition_count: int,
    country_count: int,
    dominant_country_count: int,
    dominant_competition_count: int,
) -> str:
    if team_count <= 0:
        return "unknown"

    competition_purity = dominant_competition_count / team_count
    country_purity = dominant_country_count / team_count

    if competition_count == 1:
        return "competition-like"
    if country_count == 1 and competition_count > 1:
        return "country-like"
    if competition_purity >= 0.75:
        return "competition-like"
    if country_purity >= 0.75 and competition_count > 1:
        return "country-like"
    if team_count >= 8 and competition_count >= 4:
        return "shared-family"
    return "mixed"


def _infer_secondary_split_kind(
    *,
    parent_kind: str,
    signature_count: int,
    strong_competition_count: int,
    competition_count: int,
    average_purity: float,
) -> str:
    if signature_count <= 1:
        return "flat"
    if competition_count <= 1:
        return "single-competition"
    if strong_competition_count >= max(2, competition_count // 2) and average_purity >= 0.7:
        if parent_kind in {"country-like", "shared-family", "mixed"}:
            return "competition-splitting"
        return "strong"
    if average_purity >= 0.55:
        return "partial"
    return "weak"


def _infer_tertiary_split_kind(
    *,
    tertiary_offset: int | None,
    competition_count: int,
    average_purity: float,
    strong_competition_count: int,
    baseline_average_purity: float,
    baseline_strong_competition_count: int,
) -> str:
    if tertiary_offset is None:
        return "unresolved"
    if competition_count <= 1:
        return "single-competition"
    purity_gain = average_purity - baseline_average_purity
    strong_gain = strong_competition_count - baseline_strong_competition_count
    if abs(purity_gain) < 0.01 and strong_gain <= 0:
        return "no-gain"
    if average_purity >= 0.75 and strong_gain >= 1:
        return "refining"
    if purity_gain >= 0.08 and strong_competition_count >= baseline_strong_competition_count:
        return "improving"
    if purity_gain >= 0.03:
        return "marginal"
    if average_purity > baseline_average_purity:
        return "marginal"
    return "no-gain"


def _infer_family_metadata_kind(
    *,
    offset: int | None,
    competition_count: int,
    non_text_ratio: float,
    average_purity: float,
    strong_competition_count: int,
    distinct_dominants: int,
) -> str:
    if offset is None:
        return "unresolved"
    if non_text_ratio < 0.05:
        return "text-like"
    if (
        average_purity >= 0.7
        and strong_competition_count >= max(2, competition_count // 2)
        and distinct_dominants >= min(max(2, competition_count // 2), 4)
    ):
        return "promising"
    if average_purity >= 0.6 and distinct_dominants >= 2:
        return "exploratory"
    return "weak"


def _infer_dominant_country_subgroup_kind(
    *,
    offset: int | None,
    competition_count: int,
    average_purity: float,
    non_text_ratio: float,
    distinct_dominants: int,
) -> str:
    if offset is None:
        return "unresolved"
    if competition_count <= 1:
        return "single-competition"
    if distinct_dominants < 2:
        return "flat"
    if average_purity >= 0.45 and non_text_ratio >= 0.08:
        return "exploratory"
    if average_purity >= 0.35 and non_text_ratio >= 0.05:
        return "tentative"
    return "weak"


def _evaluate_signature_metrics(
    *,
    members: list[Any],
    competition_members_by_label: dict[str, list[Any]],
    offsets: tuple[int, ...],
) -> tuple[Counter[tuple[int, ...]], int, float, list[str]]:
    signature_counts = Counter(
        signature
        for signature in (_team_probe_signature(team, offsets) for team in members)
        if signature is not None
    )
    competition_signature_purities: list[float] = []
    strong_competition_count = 0
    for competition_label, competition_members in competition_members_by_label.items():
        member_signatures = [
            signature
            for signature in (_team_probe_signature(team, offsets) for team in competition_members)
            if signature is not None
        ]
        if not member_signatures:
            continue
        _dominant_signature, dominant_signature_count = Counter(member_signatures).most_common(1)[0]
        purity = dominant_signature_count / len(member_signatures)
        competition_signature_purities.append(purity)
        if purity >= 0.75:
            strong_competition_count += 1
    average_purity = (
        sum(competition_signature_purities) / len(competition_signature_purities)
        if competition_signature_purities
        else 0.0
    )
    sample_signatures: list[str] = []
    for signature, count in signature_counts.most_common(5):
        matching_competitions = Counter(
            _team_competition_label(team)
            for team in members
            if _team_probe_signature(team, offsets) == signature
        )
        dominant_signature_competition = (
            matching_competitions.most_common(1)[0][0]
            if matching_competitions
            else "Unknown"
        )
        sample_signatures.append(
            f"{format_probe_signature(signature)} ({count}) -> {dominant_signature_competition}"
        )
    return signature_counts, strong_competition_count, average_purity, sample_signatures


def _evaluate_single_byte_offset(
    *,
    members: list[Any],
    competition_members_by_label: dict[str, list[Any]],
    offset: int,
) -> tuple[int, float, int, float, int, list[str]] | None:
    values_all: list[int] = []
    competition_results: list[tuple[int, int, int, str]] = []
    for competition_label, competition_members in competition_members_by_label.items():
        values = [
            value
            for value in (_team_competition_probe_byte(team, offset) for team in competition_members)
            if value is not None
        ]
        if not values:
            continue
        counts = Counter(values)
        dominant_value, dominant_count = counts.most_common(1)[0]
        values_all.extend(values)
        competition_results.append((dominant_value, dominant_count, len(values), competition_label))

    if not values_all or not competition_results:
        return None

    strong_competition_count = sum(
        1
        for _dominant_value, dominant_count, total, _label in competition_results
        if dominant_count / max(1, total) >= 0.75
    )
    average_purity = (
        sum(dominant_count / max(1, total) for _dominant_value, dominant_count, total, _label in competition_results)
        / len(competition_results)
    )
    distinct_dominants = len({dominant_value for dominant_value, _dominant_count, _total, _label in competition_results})
    non_text_ratio = (
        sum(1 for value in values_all if not _is_text_like_probe_byte(value)) / len(values_all)
        if values_all
        else 0.0
    )
    distinct_values = len(set(values_all))
    sample_values = []
    for dominant_value, dominant_count, total, label in sorted(
        competition_results,
        key=lambda item: (-(item[1] / max(1, item[2])), item[3]),
    )[:5]:
        sample_values.append(f"{label}={dominant_value:02X}({dominant_count}/{total})")
    return (
        strong_competition_count,
        average_purity,
        distinct_dominants,
        non_text_ratio,
        distinct_values,
        sample_values,
    )


def _pick_best_country_subgroup_offset(
    *,
    members: list[Any],
    dominant_country: str,
) -> tuple[int | None, float, float, int, int, list[str]]:
    country_members = [team for team in members if _team_country(team) == dominant_country]
    if len(country_members) < 2:
        return None, 0.0, 0.0, 0, 0, []

    competition_members_by_label: dict[str, list[Any]] = defaultdict(list)
    for team in country_members:
        competition_members_by_label[_team_competition_label(team)].append(team)
    if len(competition_members_by_label) <= 1:
        return None, 0.0, 0.0, 0, len(competition_members_by_label), []

    best_offset: int | None = None
    best_non_text_ratio = 0.0
    best_average_purity = 0.0
    best_strong_competition_count = 0
    best_distinct_dominants = 0
    best_samples: list[str] = []
    best_ranking: tuple[int, int, float, int, float, int] | None = None

    for rel in COUNTRY_SUBGROUP_SCAN_OFFSETS:
        metrics = _evaluate_single_byte_offset(
            members=country_members,
            competition_members_by_label=competition_members_by_label,
            offset=rel,
        )
        if metrics is None:
            continue
        (
            candidate_strong_competition_count,
            candidate_average_purity,
            candidate_distinct_dominants,
            candidate_non_text_ratio,
            _candidate_distinct_values,
            candidate_samples,
        ) = metrics
        ranking = (
            1 if candidate_distinct_dominants >= 2 else 0,
            1 if candidate_non_text_ratio >= 0.05 else 0,
            candidate_average_purity,
            candidate_strong_competition_count,
            candidate_non_text_ratio,
            -rel,
        )
        if best_ranking is None or ranking > best_ranking:
            best_ranking = ranking
            best_offset = rel
            best_non_text_ratio = candidate_non_text_ratio
            best_average_purity = candidate_average_purity
            best_strong_competition_count = candidate_strong_competition_count
            best_distinct_dominants = candidate_distinct_dominants
            best_samples = candidate_samples

    return (
        best_offset,
        best_non_text_ratio,
        best_average_purity,
        best_strong_competition_count,
        best_distinct_dominants,
        best_samples,
    )


def analyze_competition_codebook(teams: list[Any]) -> CompetitionCodebookSummary:
    grouped: dict[int, list[Any]] = defaultdict(list)
    for team in teams:
        code = _team_competition_code(team)
        if code is None:
            continue
        grouped[code].append(team)

    clusters: list[CompetitionCodeCluster] = []
    cluster_by_code: dict[int, CompetitionCodeCluster] = {}

    for code, members in grouped.items():
        country_counts = Counter(_team_country(team) for team in members)
        competition_labels = [_team_competition_label(team) for team in members]
        competition_counts = Counter(competition_labels)
        competition_members_by_label: dict[str, list[Any]] = defaultdict(list)
        for team, label in zip(members, competition_labels):
            competition_members_by_label[label].append(team)
        dominant_country, dominant_country_count = country_counts.most_common(1)[0]
        dominant_competition, dominant_competition_count = competition_counts.most_common(1)[0]
        sample_competitions = [label for label, _count in competition_counts.most_common(5)]
        cluster_kind = _infer_cluster_kind(
            team_count=len(members),
            competition_count=len(competition_counts),
            country_count=len(country_counts),
            dominant_country_count=dominant_country_count,
            dominant_competition_count=dominant_competition_count,
        )

        (
            signature_counts,
            strong_competition_count,
            average_purity,
            sample_secondary_signatures,
        ) = _evaluate_signature_metrics(
            members=members,
            competition_members_by_label=competition_members_by_label,
            offsets=SECONDARY_SIGNATURE_OFFSETS,
        )

        tertiary_offset: int | None = None
        tertiary_signature_counts: Counter[tuple[int, ...]] = Counter()
        tertiary_strong_competition_count = 0
        tertiary_average_purity = 0.0
        sample_tertiary_signatures: list[str] = []
        best_ranking: tuple[int, float, float, int, int] | None = None
        for rel in TERTIARY_CANDIDATE_OFFSETS:
            (
                candidate_counts,
                candidate_strong_competition_count,
                candidate_average_purity,
                candidate_samples,
            ) = _evaluate_signature_metrics(
                members=members,
                competition_members_by_label=competition_members_by_label,
                offsets=SECONDARY_SIGNATURE_OFFSETS + (rel,),
            )
            if not candidate_counts:
                continue
            purity_gain = candidate_average_purity - average_purity
            ranking = (
                candidate_strong_competition_count,
                purity_gain,
                candidate_average_purity,
                len(candidate_counts),
                -rel,
            )
            if best_ranking is None or ranking > best_ranking:
                best_ranking = ranking
                tertiary_offset = rel
                tertiary_signature_counts = candidate_counts
                tertiary_strong_competition_count = candidate_strong_competition_count
                tertiary_average_purity = candidate_average_purity
                sample_tertiary_signatures = candidate_samples

        family_metadata_offset: int | None = None
        family_metadata_non_text_ratio = 0.0
        family_metadata_distinct_dominants = 0
        family_metadata_average_purity = 0.0
        family_metadata_strong_competition_count = 0
        sample_family_metadata_values: list[str] = []
        best_family_ranking: tuple[int, float, int, float, int, int] | None = None
        for rel in FAMILY_METADATA_SCAN_OFFSETS:
            metrics = _evaluate_single_byte_offset(
                members=members,
                competition_members_by_label=competition_members_by_label,
                offset=rel,
            )
            if metrics is None:
                continue
            (
                candidate_strong_competition_count,
                candidate_average_purity,
                candidate_distinct_dominants,
                candidate_non_text_ratio,
                candidate_distinct_values,
                candidate_samples,
            ) = metrics
            ranking = (
                1 if candidate_non_text_ratio >= 0.05 else 0,
                candidate_strong_competition_count,
                candidate_average_purity,
                candidate_distinct_dominants,
                candidate_non_text_ratio,
                -rel,
            )
            if best_family_ranking is None or ranking > best_family_ranking:
                best_family_ranking = ranking
                family_metadata_offset = rel
                family_metadata_non_text_ratio = candidate_non_text_ratio
                family_metadata_distinct_dominants = candidate_distinct_dominants
                family_metadata_average_purity = candidate_average_purity
                family_metadata_strong_competition_count = candidate_strong_competition_count
                sample_family_metadata_values = candidate_samples

        (
            dominant_country_subgroup_offset,
            dominant_country_subgroup_non_text_ratio,
            dominant_country_subgroup_average_purity,
            dominant_country_subgroup_strong_competition_count,
            dominant_country_subgroup_distinct_dominants,
            sample_dominant_country_subgroup_values,
        ) = _pick_best_country_subgroup_offset(
            members=members,
            dominant_country=dominant_country,
        )

        cluster = CompetitionCodeCluster(
            code=code,
            team_count=len(members),
            competition_count=len(competition_counts),
            country_count=len(country_counts),
            dominant_country=dominant_country,
            dominant_country_count=dominant_country_count,
            dominant_competition=dominant_competition,
            dominant_competition_count=dominant_competition_count,
            inferred_kind=cluster_kind,
            sample_competitions=sample_competitions,
            secondary_signature_count=len(signature_counts),
            secondary_strong_competition_count=strong_competition_count,
            secondary_average_competition_purity=average_purity,
            secondary_inferred_kind=_infer_secondary_split_kind(
                parent_kind=cluster_kind,
                signature_count=len(signature_counts),
                strong_competition_count=strong_competition_count,
                competition_count=len(competition_counts),
                average_purity=average_purity,
            ),
            sample_secondary_signatures=sample_secondary_signatures,
            tertiary_offset=tertiary_offset,
            tertiary_signature_count=len(tertiary_signature_counts),
            tertiary_strong_competition_count=tertiary_strong_competition_count,
            tertiary_average_competition_purity=tertiary_average_purity,
            tertiary_inferred_kind=_infer_tertiary_split_kind(
                tertiary_offset=tertiary_offset,
                competition_count=len(competition_counts),
                average_purity=tertiary_average_purity,
                strong_competition_count=tertiary_strong_competition_count,
                baseline_average_purity=average_purity,
                baseline_strong_competition_count=strong_competition_count,
            ),
            sample_tertiary_signatures=sample_tertiary_signatures,
            family_metadata_offset=family_metadata_offset,
            family_metadata_non_text_ratio=family_metadata_non_text_ratio,
            family_metadata_distinct_dominants=family_metadata_distinct_dominants,
            family_metadata_average_competition_purity=family_metadata_average_purity,
            family_metadata_strong_competition_count=family_metadata_strong_competition_count,
            family_metadata_inferred_kind=_infer_family_metadata_kind(
                offset=family_metadata_offset,
                competition_count=len(competition_counts),
                non_text_ratio=family_metadata_non_text_ratio,
                average_purity=family_metadata_average_purity,
                strong_competition_count=family_metadata_strong_competition_count,
                distinct_dominants=family_metadata_distinct_dominants,
            ),
            sample_family_metadata_values=sample_family_metadata_values,
            dominant_country_subgroup_offset=dominant_country_subgroup_offset,
            dominant_country_subgroup_non_text_ratio=dominant_country_subgroup_non_text_ratio,
            dominant_country_subgroup_average_competition_purity=dominant_country_subgroup_average_purity,
            dominant_country_subgroup_strong_competition_count=dominant_country_subgroup_strong_competition_count,
            dominant_country_subgroup_distinct_dominants=dominant_country_subgroup_distinct_dominants,
            dominant_country_subgroup_inferred_kind=_infer_dominant_country_subgroup_kind(
                offset=dominant_country_subgroup_offset,
                competition_count=len(
                    {
                        _team_competition_label(team)
                        for team in members
                        if _team_country(team) == dominant_country
                    }
                ),
                average_purity=dominant_country_subgroup_average_purity,
                non_text_ratio=dominant_country_subgroup_non_text_ratio,
                distinct_dominants=dominant_country_subgroup_distinct_dominants,
            ),
            sample_dominant_country_subgroup_values=sample_dominant_country_subgroup_values,
        )
        clusters.append(cluster)
        cluster_by_code[code] = cluster

    clusters.sort(key=lambda item: (-item.team_count, item.code))
    return CompetitionCodebookSummary(
        assigned_team_count=sum(cluster.team_count for cluster in clusters),
        clusters=clusters,
        cluster_by_code=cluster_by_code,
    )


def _split_competition_label(label: str) -> tuple[str, str]:
    text = str(label or "").strip()
    if " / " in text:
        country, league = text.split(" / ", 1)
        return (country.strip() or "Unknown"), (league.strip() or "Unknown League")
    if not text:
        return "Unknown", "Unknown League"
    return "Unknown", text


def _probe_confidence(*, purity: float, support_count: int) -> str:
    if support_count >= 3 and purity >= 0.9:
        return "high"
    if support_count >= 2 and purity >= 0.8:
        return "medium"
    if support_count >= 2 and purity >= 0.65:
        return "low"
    return "unresolved"


def _safe_country_label(value: Any) -> str:
    text = str(value or "").strip()
    return text or "Unknown"


def _safe_league_label(value: Any) -> str:
    text = str(value or "").strip()
    return text or "Unknown League"


def resolve_league_assignment_contract(
    *,
    current_country: str,
    current_league: str,
    current_source: str,
    probe: LeagueAssignmentProbe | None,
    allow_medium_promotions: bool = True,
) -> LeagueAssignmentResolution:
    source = str(current_source or "unknown").strip() or "unknown"
    country = _safe_country_label(current_country)
    league = _safe_league_label(current_league)

    probe_confidence = str(getattr(probe, "confidence", "") or "unresolved")
    probe_method = str(getattr(probe, "method", "") or "unresolved")
    probe_matches = getattr(probe, "matches_assigned_competition", None)
    candidate_country = _safe_country_label(getattr(probe, "candidate_country", ""))
    candidate_league = _safe_league_label(getattr(probe, "candidate_league", ""))
    allowed_confidences = {"high", "medium"} if allow_medium_promotions else {"high"}

    if source != "team_id_range":
        if (
            probe is not None
            and probe_confidence in allowed_confidences
            and probe_method in PROMOTABLE_LEAGUE_PROBE_METHODS
        ):
            return LeagueAssignmentResolution(
                source="competition_probe_contract",
                country=candidate_country,
                league=candidate_league,
                confidence=("high" if probe_confidence == "high" else "medium"),
                status="probe-promoted",
                promoted=True,
                promoted_from_source=source,
                promoted_method=probe_method,
                promoted_probe_confidence=probe_confidence,
            )

    if source == "team_id_range":
        return LeagueAssignmentResolution(
            source=source,
            country=country,
            league=league,
            confidence="high",
            status="confirmed",
        )

    if source == "competition_probe_contract":
        return LeagueAssignmentResolution(
            source=source,
            country=country,
            league=league,
            confidence=("high" if probe_confidence == "high" else "medium"),
            status="probe-promoted",
            promoted=True,
            promoted_from_source="competition_probe_contract",
            promoted_method=probe_method,
            promoted_probe_confidence=probe_confidence,
        )

    if source == "sequence_fallback":
        if probe_confidence in {"high", "medium"} and probe_matches is True:
            return LeagueAssignmentResolution(
                source=source,
                country=country,
                league=league,
                confidence="medium",
                status="supported",
            )
        if probe_confidence in {"high", "medium"} and probe_matches is False:
            return LeagueAssignmentResolution(
                source=source,
                country=country,
                league=league,
                confidence="review",
                status="probe-mismatch",
            )
        if probe_confidence == "low" and probe_matches is True:
            return LeagueAssignmentResolution(
                source=source,
                country=country,
                league=league,
                confidence="low",
                status="weakly-supported",
            )
        return LeagueAssignmentResolution(
            source=source,
            country=country,
            league=league,
            confidence="low",
            status="fallback",
        )

    if probe_confidence in {"high", "medium"} and probe_matches is True:
        return LeagueAssignmentResolution(
            source=source,
            country=country,
            league=league,
            confidence="medium",
            status="probe-only",
        )
    if probe_confidence in {"high", "medium"} and probe_matches is False:
        return LeagueAssignmentResolution(
            source=source,
            country=country,
            league=league,
            confidence="review",
            status="probe-mismatch",
        )
    if probe_confidence == "low":
        return LeagueAssignmentResolution(
            source=source,
            country=country,
            league=league,
            confidence="low",
            status="probe-weak",
        )
    return LeagueAssignmentResolution(
        source=source,
        country=country,
        league=league,
        confidence="unresolved",
        status="unresolved",
    )


def _build_signal_competition_map(
    *,
    members: list[Any],
    signal_getter,
    allowed_labels: set[str] | None = None,
) -> dict[Any, tuple[str, int, int, float]]:
    values_by_signal: dict[Any, list[str]] = defaultdict(list)
    for team in members:
        signal = signal_getter(team)
        if signal is None:
            continue
        label = _team_competition_label(team)
        if allowed_labels is not None and label not in allowed_labels:
            continue
        values_by_signal[signal].append(label)

    out: dict[Any, tuple[str, int, int, float]] = {}
    for signal, labels in values_by_signal.items():
        if len(labels) < 2:
            continue
        counts = Counter(labels)
        dominant_label, support_count = counts.most_common(1)[0]
        total_count = len(labels)
        purity = support_count / max(1, total_count)
        if purity < 0.65:
            continue
        out[signal] = (dominant_label, support_count, total_count, purity)
    return out


def derive_league_assignment_probes(teams: list[Any]) -> dict[int, LeagueAssignmentProbe]:
    codebook = analyze_competition_codebook(teams)
    teams_by_code: dict[int, list[Any]] = defaultdict(list)
    for team in teams:
        code = _team_competition_code(team)
        if code is None:
            continue
        teams_by_code[code].append(team)

    probes_by_identity: dict[int, LeagueAssignmentProbe] = {}
    confidence_rank = {"high": 3, "medium": 2, "low": 1, "unresolved": 0}

    for code, members in teams_by_code.items():
        cluster = codebook.cluster_by_code.get(code)
        if cluster is None:
            continue

        primary_map = _build_signal_competition_map(
            members=members,
            signal_getter=lambda _team: int(code),
        )
        secondary_map = _build_signal_competition_map(
            members=members,
            signal_getter=lambda team: _team_secondary_signature(team, SECONDARY_SIGNATURE_OFFSETS),
        )

        tertiary_map: dict[Any, tuple[str, int, int, float]] = {}
        tertiary_offset = cluster.tertiary_offset
        if tertiary_offset is not None:
            tertiary_map = _build_signal_competition_map(
                members=members,
                signal_getter=lambda team: _team_probe_signature(
                    team, SECONDARY_SIGNATURE_OFFSETS + (int(tertiary_offset),)
                ),
            )

        family_offset = cluster.family_metadata_offset
        family_map: dict[Any, tuple[str, int, int, float]] = {}
        if family_offset is not None:
            family_map = _build_signal_competition_map(
                members=members,
                signal_getter=lambda team: _team_competition_probe_byte(team, int(family_offset)),
            )

        subgroup_offset = cluster.dominant_country_subgroup_offset
        subgroup_map: dict[Any, tuple[str, int, int, float]] = {}
        subgroup_allowed_labels: set[str] = {
            _team_competition_label(team)
            for team in members
            if _team_country(team) == cluster.dominant_country
        }
        if subgroup_offset is not None and subgroup_allowed_labels:
            subgroup_map = _build_signal_competition_map(
                members=members,
                signal_getter=lambda team: _team_competition_probe_byte(team, int(subgroup_offset)),
                allowed_labels=subgroup_allowed_labels,
            )

        for team in members:
            assigned_competition = _team_competition_label(team)
            candidates: list[dict[str, Any]] = []

            def _consider_candidate(
                *,
                method: str,
                method_priority: int,
                signal_name: str,
                signal_offset: int | None,
                signal_value: Any,
                signal_display: str,
                signal_map: dict[Any, tuple[str, int, int, float]],
            ) -> None:
                if signal_value is None:
                    return
                match = signal_map.get(signal_value)
                if match is None:
                    return
                candidate_competition, support_count, total_count, purity = match
                confidence = _probe_confidence(purity=purity, support_count=support_count)
                if confidence == "unresolved":
                    return
                candidates.append(
                    {
                        "method": method,
                        "method_priority": method_priority,
                        "signal_name": signal_name,
                        "signal_offset": signal_offset,
                        "signal_value_display": signal_display,
                        "candidate_competition": candidate_competition,
                        "purity": purity,
                        "support_count": support_count,
                        "total_count": total_count,
                        "confidence": confidence,
                    }
                )

            secondary_signature = _team_secondary_signature(team, SECONDARY_SIGNATURE_OFFSETS)
            tertiary_signature = (
                _team_probe_signature(team, SECONDARY_SIGNATURE_OFFSETS + (int(tertiary_offset),))
                if tertiary_offset is not None
                else None
            )
            family_value = (
                _team_competition_probe_byte(team, int(family_offset))
                if family_offset is not None
                else None
            )
            subgroup_value = (
                _team_competition_probe_byte(team, int(subgroup_offset))
                if subgroup_offset is not None
                else None
            )

            _consider_candidate(
                method="primary_code",
                method_priority=1,
                signal_name="primary_code",
                signal_offset=0,
                signal_value=int(code),
                signal_display=f"0x{int(code):02X}",
                signal_map=primary_map,
            )
            _consider_candidate(
                method="secondary_signature",
                method_priority=4,
                signal_name="secondary_signature",
                signal_offset=None,
                signal_value=secondary_signature,
                signal_display=format_probe_signature(secondary_signature),
                signal_map=secondary_map,
            )
            _consider_candidate(
                method="tertiary_signature",
                method_priority=5,
                signal_name="tertiary_signature",
                signal_offset=tertiary_offset,
                signal_value=tertiary_signature,
                signal_display=format_probe_signature(tertiary_signature),
                signal_map=tertiary_map,
            )
            _consider_candidate(
                method="family_metadata_byte",
                method_priority=3,
                signal_name="family_metadata_byte",
                signal_offset=family_offset,
                signal_value=family_value,
                signal_display=(
                    f"0x{int(family_value):02X}" if family_value is not None else "unavailable"
                ),
                signal_map=family_map,
            )
            if _team_country(team) == cluster.dominant_country:
                _consider_candidate(
                    method="dominant_country_subgroup_byte",
                    method_priority=2,
                    signal_name="dominant_country_subgroup_byte",
                    signal_offset=subgroup_offset,
                    signal_value=subgroup_value,
                    signal_display=(
                        f"0x{int(subgroup_value):02X}" if subgroup_value is not None else "unavailable"
                    ),
                    signal_map=subgroup_map,
                )

            if not candidates:
                continue

            best = max(
                candidates,
                key=lambda item: (
                    confidence_rank.get(str(item["confidence"]), 0),
                    int(item["method_priority"]),
                    float(item["purity"]),
                    int(item["support_count"]),
                ),
            )
            candidate_country, candidate_league = _split_competition_label(str(best["candidate_competition"]))
            probes_by_identity[id(team)] = LeagueAssignmentProbe(
                primary_code=int(code),
                method=str(best["method"]),
                signal_name=str(best["signal_name"]),
                signal_offset=(int(best["signal_offset"]) if best["signal_offset"] is not None else None),
                signal_value_display=str(best["signal_value_display"]),
                candidate_competition=str(best["candidate_competition"]),
                candidate_country=candidate_country,
                candidate_league=candidate_league,
                purity=float(best["purity"]),
                support_count=int(best["support_count"]),
                total_count=int(best["total_count"]),
                confidence=str(best["confidence"]),
                assigned_competition=assigned_competition,
                matches_assigned_competition=(str(best["candidate_competition"]) == assigned_competition),
            )

    return probes_by_identity
