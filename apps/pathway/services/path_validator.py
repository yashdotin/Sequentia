
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
    metadata = load_course_metadata()
    evidence = {e.skill: e.evidence_level for e in path.profile.skills.all()}

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
    current_count = path.items.filter(status="current").count()
    if current_count > 1:
        result.add_error(f"{current_count} items marked 'current'; expected at most 1")


def validate_domain_relevance(path: LearningPath, result: ValidationResult) -> None:
    metadata = load_course_metadata()
    primary = determine_primary_domain(path.profile)
    relevant = relevant_domains(primary)
    if relevant is None:
        return
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
