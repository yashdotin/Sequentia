"""
Project recommendation — a first-class system, separate from course scoring.

A project's job is to demonstrate/practice/prove skills, not to be "the next
best semantic match." So this module does NOT call score_all_courses() or
reuse course-scoring weights. It computes:

  1. readiness (hard gate) — every required skill must be satisfied
     (known/inferred evidence, or completed-in-history) before a project
     is ever offered as "recommended now". This is the fix for the bug
     where unlocking used to check `path_item.stage == project.stage`
     against string values that silently drifted apart once path stages
     became domain-derived instead of a fixed list.

  2. score (soft ranking, only among already-unlocked projects) — goal/
     domain alignment, portfolio value, and difficulty fit relative to the
     learner's stated experience level. Configurable, transparent weights.

Projects outside the learner's relevant domain set are excluded from
"recommended", same domain-contamination rule the path engine uses — a
Web Development learner should not be handed an ML capstone as their
suggested project just because it scored fine on some other axis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.pathway.services.domain import FOUNDATION_DOMAINS, determine_primary_domain, relevant_domains
from apps.profiles.models import LearnerProfile
from apps.catalog.models import LearnerProjectState
from apps.catalog.services.projects import ProjectMeta, load_project_seed

WEIGHTS = {
    "goal_alignment": 0.35,
    "portfolio_value": 0.20,
    "difficulty_fit": 0.20,
    "readiness_margin": 0.25,  # rewards projects that are *comfortably* unlocked, not barely
}

_PORTFOLIO_VALUE_SCORE = {"high": 1.0, "medium": 0.6, "low": 0.3}
_DIFFICULTY_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}
_EXPERIENCE_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 2}


@dataclass
class ProjectRecommendation:
    project: ProjectMeta
    status: str  # "recommended" | "locked" | "completed" | "published"
    score: float
    domain_match: bool
    readiness: float
    satisfied_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    difficulty_fit: float = 0.0
    reason: str = ""


def _skill_satisfied(skill: str, evidence: dict[str, str], completed: set[str]) -> bool:
    return evidence.get(skill) in ("known", "inferred") or skill in completed


def compute_readiness(profile: LearnerProfile, project: ProjectMeta) -> tuple[float, list[str], list[str]]:
    """(readiness 0..1, satisfied_skills, missing_skills) — same evidence
    signal as scoring._skill_evidence_map, so a project and a course never
    disagree about whether a skill is "known"."""
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


def _reason_for(project: ProjectMeta, readiness: float, satisfied: list[str], missing: list[str], domain_match: bool) -> str:
    if not domain_match:
        return f'Outside your current target domain ({project.domain}).'
    if readiness >= 1.0:
        skills_str = ", ".join(satisfied) if satisfied else "no specific prerequisites"
        return f"Unlocked — you already have {skills_str}, the skills this project demonstrates."
    return f"Locked — still missing: {', '.join(missing)}."


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
        difficulty_fit = _difficulty_fit(project.difficulty, profile.experience_level)

        if state and state.status in ("completed", "published"):
            status = state.status
        elif readiness >= 1.0 and domain_match:
            status = "recommended"
        else:
            status = "locked"

        portfolio_score = _PORTFOLIO_VALUE_SCORE.get(project.portfolio_value.lower(), 0.5)
        goal_alignment = 1.0 if (domain_match and project.domain == primary_domain) else (0.6 if domain_match else 0.0)
        readiness_margin = readiness  # comfortably-unlocked projects rank a little higher among unlocked ones

        score = (
            WEIGHTS["goal_alignment"] * goal_alignment
            + WEIGHTS["portfolio_value"] * portfolio_score
            + WEIGHTS["difficulty_fit"] * difficulty_fit
            + WEIGHTS["readiness_margin"] * readiness_margin
        )

        results.append(ProjectRecommendation(
            project=project,
            status=status,
            score=round(score, 4),
            domain_match=domain_match,
            readiness=round(readiness, 4),
            satisfied_skills=satisfied,
            missing_skills=missing,
            difficulty_fit=difficulty_fit,
            reason=_reason_for(project, readiness, satisfied, missing, domain_match),
        ))

    # Recommended-and-in-domain first, ranked by score; everything else after.
    results.sort(key=lambda r: (r.status == "recommended", r.score), reverse=True)
    return results[:limit] if limit else results
