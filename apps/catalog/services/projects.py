"""
Loads the hand-curated project seed (data/project_seed.csv) — manually
authored the same way course_metadata_seed.csv is, not derived from the
review dataset or any ML process. See that file's docstring for the
reasoning: train.csv has no project-type resources, so this is deliberately
separate, small, and honestly labeled as curated rather than recommended.

`domain` is the real, semantic classification (Web Development, Machine
Learning, ...) — the same 16-value vocabulary used by course metadata and
by apps.pathway.services.domain. `project_type` is a lighter-weight
presentational tag (frontend/backend/fullstack/mobile/devops/...) with no
bearing on unlocking logic; unlocking is skill-based (see
project_recommender.py), never a string match against a path "stage".

`skills` values are exact course names from course_metadata_seed.csv —
using the same string is what makes a project's required skills line up
with LearnerSkillEvidence and course completion. Course names function as
the canonical skill identifier throughout the app; this file doesn't invent
a parallel ID system, it stays consistent with how profiles/pathway/
recommender already treat "skill" everywhere else.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


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
    # Distinct from `skills` (what it demonstrates) — role targeting is
    # deliberately separate from domain, since Web Development contains
    # Frontend/Backend/Full Stack roles that shouldn't get each other's
    # projects just because they share a domain.
    target_roles: tuple[str, ...] = ()
    # Explicitly nullable/unknown rather than fabricated — no real duration
    # data exists for these curated projects.
    estimated_hours: float | None = None


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
            ))
    return projects
