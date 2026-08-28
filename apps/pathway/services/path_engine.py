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
from apps.pathway.services.domain import (
    FOUNDATION_DOMAINS,
    determine_primary_domain,
    relevant_domains,
)
from apps.profiles.models import LearnerProfile
from apps.recommender.models import Recommendation
from apps.recommender.services.explainability import explain_recommendation
from apps.recommender.services.scoring import CourseScore, score_all_courses

# --- Legacy constants -------------------------------------------------
# No longer used by generate_path (see domain.py) — this fixed, universal
# ordering was the actual root cause of the "every path looks ML-shaped"
# bug: it unconditionally walked every learner through a Machine Learning
# and Deep Learning stage regardless of their goal. Kept only in case
# anything external still imports these names.
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


def _stage_for_domain(domain: str) -> str:
    """Foundational domains collapse into one 'Foundations' stage; every
    other domain becomes its own named stage. Replaces the old fixed
    6-stage bucket, so a Web Development path shows stages named
    'Web Development' / 'Cloud' / ... instead of a generic ML-shaped
    'Core Skills' / 'Machine Learning' / 'Deep Learning' pipeline that
    never applied to it in the first place."""
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

    # Anything else present — either the domain is unconstrained (relevant
    # is None), or it's a domain the learner has real history in outside
    # their current target — still gets shown, just after the main sequence,
    # so completed work never silently disappears.
    leftover = sorted(
        d for d in domains_present
        if _stage_for_domain(d) != "Foundations" and d not in stages
    )
    stages.extend(leftover)
    return stages


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
    Scores every course, constrains eligible/blocked candidates to the
    learner's actual target domain (+ legitimate adjacent domains) so a
    Web Development goal doesn't pull in Machine Learning courses just
    because they scored well semantically, buckets what's left into
    per-learner stages, picks exactly one "current" item, and persists the
    result as a new path version. Never mutates an existing version —
    every regeneration is a new row, which is what makes path
    history/versioning possible.
    """
    scores = score_all_courses(profile, query_text)
    covered = _covered_courses(profile)
    by_course: dict[str, CourseScore] = {s.course: s for s in scores}

    primary_domain = determine_primary_domain(profile)
    relevant = relevant_domains(primary_domain)
    explicit_interests = set(profile.interests.values_list("label", flat=True))

    def in_scope(course_score: CourseScore) -> bool:
        if relevant is None:
            return True
        domain = course_score.meta.domain
        return domain in FOUNDATION_DOMAINS or domain in relevant or domain in explicit_interests

    completed: list[CourseScore] = []
    blocked: list[CourseScore] = []
    eligible: list[CourseScore] = []

    for s in scores:
        if s.course in covered:
            completed.append(s)  # history is never domain-filtered — it already happened
        elif not in_scope(s):
            continue  # out-of-domain and not eligible/blocked: don't recommend, don't show as blocked
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

    from apps.pathway.services.path_validator import validate_path
    validation = validate_path(path)

    if not validation.ok:
        # Hard rule (spec-mandated): an invalid path must never be the
        # current one. Structurally this should be near-impossible — the
        # eligibility gating above already enforces prerequisites — so a
        # failure here means something upstream regressed, not a normal
        # runtime condition. Roll back to the previous version rather than
        # silently serving a broken recommendation.
        path.is_current = False
        path.save(update_fields=["is_current"])
        if prev:
            prev.is_current = True
            prev.save(update_fields=["is_current"])
            return prev
        # No previous version to fall back to (this was the very first
        # generation for this learner) — there's nothing valid to serve
        # instead, so this one has to stay current despite the failure.
        # This should only ever happen if the eligibility logic itself has
        # a bug; it is not a normal path for real input.
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
