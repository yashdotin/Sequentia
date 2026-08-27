"""
Loads the hand-curated project seed (data/project_seed.csv) — manually
authored the same way course_metadata_seed.csv is, not derived from the
review dataset or any ML process. See that file's docstring for the
reasoning: train.csv has no project-type resources, so this is deliberately
separate, small, and honestly labeled as curated rather than recommended.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True)
class ProjectMeta:
    slug: str
    title: str
    stage: str
    difficulty: str
    skills: tuple[str, ...]
    description: str
    portfolio_value: str


def load_project_seed(path: str | Path | None = None) -> list[ProjectMeta]:
    path = Path(path or settings.PROJECT_SEED_CSV)
    if not path.exists():
        return []

    projects = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skills = tuple(s.strip() for s in row["skills"].split(",") if s.strip())
            projects.append(ProjectMeta(
                slug=row["slug"].strip(),
                title=row["title"].strip(),
                stage=row["stage"].strip(),
                difficulty=row["difficulty"].strip(),
                skills=skills,
                description=row["description"].strip(),
                portfolio_value=row["portfolio_value"].strip(),
            ))
    return projects
