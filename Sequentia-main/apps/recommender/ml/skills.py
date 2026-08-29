
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True)
class Skill:
    skill_id: str
    canonical_name: str
    domain: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    parent_skill: str = ""
    prerequisite_skill_ids: tuple[str, ...] = field(default_factory=tuple)
    applicable_roles: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    def all_prerequisites(self) -> tuple[str, ...]:
        prereqs = list(self.prerequisite_skill_ids)
        if self.parent_skill and self.parent_skill not in prereqs:
            prereqs.append(self.parent_skill)
        return tuple(prereqs)


class SkillVocabularyError(Exception):
    pass


def _parse_list(raw: str) -> tuple[str, ...]:
    raw = (raw or "").strip()
    if not raw:
        return tuple()
    return tuple(p.strip() for p in raw.split(";") if p.strip())


@lru_cache(maxsize=4)
def load_skill_vocabulary(path: str | Path | None = None) -> dict[str, Skill]:
    path = Path(path or settings.SKILL_VOCABULARY_CSV)
    if not path.exists():
        raise SkillVocabularyError(f"Skill vocabulary file not found: {path}")

    skills: dict[str, Skill] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_cols = {
            "skill_id", "canonical_name", "domain", "aliases",
            "parent_skill", "prerequisite_skill_ids", "applicable_roles", "description",
        }
        missing_cols = required_cols - set(reader.fieldnames or [])
        if missing_cols:
            raise SkillVocabularyError(f"Skill vocabulary CSV missing columns: {missing_cols}")

        for row in reader:
            skill_id = row["skill_id"].strip()
            if not skill_id:
                continue
            if skill_id in skills:
                raise SkillVocabularyError(f"Duplicate skill_id '{skill_id}'")
            skills[skill_id] = Skill(
                skill_id=skill_id,
                canonical_name=row["canonical_name"].strip(),
                domain=row["domain"].strip(),
                aliases=_parse_list(row["aliases"]),
                parent_skill=row["parent_skill"].strip(),
                prerequisite_skill_ids=_parse_list(row["prerequisite_skill_ids"]),
                applicable_roles=_parse_list(row["applicable_roles"]),
                description=row["description"].strip(),
            )

    _validate_references(skills)
    _validate_acyclic(skills)
    return skills


def _validate_references(skills: dict[str, Skill]) -> None:
    for skill in skills.values():
        if skill.parent_skill and skill.parent_skill not in skills:
            raise SkillVocabularyError(
                f"Skill '{skill.skill_id}' has unknown parent_skill '{skill.parent_skill}'"
            )
        for prereq in skill.prerequisite_skill_ids:
            if prereq not in skills:
                raise SkillVocabularyError(
                    f"Skill '{skill.skill_id}' lists unknown prerequisite '{prereq}'"
                )
        if not skill.applicable_roles:
            raise SkillVocabularyError(
                f"Skill '{skill.skill_id}' has no applicable_roles — every skill must map "
                f"to at least one role (see section 15, 'orphan skills')"
            )


def _validate_acyclic(skills: dict[str, Skill]) -> None:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {skill_id: WHITE for skill_id in skills}

    def visit(skill_id: str, path: list[str]) -> None:
        color[skill_id] = GRAY
        for dep in skills[skill_id].all_prerequisites():
            if color[dep] == GRAY:
                cycle = " -> ".join(path + [skill_id, dep])
                raise SkillVocabularyError(f"Dependency cycle detected: {cycle}")
            if color[dep] == WHITE:
                visit(dep, path + [skill_id])
        color[skill_id] = BLACK

    for skill_id in skills:
        if color[skill_id] == WHITE:
            visit(skill_id, [])


def resolve_alias(name: str, skills: dict[str, Skill] | None = None) -> str | None:
    skills = skills if skills is not None else load_skill_vocabulary()
    name_lower = name.strip().lower()
    for skill in skills.values():
        if skill.skill_id.lower() == name_lower or skill.canonical_name.lower() == name_lower:
            return skill.skill_id
        if any(alias.lower() == name_lower for alias in skill.aliases):
            return skill.skill_id
    return None
