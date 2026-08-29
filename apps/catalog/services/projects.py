"""Project catalog loader with canonical-skill compatibility.

The CSV keeps the legacy ``skills`` column for UI/tests, while the new
canonical fields drive readiness and portfolio evidence:
required_skill_ids, prerequisite_skill_ids, demonstrates_skill_ids, and
compatible_stack_ids.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.conf import settings

from apps.recommender.ml.canonical import load_skill_catalog, skill_display


def _split(raw: str, sep: str = "|") -> tuple[str, ...]:
    return tuple(x.strip() for x in (raw or "").split(sep) if x.strip())


def _legacy_split(raw: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in (raw or "").split(",") if x.strip())


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
    required_skill_ids: tuple[str, ...] = ()
    prerequisite_skill_ids: tuple[str, ...] = ()
    demonstrates_skill_ids: tuple[str, ...] = ()
    compatible_stack_ids: tuple[str, ...] = ()
    learning_outcomes: tuple[str, ...] = ()

    @property
    def demonstrated_skill_names(self) -> tuple[str, ...]:
        catalog = load_skill_catalog()
        return tuple(catalog[s].canonical_name if s in catalog else s for s in self.demonstrates_skill_ids)

    @property
    def prerequisite_skill_names(self) -> tuple[str, ...]:
        catalog = load_skill_catalog()
        return tuple(catalog[s].canonical_name if s in catalog else s for s in self.prerequisite_skill_ids)


def _infer_skill_ids_from_legacy(legacy_skills: Iterable[str]) -> tuple[str, ...]:
    # Lazy import avoids making the catalog loader depend on project parsing.
    from apps.recommender.ml.canonical import canonical_skill_ids_for_course
    ids=[]
    for value in legacy_skills:
        ids.extend(canonical_skill_ids_for_course(value))
    return tuple(dict.fromkeys(ids))


def load_project_seed(path: str | Path | None = None) -> list[ProjectMeta]:
    path = Path(path or settings.PROJECT_SEED_CSV)
    if not path.exists():
        return []

    projects=[]
    with path.open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        for row in reader:
            legacy=_legacy_split(row.get("skills", ""))
            inferred=_infer_skill_ids_from_legacy(legacy)
            required=_split(row.get("required_skill_ids", "")) or inferred
            prereqs=_split(row.get("prerequisite_skill_ids", "")) or required
            demos=_split(row.get("demonstrates_skill_ids", "")) or required
            stack=_split(row.get("compatible_stack_ids", ""))
            hours_raw=(row.get("estimated_hours") or "").strip()
            try: hours=float(hours_raw) if hours_raw else None
            except ValueError: hours=None
            outcomes=_split(row.get("learning_outcomes", ""), ";") if row.get("learning_outcomes") else ()
            projects.append(ProjectMeta(
                slug=row.get("slug", "").strip(),
                title=row.get("title", "").strip(),
                domain=row.get("domain", "").strip(),
                difficulty=row.get("difficulty", "").strip(),
                skills=legacy,
                description=row.get("description", "").strip(),
                portfolio_value=row.get("portfolio_value", "").strip(),
                project_type=row.get("project_type", "").strip(),
                target_roles=tuple(x.strip() for x in row.get("target_roles", "").split(";") if x.strip()),
                estimated_hours=hours,
                required_skill_ids=required,
                prerequisite_skill_ids=prereqs,
                demonstrates_skill_ids=demos,
                compatible_stack_ids=stack,
                learning_outcomes=outcomes,
            ))
    return projects
