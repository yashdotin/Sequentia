
from __future__ import annotations

from dataclasses import dataclass

from apps.profiles.models import LearnerProfile
from apps.recommender.ml.inference import get_engine
from apps.recommender.ml.metadata import CourseMeta


WEIGHTS = {
    "semantic_relevance": 0.30,
    "interest_alignment": 0.20,
    "skill_gap": 0.20,
    "prerequisite_readiness": 0.20,
    "difficulty_fit": 0.10,
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
    evidence = {e.skill: e.evidence_level for e in profile.skills.all()}
    for entry in profile.history.filter(status="completed"):
        evidence[entry.course] = "known"
    return evidence


def _interest_set(profile: LearnerProfile) -> set[str]:
    return {i.label for i in profile.interests.all()}


def _prerequisite_readiness(meta: CourseMeta, evidence: dict[str, str]) -> tuple[float, list[str]]:
    if not meta.prerequisites:
        return 1.0, []

    satisfied = 0
    missing: list[str] = []
    for prereq in meta.prerequisites:
        level = evidence.get(prereq, "unknown")
        if level == "known":
            satisfied += 1
        elif level == "inferred":
            satisfied += 0.5
        else:
            missing.append(prereq)

    readiness = satisfied / len(meta.prerequisites)
    return readiness, missing


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
        meta = engine.get_course(course).meta

        semantic_score = semantic.get(course, 0.0) / max_semantic
        interest_score = 1.0 if meta.domain in interests else 0.0
        readiness, missing = _prerequisite_readiness(meta, evidence)
        difficulty_score = _difficulty_fit(meta, profile.experience_level)


        current_level = evidence.get(course, "unknown")
        skill_gap_score = {"unknown": 1.0, "inferred": 0.6, "known": 0.05}[current_level]

        components = {
            "semantic_relevance": semantic_score,
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
