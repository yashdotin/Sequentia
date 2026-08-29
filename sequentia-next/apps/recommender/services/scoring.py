"""Transparent, role-aware course scoring over the canonical catalog."""

from __future__ import annotations

from dataclasses import dataclass

from apps.profiles.models import LearnerProfile
from apps.recommender.ml.canonical import load_skill_catalog, resolve_skill_ids, skill_display
from apps.recommender.ml.inference import get_engine
from apps.recommender.ml.metadata import CourseMeta

WEIGHTS = {
    "semantic_relevance": 0.25,
    "role_alignment": 0.20,
    "interest_alignment": 0.15,
    "skill_gap": 0.20,
    "prerequisite_readiness": 0.15,
    "difficulty_fit": 0.05,
}

_EXPERIENCE_TO_DIFFICULTY_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}
_DIFFICULTY_RANK = {"Beginner": 0, "Intermediate": 1, "Advanced": 2}


@dataclass
class CourseScore:
    course: str
    meta: CourseMeta
    total: float
    components: dict[str, float]
    prerequisite_readiness: float
    missing_prerequisites: list[str]
    already_covered: bool


def _skill_evidence_map(profile: LearnerProfile) -> dict[str, str]:
    evidence: dict[str, str] = {}

    for entry in profile.skills.all():
        value = entry.skill.strip()
        evidence[value] = entry.evidence_level
        for skill_id in resolve_skill_ids(value):
            previous = evidence.get(skill_id)
            rank = {"unknown": 0, "inferred": 1, "known": 2}
            if previous is None or rank.get(entry.evidence_level, 0) > rank.get(previous, 0):
                evidence[skill_id] = entry.evidence_level

    for entry in profile.history.filter(status="completed"):
        evidence[entry.course] = "known"
        for skill_id in resolve_skill_ids(entry.course):
            evidence[skill_id] = "known"

    return evidence


def _interest_set(profile: LearnerProfile) -> set[str]:
    return {i.label for i in profile.interests.all()}


def _prerequisite_readiness(meta: CourseMeta, evidence: dict[str, str]) -> tuple[float, list[str]]:
    prerequisites = meta.prerequisite_skill_ids

    # Backward-compatible fallback for old metadata/test fixtures.
    if not prerequisites:
        prerequisites = tuple(meta.prerequisites)

    if not prerequisites:
        return 1.0, []

    satisfied = 0.0
    missing: list[str] = []
    skills = load_skill_catalog()

    for prereq in prerequisites:
        level = evidence.get(prereq, "unknown")
        if prereq in skills:
            display = skill_display(prereq)
        else:
            display = prereq
            resolved = resolve_skill_ids(prereq)
            if resolved:
                level = evidence.get(resolved[0], level)
                display = skill_display(resolved[0])

        if level == "known":
            satisfied += 1.0
        elif level == "inferred":
            satisfied += 0.5
        else:
            missing.append(display)

    return satisfied / len(prerequisites), missing


def _difficulty_fit(meta: CourseMeta, experience_level: str) -> float:
    learner_rank = _EXPERIENCE_TO_DIFFICULTY_RANK.get(experience_level, 0)
    course_rank = _DIFFICULTY_RANK[meta.difficulty]
    gap = course_rank - learner_rank
    if gap == 0:
        return 1.0
    if gap == 1:
        return 0.6
    if gap < 0:
        return 0.5
    return 0.15


def _role_alignment(meta: CourseMeta, target_role: str) -> float:
    if not target_role or not meta.target_roles:
        return 0.5
    target = target_role.strip().lower()
    for role in meta.target_roles:
        tagged = role.strip().lower()
        if target == tagged or target in tagged or tagged in target:
            return 1.0
    return 0.0


def _skill_gap_score(meta: CourseMeta, evidence: dict[str, str]) -> float:
    skill_ids = meta.canonical_skill_ids
    if not skill_ids:
        level = evidence.get(meta.course, "unknown")
        return {"unknown": 1.0, "inferred": 0.6, "known": 0.05}.get(level, 1.0)

    values = [evidence.get(skill_id, "unknown") for skill_id in skill_ids]
    if all(v == "known" for v in values):
        return 0.05
    if any(v == "unknown" for v in values):
        return 1.0
    return 0.6


def _feedback_adjustment_map(profile: LearnerProfile) -> dict[str, float]:
    adjustments: dict[str, float] = {}
    for fb in profile.recommendation_feedback.select_related("recommendation"):
        course = fb.recommendation.course
        delta = 0.08 if fb.feedback == "helpful" else -0.15
        adjustments[course] = adjustments.get(course, 0.0) + delta
    return adjustments


def score_all_courses(profile: LearnerProfile, query_text: str) -> list[CourseScore]:
    engine = get_engine()
    semantic = dict(engine.semantic_relevance(query_text))
    evidence = _skill_evidence_map(profile)
    interests = _interest_set(profile)
    covered_courses = {
        e.course for e in profile.history.filter(status__in=["completed", "skipped"])
    }
    feedback_adjustments = _feedback_adjustment_map(profile)
    max_semantic = max(semantic.values()) if semantic and max(semantic.values()) > 0 else 1.0

    scores: list[CourseScore] = []
    for course in engine.all_courses:
        corpus = engine.get_course(course)
        if corpus is None:
            continue
        meta = corpus.meta

        semantic_score = semantic.get(course, 0.0) / max_semantic
        interest_score = 1.0 if meta.domain in interests else 0.0
        role_score = _role_alignment(meta, profile.target_role or "")
        readiness, missing = _prerequisite_readiness(meta, evidence)
        difficulty_score = _difficulty_fit(meta, profile.experience_level)
        skill_gap_score = _skill_gap_score(meta, evidence)

        components = {
            "semantic_relevance": semantic_score,
            "role_alignment": role_score,
            "interest_alignment": interest_score,
            "skill_gap": skill_gap_score,
            "prerequisite_readiness": readiness,
            "difficulty_fit": difficulty_score,
        }
        total = sum(WEIGHTS[k] * v for k, v in components.items())
        total = max(0.0, min(1.0, total + feedback_adjustments.get(course, 0.0)))

        scores.append(
            CourseScore(
                course=course,
                meta=meta,
                total=total,
                components=components,
                prerequisite_readiness=readiness,
                missing_prerequisites=missing,
                already_covered=course in covered_courses,
            )
        )

    scores.sort(key=lambda s: s.total, reverse=True)
    return scores
