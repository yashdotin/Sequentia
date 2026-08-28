"""
Loads the hand-curated course metadata seed (domain / difficulty / prerequisites).

train.csv has no such columns — this file is the only source of truth for them,
and it was manually curated by the project owner, not inferred by the model.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings

VALID_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced"}


@dataclass(frozen=True)
class CourseMeta:
    course: str
    domain: str
    difficulty: str
    resource_type: str
    prerequisites: tuple[str, ...] = field(default_factory=tuple)


class MetadataError(Exception):
    """Raised when the seed file is malformed or inconsistent with train.csv."""


def _parse_prereqs(raw: str) -> tuple[str, ...]:
    raw = (raw or "").strip()
    if not raw:
        return tuple()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


@lru_cache(maxsize=4)
def load_course_metadata(path: str | Path | None = None) -> dict[str, CourseMeta]:
    """
    Returns {course_name: CourseMeta}. Raises MetadataError on malformed rows
    rather than silently guessing — a bad prerequisite reference should fail
    loudly at startup, not corrupt path generation later.
    """
    path = Path(path or settings.COURSE_METADATA_CSV)
    if not path.exists():
        raise MetadataError(f"Course metadata file not found: {path}")

    metadata: dict[str, CourseMeta] = {}
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
            metadata[course] = CourseMeta(
                course=course,
                domain=row["domain"].strip(),
                difficulty=difficulty,
                resource_type=row["resource_type"].strip() or "course",
                prerequisites=_parse_prereqs(row["prerequisites"]),
            )

    # Every prerequisite must itself be a known course — catches typos early.
    for meta in metadata.values():
        for prereq in meta.prerequisites:
            if prereq not in metadata:
                raise MetadataError(
                    f"Course '{meta.course}' lists unknown prerequisite '{prereq}'"
                )

    return metadata
