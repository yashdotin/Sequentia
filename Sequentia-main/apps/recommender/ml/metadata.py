
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .skills import load_skill_vocabulary

VALID_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced"}


@dataclass(frozen=True)
class CourseMeta:
    course: str
    domain: str
    difficulty: str
    resource_type: str
    prerequisites: tuple[str, ...] = field(default_factory=tuple)
    canonical_skill_ids: tuple[str, ...] = field(default_factory=tuple)


class MetadataError(Exception):
    pass


def _parse_prereqs(raw: str) -> tuple[str, ...]:
    raw = (raw or "").strip()
    if not raw:
        return tuple()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


@lru_cache(maxsize=4)
def load_course_metadata(path: str | Path | None = None) -> dict[str, CourseMeta]:
    path = Path(path or settings.COURSE_METADATA_CSV)
    if not path.exists():
        raise MetadataError(f"Course metadata file not found: {path}")

    metadata: dict[str, CourseMeta] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_cols = {
            "course", "domain", "difficulty", "resource_type",
            "prerequisites", "canonical_skill_ids",
        }
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
            skill_ids = tuple(
                s.strip() for s in row["canonical_skill_ids"].split(",") if s.strip()
            )
            if not skill_ids:
                raise MetadataError(f"Course '{course}' has no canonical_skill_ids")
            metadata[course] = CourseMeta(
                course=course,
                domain=row["domain"].strip(),
                difficulty=difficulty,
                resource_type=row["resource_type"].strip() or "course",
                prerequisites=_parse_prereqs(row["prerequisites"]),
                canonical_skill_ids=skill_ids,
            )


    for meta in metadata.values():
        for prereq in meta.prerequisites:
            if prereq not in metadata:
                raise MetadataError(
                    f"Course '{meta.course}' lists unknown prerequisite '{prereq}'"
                )


    known_skills = load_skill_vocabulary()
    for meta in metadata.values():
        for skill_id in meta.canonical_skill_ids:
            if skill_id not in known_skills:
                raise MetadataError(
                    f"Course '{meta.course}' references unknown canonical_skill_id "
                    f"'{skill_id}' — add it to skill_vocabulary_seed.csv first"
                )

    return metadata
