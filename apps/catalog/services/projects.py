
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from apps.recommender.ml.metadata import load_course_metadata
from apps.recommender.ml.skills import Skill, load_skill_vocabulary


@dataclass(frozen=True)
class ProjectMeta:
    slug: str
    title: str
    domain: str
    difficulty: str
    skills: tuple[str, ...]
    description: str
    portfolio_value: str
    project_type: str = ""


    target_roles: tuple[str, ...] = ()


    estimated_hours: float | None = None

    prerequisite_skill_ids: tuple[str, ...] = field(default_factory=tuple)
    demonstrates_skill_ids: tuple[str, ...] = field(default_factory=tuple)


def _skill_ancestors(skill_id: str, skills: dict[str, Skill], seen: set[str] | None = None) -> set[str]:
    seen = seen if seen is not None else set()
    skill = skills.get(skill_id)
    if skill is None:
        return seen
    for dep in skill.all_prerequisites():
        if dep not in seen:
            seen.add(dep)
            _skill_ancestors(dep, skills, seen)
    return seen


@lru_cache(maxsize=256)
def _skill_derivations_for_project(course_names: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    courses = load_course_metadata()
    skills = load_skill_vocabulary()

    demonstrates: set[str] = set()
    for name in course_names:
        meta = courses.get(name)
        if meta:
            demonstrates.update(meta.canonical_skill_ids)

    ancestors: set[str] = set()
    for skill_id in demonstrates:
        ancestors |= _skill_ancestors(skill_id, skills)
    prerequisites = ancestors - demonstrates

    return tuple(sorted(demonstrates)), tuple(sorted(prerequisites))


def load_project_seed(path: str | Path | None = None) -> list[ProjectMeta]:
    path = Path(path or settings.PROJECT_SEED_CSV)
    if not path.exists():
        return []

    projects = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skills = tuple(s.strip() for s in row["skills"].split(",") if s.strip())
            roles = tuple(r.strip() for r in row.get("target_roles", "").split(";") if r.strip())
            demonstrates_ids, prerequisite_ids = _skill_derivations_for_project(skills)
            projects.append(ProjectMeta(
                slug=row["slug"].strip(),
                title=row["title"].strip(),
                domain=row["domain"].strip(),
                difficulty=row["difficulty"].strip(),
                skills=skills,
                description=row["description"].strip(),
                portfolio_value=row["portfolio_value"].strip(),
                project_type=row.get("project_type", "").strip(),
                target_roles=roles,
                prerequisite_skill_ids=prerequisite_ids,
                demonstrates_skill_ids=demonstrates_ids,
            ))
    return projects
