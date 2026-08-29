
from __future__ import annotations

from dataclasses import dataclass, field

from apps.pathway.services.domain import FOUNDATION_DOMAINS, determine_primary_domain, relevant_domains
from apps.profiles.models import LearnerProfile
from apps.catalog.models import LearnerProjectState
from apps.catalog.services.projects import ProjectMeta, load_project_seed

WEIGHTS = {
    "role_alignment": 0.20,
    "goal_alignment": 0.20,
    "readiness_margin": 0.20,
    "current_path_relevance": 0.15,
    "difficulty_fit": 0.10,
    "portfolio_value": 0.10,
    "interest_alignment": 0.05,
}

_PORTFOLIO_VALUE_SCORE = {"high": 1.0, "medium": 0.6, "low": 0.3}
_DIFFICULTY_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}
_EXPERIENCE_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 2}


@dataclass
class ProjectRecommendation:
    project: ProjectMeta
    status: str
    score: float
    domain_match: bool
    role_match: float
    readiness: float
    path_relevance: float = 0.0
    satisfied_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    difficulty_fit: float = 0.0
    reason: str = ""


def _skill_satisfied(skill: str, evidence: dict[str, str], completed: set[str]) -> bool:
    return evidence.get(skill) in ("known", "inferred") or skill in completed


def compute_readiness(profile: LearnerProfile, project: ProjectMeta) -> tuple[float, list[str], list[str]]:
    if not project.skills:
        return 1.0, [], []
    evidence = {e.skill: e.evidence_level for e in profile.skills.all()}
    completed = set(profile.history.filter(status="completed").values_list("course", flat=True))
    satisfied, missing = [], []
    for skill in project.skills:
        if _skill_satisfied(skill, evidence, completed):
            satisfied.append(skill)
        else:
            missing.append(skill)
    return len(satisfied) / len(project.skills), satisfied, missing


def _difficulty_fit(project_difficulty: str, experience_level: str) -> float:
    p_rank = _DIFFICULTY_RANK.get(project_difficulty.lower(), 1)
    l_rank = _EXPERIENCE_RANK.get(experience_level, 0)
    gap = abs(p_rank - l_rank)
    return {0: 1.0, 1: 0.6, 2: 0.25}.get(gap, 0.1)


def _role_alignment(project: ProjectMeta, target_role: str) -> float:
    if not project.target_roles:
        return 0.5
    if not target_role:
        return 0.5
    role_norm = target_role.strip().lower()
    for tagged in project.target_roles:
        tagged_norm = tagged.strip().lower()
        if role_norm == tagged_norm or role_norm in tagged_norm or tagged_norm in role_norm:
            return 1.0
    return 0.0


def _current_path_relevance(project: ProjectMeta, path) -> float:
    if path is None or not project.skills:
        return 0.0
    path_courses = set(
        path.items.filter(status__in=("current", "upcoming", "completed")).values_list("course", flat=True)
    )
    if not path_courses:
        return 0.0
    overlap = sum(1 for s in project.skills if s in path_courses)
    return overlap / len(project.skills)


def _interest_alignment(project: ProjectMeta, primary_domain: str | None, explicit_interests: set[str]) -> float:
    if project.domain == primary_domain:
        return 0.0
    return 1.0 if project.domain in explicit_interests else 0.0


def _reason_for(project: ProjectMeta, readiness: float, satisfied: list[str], missing: list[str],
                 domain_match: bool, role_match: float, path_relevance: float) -> str:
    if not domain_match:
        return f'Outside your current target domain ({project.domain}).'
    if readiness < 1.0:
        return f"Locked — still missing: {', '.join(missing)}."
    skills_str = ", ".join(satisfied) if satisfied else "no specific prerequisites"
    tail = ""
    if role_match >= 1.0 and project.target_roles:
        tail = f" It's specifically tagged for your target role."
    elif path_relevance > 0:
        tail = " It practices skills currently in your active path."
    return f"Unlocked — you already have {skills_str}, the skills this project demonstrates.{tail}"


def recommend_projects(profile: LearnerProfile, path=None, limit: int | None = None) -> list[ProjectRecommendation]:
    all_projects = load_project_seed()
    states = {s.project_slug: s for s in profile.project_states.all()}

    primary_domain = determine_primary_domain(profile)
    relevant = relevant_domains(primary_domain)
    explicit_interests = set(profile.interests.values_list("label", flat=True))

    def domain_in_scope(domain: str) -> bool:
        if relevant is None:
            return True
        return domain in FOUNDATION_DOMAINS or domain in relevant or domain in explicit_interests

    results = []
    for project in all_projects:
        state = states.get(project.slug)
        readiness, satisfied, missing = compute_readiness(profile, project)
        domain_match = domain_in_scope(project.domain)
        role_match = _role_alignment(project, profile.target_role or "")
        difficulty_fit = _difficulty_fit(project.difficulty, profile.experience_level)
        path_relevance = _current_path_relevance(project, path)
        interest_score = _interest_alignment(project, primary_domain, explicit_interests)

        if state and state.status in ("completed", "published"):
            status = state.status
        elif readiness >= 1.0 and domain_match:
            status = "recommended"
        else:
            status = "locked"

        portfolio_score = _PORTFOLIO_VALUE_SCORE.get(project.portfolio_value.lower(), 0.5)
        goal_alignment = 1.0 if (domain_match and project.domain == primary_domain) else (0.6 if domain_match else 0.0)
        readiness_margin = readiness

        score = (
            WEIGHTS["role_alignment"] * role_match
            + WEIGHTS["goal_alignment"] * goal_alignment
            + WEIGHTS["readiness_margin"] * readiness_margin
            + WEIGHTS["current_path_relevance"] * path_relevance
            + WEIGHTS["difficulty_fit"] * difficulty_fit
            + WEIGHTS["portfolio_value"] * portfolio_score
            + WEIGHTS["interest_alignment"] * interest_score
        )

        results.append(ProjectRecommendation(
            project=project,
            status=status,
            score=round(score, 4),
            domain_match=domain_match,
            role_match=role_match,
            readiness=round(readiness, 4),
            path_relevance=round(path_relevance, 4),
            satisfied_skills=satisfied,
            missing_skills=missing,
            difficulty_fit=difficulty_fit,
            reason=_reason_for(project, readiness, satisfied, missing, domain_match, role_match, path_relevance),
        ))


    results.sort(key=lambda r: (r.status == "recommended", r.score), reverse=True)
    return results[:limit] if limit else results
