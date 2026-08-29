"""Loads course metadata plus canonical skill/role relationships.

The original five-column CSV contract remains supported for tests and backward
compatibility. When canonical catalog files are present, the loader enriches
CourseMeta with stable skill IDs, prerequisite skill IDs, and target roles.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .canonical import canonical_skill_ids_for_course, load_skill_catalog

VALID_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced"}


@dataclass(frozen=True)
class CourseMeta:
    course: str
    domain: str
    difficulty: str
    resource_type: str
    prerequisites: tuple[str, ...] = field(default_factory=tuple)
    canonical_skill_ids: tuple[str, ...] = field(default_factory=tuple)
    prerequisite_skill_ids: tuple[str, ...] = field(default_factory=tuple)
    target_roles: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""
    estimated_hours: float | None = None
    learning_outcomes: tuple[str, ...] = field(default_factory=tuple)


class MetadataError(Exception):
    """Raised when the seed file is malformed or inconsistent."""


def _parse_prereqs(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in (raw or "").split(",") if p.strip())


def _parse_ids(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in (raw or "").split("|") if p.strip())


def _course_to_roles(skill_ids: tuple[str, ...]) -> tuple[str, ...]:
    role_names: set[str] = set()
    skills = load_skill_catalog()
    for skill_id in skill_ids:
        meta = skills.get(skill_id)
        if meta:
            role_names.update(meta.applicable_roles)
    return tuple(sorted(role_names))


def _course_to_prerequisite_skills(
    prerequisites: tuple[str, ...], course_skill_map: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    ids: list[str] = []
    for course in prerequisites:
        ids.extend(course_skill_map.get(course, canonical_skill_ids_for_course(course)))
    return tuple(dict.fromkeys(ids))


@lru_cache(maxsize=4)
def load_course_metadata(path: str | Path | None = None) -> dict[str, CourseMeta]:
    path = Path(path or settings.COURSE_METADATA_CSV)
    if not path.exists():
        raise MetadataError(f"Course metadata file not found: {path}")

    metadata: dict[str, CourseMeta] = {}
    raw_rows: list[dict[str, str]] = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_cols = {"course", "domain", "difficulty", "resource_type", "prerequisites"}
        missing_cols = required_cols - set(reader.fieldnames or [])
        if missing_cols:
            raise MetadataError(f"Seed CSV missing columns: {missing_cols}")

        for row in reader:
            course = row["course"].strip()
            difficulty = row["difficulty"].strip()
            if difficulty not in VALID_DIFFICULTIES:
                raise MetadataError(
                    f"Course '{course}' has invalid difficulty '{difficulty}' "
                    f"(expected one of {VALID_DIFFICULTIES})"
                )
            raw_rows.append(row)

    course_skill_map_path = Path(settings.DATA_DIR) / "course_skill_map.csv"
    course_skill_map: dict[str, tuple[str, ...]] = {}
    if course_skill_map_path.exists():
        with course_skill_map_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                course_skill_map[row.get("course", "").strip()] = _parse_ids(row.get("skill_ids", ""))

    for row in raw_rows:
        course = row["course"].strip()
        prerequisites = _parse_prereqs(row["prerequisites"])
        canonical_ids = _parse_ids(row.get("canonical_skill_ids", "")) or canonical_skill_ids_for_course(course)
        canonical_ids = tuple(x for x in canonical_ids if x in load_skill_catalog())
        prereq_ids = _parse_ids(row.get("prerequisite_skill_ids", "")) or _course_to_prerequisite_skills(prerequisites, course_skill_map)
        target_roles = _parse_ids(row.get("target_roles", "")) or _course_to_roles(canonical_ids)

        hours_raw = (row.get("estimated_hours") or "").strip()
        try:
            hours = float(hours_raw) if hours_raw else None
        except ValueError:
            hours = None

        outcomes = _split_outcomes(row.get("learning_outcomes", ""))
        metadata[course] = CourseMeta(
            course=course,
            domain=row["domain"].strip(),
            difficulty=row["difficulty"].strip(),
            resource_type=row["resource_type"].strip() or "course",
            prerequisites=prerequisites,
            canonical_skill_ids=canonical_ids,
            prerequisite_skill_ids=prereq_ids,
            target_roles=target_roles,
            description=(row.get("description") or "").strip(),
            estimated_hours=hours,
            learning_outcomes=outcomes,
        )

    # Legacy prerequisite validation remains intact.
    for meta in metadata.values():
        for prereq in meta.prerequisites:
            if prereq not in metadata:
                raise MetadataError(
                    f"Course '{meta.course}' lists unknown prerequisite '{prereq}'"
                )

    # Canonical references must be valid when the catalog exists.
    known = set(load_skill_catalog())
    if known:
        for meta in metadata.values():
            unknown = set(meta.canonical_skill_ids) | set(meta.prerequisite_skill_ids)
            bad = sorted(x for x in unknown if x not in known)
            if bad:
                raise MetadataError(f"Course '{meta.course}' references unknown canonical skill(s): {bad}")

    return metadata


def _split_outcomes(raw: str) -> tuple[str, ...]:
    raw = (raw or "").strip()
    if not raw:
        return tuple()
    return tuple(x.strip() for x in raw.split("|") if x.strip())
