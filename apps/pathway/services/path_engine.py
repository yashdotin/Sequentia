"""
Builds the personalized, sequenced learning path — the core algorithm.

Answers "what sequence of resources is most useful for THIS learner", not just
"which courses score highest individually": prerequisite-blocked courses are
never marked current/upcoming no matter how relevant they score, and exactly
one item is ever marked "current" (the single next best action).
"""

from __future__ import annotations

import csv

from django.conf import settings
from django.db import transaction
from django.db.models import Max

from apps.pathway.models import LearningPath, LearningPathItem, PathChangeEvent
from apps.profiles.models import LearnerProfile
from apps.recommender.models import Recommendation
from apps.recommender.services.explainability import explain_recommendation
from apps.recommender.services.scoring import CourseScore, score_all_courses

# Curated domain -> stage grouping. Like the metadata seed, this is a manual
# categorization (not derived from the dataset) that gives the path a readable
# shape (Foundations -> ... -> Specialization) instead of 13 flat domains.
DOMAIN_TO_STAGE = {
    "Programming Foundations": "Foundations",
    "Math Foundations": "Foundations",
    "Developer Tools": "Foundations",
    "Databases": "Foundations",
    "Web Development": "Core Skills",
    "Mobile Development": "Core Skills",
    "Data Analytics": "Core Skills",
    "Machine Learning": "Machine Learning",
    "Deep Learning": "Deep Learning",
    "Data Engineering": "Production & Data Systems",
    "DevOps": "Production & Data Systems",
    "Cloud": "Production & Data Systems",
    "MLOps": "Production & Data Systems",
    "Security": "Specialization",
    "Blockchain": "Specialization",
    "Systems": "Specialization",
}
STAGE_ORDER = [
    "Foundations",
    "Core Skills",
    "Machine Learning",
    "Deep Learning",
    "Production & Data Systems",
    "Specialization",
]
ITEMS_PER_STAGE = 4


def _portfolio_relevant_skills() -> set[str]:
    """
    Courses that appear as a listed skill in the curated project seed
    (data/project_seed.csv). Read directly rather than importing the catalog
    app, to avoid a circular import (catalog -> dashboard -> pathway).
    Used only as an Internship Mode tiebreak, never to change the core score.
    """
    path = settings.PROJECT_SEED_CSV
    skills: set[str] = set()
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                skills.update(s.strip() for s in row["skills"].split(",") if s.strip())
    except FileNotFoundError:
        pass
    return skills


def _covered_courses(profile: LearnerProfile) -> set[str]:
    return set(profile.history.filter(status="completed").values_list("course", flat=True))


@transaction.atomic
def generate_path(profile: LearnerProfile, query_text: str, reason: str) -> LearningPath:
    """
    Scores every course, buckets eligible ones into stages, picks exactly one
    "current" item, and persists the result as a new path version. Never
    mutates an existing version — every regeneration is a new row, which is
    what makes path history/versioning possible.
    """
    scores = score_all_courses(profile, query_text)
    covered = _covered_courses(profile)
    by_course: dict[str, CourseScore] = {s.course: s for s in scores}

    eligible: list[CourseScore] = []
    blocked: list[CourseScore] = []
    completed: list[CourseScore] = []

    for s in scores:
        if s.course in covered:
            completed.append(s)
        elif s.missing_prerequisites:
            blocked.append(s)
        else:
            eligible.append(s)

    eligible.sort(key=lambda s: s.total, reverse=True)

    portfolio_skills = _portfolio_relevant_skills() if profile.internship_mode else set()
    if profile.internship_mode:
        # Stable secondary sort: among close scores, surface courses that feed
        # a real curated project first. Never overrides a meaningfully higher
        # base score — this is a tiebreak, not a reweighting.
        eligible.sort(key=lambda s: (round(s.total, 2), s.course in portfolio_skills), reverse=True)

    current_course = eligible[0].course if eligible else None

    prev = profile.paths.filter(is_current=True).first()
    if prev:
        prev.is_current = False
        prev.save(update_fields=["is_current"])
        next_version = prev.version + 1
    else:
        next_version = 1

    path = LearningPath.objects.create(
        profile=profile,
        version=next_version,
        goal_snapshot=profile.goal_text,
        change_reason=reason,
        is_current=True,
    )

    position = 0
    for stage in STAGE_ORDER:
        stage_completed = [s for s in completed if DOMAIN_TO_STAGE.get(s.meta.domain) == stage]
        stage_eligible = [s for s in eligible if DOMAIN_TO_STAGE.get(s.meta.domain) == stage]
        stage_blocked = [s for s in blocked if DOMAIN_TO_STAGE.get(s.meta.domain) == stage]

        stage_items = (
            stage_completed[:ITEMS_PER_STAGE]
            + stage_eligible[:ITEMS_PER_STAGE]
            + stage_blocked[:ITEMS_PER_STAGE]
        )
        if not stage_items:
            continue

        for s in stage_items:
            if s.course in covered:
                status = "completed"
            elif s.course == current_course:
                status = "current"
            elif s.missing_prerequisites:
                status = "blocked"
            else:
                status = "upcoming"

            reason_text = explain_recommendation(s)
            if profile.internship_mode and s.course in portfolio_skills and status != "completed":
                reason_text += " It also feeds directly into one of your curated portfolio projects."

            LearningPathItem.objects.create(
                path=path,
                course=s.course,
                stage=stage,
                position=position,
                status=status,
                match_score=s.total,
                reason=reason_text,
            )
            Recommendation.objects.update_or_create(
                profile=profile,
                course=s.course,
                defaults={"score": s.total, "explanation": reason_text},
            )
            position += 1

    PathChangeEvent.objects.create(
        profile=profile,
        previous_version=prev.version if prev else None,
        new_version=path.version,
        reason=reason,
    )

    return path


def get_current_path(profile: LearnerProfile) -> LearningPath | None:
    return profile.paths.filter(is_current=True).prefetch_related("items").first()


def next_best_action(path: LearningPath) -> LearningPathItem | None:
    return path.items.filter(status="current").first()


def readiness_percent(path: LearningPath) -> int:
    items = list(path.items.all())
    if not items:
        return 0
    completed = sum(1 for i in items if i.status == "completed")
    return round(100 * completed / len(items))
