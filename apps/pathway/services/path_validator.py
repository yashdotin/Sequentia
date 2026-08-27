"""
Real-data regression checks against a freshly generated path.

generate_path() already enforces prerequisites as a hard constraint (blocked
items are never marked current/upcoming) and now domain-scoping via
domain.py — this module exists to *verify* those guarantees held, both as a
runtime safety net (validate_path() is called right after generation; a
critical failure is logged loudly since it means the eligibility logic
itself has a bug) and as the thing the automated multi-domain tests assert
against directly.

This is deliberately validate-then-log rather than a reject-and-regenerate
loop: generate_path's eligibility gating already makes most of these
violations structurally impossible, so a validator failure here is a signal
that the *generation logic itself* regressed, not routine input to route
around.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from apps.pathway.models import LearningPath
from apps.pathway.services.domain import FOUNDATION_DOMAINS, determine_primary_domain, relevant_domains
from apps.recommender.ml.metadata import load_course_metadata

logger = logging.getLogger("sequentia.path_validator")


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_prerequisites(path: LearningPath, result: ValidationResult) -> None:
    """Hard constraint: an item marked current/upcoming must have every
    prerequisite satisfied by the *same* evidence signal generate_path
    actually used (LearnerSkillEvidence 'known'/'inferred', per
    scoring._skill_evidence_map — not course-completion history, which is a
    different, stricter thing generate_path never required)."""
    metadata = load_course_metadata()
    evidence = {e.skill: e.evidence_level for e in path.profile.skills.all()}
    # A course completed *within this same path* also counts, same as generate_path.
    completed_in_path = {i.course for i in path.items.all() if i.status == "completed"}

    def satisfied(prereq: str) -> bool:
        return evidence.get(prereq) in ("known", "inferred") or prereq in completed_in_path

    for item in path.items.exclude(status__in=("completed", "blocked")):
        meta = metadata.get(item.course)
        if not meta:
            continue
        missing = [p for p in meta.prerequisites if not satisfied(p)]
        if missing:
            result.add_error(
                f'"{item.course}" is marked {item.status} but is missing prerequisites: {missing}'
            )


def validate_sequence(path: LearningPath, result: ValidationResult) -> None:
    """At most one item should ever be 'current' — the single next action."""
    current_count = path.items.filter(status="current").count()
    if current_count > 1:
        result.add_error(f"{current_count} items marked 'current'; expected at most 1")


def validate_domain_relevance(path: LearningPath, result: ValidationResult) -> None:
    """A recommended (non-completed, non-blocked) item's domain should be
    the primary domain, a foundation domain, an adjacency-approved
    supporting domain, or a domain the learner explicitly said they're
    interested in. Anything else is contamination."""
    metadata = load_course_metadata()
    primary = determine_primary_domain(path.profile)
    relevant = relevant_domains(primary)
    if relevant is None:
        return  # domain genuinely undetermined — nothing to contaminate against
    explicit_interests = set(path.profile.interests.values_list("label", flat=True))

    for item in path.items.filter(status__in=("current", "upcoming")):
        meta = metadata.get(item.course)
        if not meta:
            continue
        if meta.domain in FOUNDATION_DOMAINS or meta.domain in relevant or meta.domain in explicit_interests:
            continue
        result.add_error(
            f'"{item.course}" (domain: {meta.domain}) is recommended but outside the '
            f"relevant domain set for primary domain \"{primary}\": {sorted(relevant)}"
        )


def validate_duplicate_courses(path: LearningPath, result: ValidationResult) -> None:
    courses = [i.course for i in path.items.all()]
    seen = set()
    for c in courses:
        if c in seen:
            result.add_error(f'"{c}" appears more than once in the same path')
        seen.add(c)


def validate_completed_skill_exclusion(path: LearningPath, result: ValidationResult) -> None:
    """A course the learner has already completed (history) should never be
    recommended again as current/upcoming in a new path."""
    history_courses = set(path.profile.history.filter(status="completed").values_list("course", flat=True))
    for item in path.items.filter(status__in=("current", "upcoming")):
        if item.course in history_courses:
            result.add_error(f'"{item.course}" is already completed in history but recommended again')


def validate_status(path: LearningPath, result: ValidationResult) -> None:
    valid_statuses = {"completed", "current", "upcoming", "blocked"}
    for item in path.items.all():
        if item.status not in valid_statuses:
            result.add_error(f'"{item.course}" has invalid status "{item.status}"')


VALIDATORS = [
    validate_prerequisites,
    validate_sequence,
    validate_domain_relevance,
    validate_duplicate_courses,
    validate_completed_skill_exclusion,
    validate_status,
]


def validate_path(path: LearningPath) -> ValidationResult:
    result = ValidationResult()
    for validator in VALIDATORS:
        validator(path, result)

    if not result.ok:
        logger.error(
            "Path validation failed for profile=%s path_id=%s version=%s: %s",
            path.profile_id, path.id, path.version, result.errors,
        )
    for w in result.warnings:
        logger.warning("Path validation warning for path_id=%s: %s", path.id, w)

    return result
