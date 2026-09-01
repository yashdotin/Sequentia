from __future__ import annotations

import csv

from django.conf import settings
from django.db import transaction
from django.db.models import Max

from apps.pathway.models import LearningPath, LearningPathItem, PathChangeEvent
from apps.pathway.services.domain import (
    FOUNDATION_DOMAINS,
    determine_primary_domain,
    relevant_domains,
)
from apps.pathway.services.stack import detect_stack, stack_conflicts
from apps.profiles.models import LearnerProfile
from apps.recommender.models import Recommendation
from apps.recommender.services.explainability import explain_recommendation
from apps.recommender.services.scoring import CourseScore, score_all_courses


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
QUANT_ADJACENT_DOMAINS = {"Machine Learning", "Deep Learning", "Data Analytics", "Data Engineering", "MLOps"}


def _stage_for_domain(domain: str) -> str:
    return "Foundations" if domain in FOUNDATION_DOMAINS else domain


def _ordered_stage_names(primary_domain, relevant, domains_present: set[str]) -> list[str]:
    stages: list[str] = []
    if any(_stage_for_domain(d) == "Foundations" for d in domains_present):
        stages.append("Foundations")

    priority: list[str] = []
    if primary_domain and primary_domain not in FOUNDATION_DOMAINS:
        priority.append(primary_domain)
    if relevant:
        priority.extend(sorted(d for d in relevant if d not in FOUNDATION_DOMAINS and d != primary_domain))
    for d in priority:
        if d in domains_present and d not in stages:
            stages.append(d)


    leftover = sorted(
        d for d in domains_present
        if _stage_for_domain(d) != "Foundations" and d not in stages
    )
    stages.extend(leftover)
    return stages


def _portfolio_relevant_skills() -> set[str]:
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
    # Lock this profile's row for the duration of the transaction so that
    # concurrent calls (double-click, two tabs, a retried request) serialize
    # instead of racing on the version-number read below.
    profile = LearnerProfile.objects.select_for_update().get(pk=profile.pk)

    scores = score_all_courses(profile, query_text)
    covered = _covered_courses(profile)
    by_course: dict[str, CourseScore] = {s.course: s for s in scores}

    primary_domain = determine_primary_domain(profile)
    relevant = relevant_domains(primary_domain)
    explicit_interests = set(profile.interests.values_list("label", flat=True))
    stack = detect_stack(profile)
    wants_math = bool(
        (primary_domain in QUANT_ADJACENT_DOMAINS)
        or (relevant and relevant & QUANT_ADJACENT_DOMAINS)
        or ("Math Foundations" in explicit_interests)
    )

    def in_scope(course_score: CourseScore) -> bool:
        if stack_conflicts(course_score.meta.canonical_skill_ids, stack):
            return False
        domain = course_score.meta.domain
        if domain == "Math Foundations" and not wants_math:
            return False
        if relevant is None:
            return True
        return domain in FOUNDATION_DOMAINS or domain in relevant or domain in explicit_interests

    completed: list[CourseScore] = []
    blocked: list[CourseScore] = []
    eligible: list[CourseScore] = []

    for s in scores:
        if s.course in covered:
            completed.append(s)
        elif not in_scope(s):
            continue
        elif s.missing_prerequisites:
            blocked.append(s)
        else:
            eligible.append(s)

    eligible.sort(key=lambda s: s.total, reverse=True)

    portfolio_skills = _portfolio_relevant_skills() if profile.internship_mode else set()
    if profile.internship_mode:


        eligible.sort(key=lambda s: (round(s.total, 2), s.course in portfolio_skills), reverse=True)

    current_course = eligible[0].course if eligible else None

    prev = profile.paths.filter(is_current=True).first()
    if prev:
        prev.is_current = False
        prev.save(update_fields=["is_current"])

    # Base next_version on the highest version ever used for this profile,
    # not just the current one — a version can exist on disk without being
    # "current" (e.g. a previous attempt that failed validation below and
    # was demoted instead of deleted). Using prev.version + 1 alone lets
    # that orphaned version number collide with a freshly generated one.
    max_version = profile.paths.aggregate(Max("version"))["version__max"] or 0
    next_version = max_version + 1

    path = LearningPath.objects.create(
        profile=profile,
        version=next_version,
        goal_snapshot=profile.goal_text,
        change_reason=reason,
        is_current=True,
    )

    domains_present = {s.meta.domain for s in (completed + eligible + blocked)}
    stage_names = _ordered_stage_names(primary_domain, relevant, domains_present)

    position = 0
    for stage in stage_names:
        if stage == "Foundations":
            stage_completed = [s for s in completed if s.meta.domain in FOUNDATION_DOMAINS]
            stage_eligible = [s for s in eligible if s.meta.domain in FOUNDATION_DOMAINS]
            stage_blocked = [s for s in blocked if s.meta.domain in FOUNDATION_DOMAINS]
        else:
            stage_completed = [s for s in completed if s.meta.domain == stage]
            stage_eligible = [s for s in eligible if s.meta.domain == stage]
            stage_blocked = [s for s in blocked if s.meta.domain == stage]

        stage_items = (
            stage_completed
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

    from apps.pathway.services.path_validator import validate_path
    validation = validate_path(path)

    if not validation.ok:
        if prev:
            prev.is_current = True
            prev.save(update_fields=["is_current"])
            path.delete()
            return prev

        path.is_current = True
        path.save(update_fields=["is_current"])

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
