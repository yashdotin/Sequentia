"""Canonical skill/role catalog helpers.

The application keeps the existing course/project CSVs for backward
compatibility, but this layer gives them stable skill and role identities.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True)
class SkillMeta:
    skill_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    domain: str
    description: str
    parent_skill: str | None
    prerequisites: tuple[str, ...]
    related_skills: tuple[str, ...]
    applicable_roles: tuple[str, ...]


@dataclass(frozen=True)
class RoleMeta:
    role_id: str
    role_name: str
    domain: str
    required_skill_ids: tuple[str, ...]


def _split(raw: str, sep: str = "|") -> tuple[str, ...]:
    return tuple(x.strip() for x in (raw or "").split(sep) if x.strip())


def _path(name: str) -> Path:
    return Path(settings.DATA_DIR) / name


@lru_cache(maxsize=4)
def load_skill_catalog(path: str | Path | None = None) -> dict[str, SkillMeta]:
    path = Path(path or getattr(settings, "SKILL_CATALOG_CSV", _path("skill_seed.csv")))
    if not path.exists():
        return {}

    result: dict[str, SkillMeta] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            skill_id = row.get("skill_id", "").strip()
            if not skill_id:
                continue
            result[skill_id] = SkillMeta(
                skill_id=skill_id,
                canonical_name=row.get("canonical_name", skill_id).strip(),
                aliases=_split(row.get("aliases", "")),
                domain=row.get("domain", "").strip(),
                description=row.get("description", "").strip(),
                parent_skill=(row.get("parent_skill") or "").strip() or None,
                prerequisites=_split(row.get("prerequisites", "")),
                related_skills=_split(row.get("related_skills", "")),
                applicable_roles=_split(row.get("applicable_roles", "")),
            )
    return result


@lru_cache(maxsize=4)
def load_role_catalog(path: str | Path | None = None) -> dict[str, RoleMeta]:
    path = Path(path or getattr(settings, "ROLE_CATALOG_CSV", _path("role_seed.csv")))
    if not path.exists():
        return {}

    result: dict[str, RoleMeta] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            role_id = row.get("role_id", "").strip()
            if not role_id:
                continue
            result[role_id] = RoleMeta(
                role_id=role_id,
                role_name=row.get("role_name", role_id).strip(),
                domain=row.get("domain", "").strip(),
                required_skill_ids=_split(row.get("required_skill_ids", "")),
            )
    return result


@lru_cache(maxsize=4)
def load_course_skill_map(path: str | Path | None = None) -> dict[str, tuple[str, ...]]:
    path = Path(path or getattr(settings, "COURSE_SKILL_MAP_CSV", _path("course_skill_map.csv")))
    if not path.exists():
        return {}

    result: dict[str, tuple[str, ...]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            course = row.get("course", "").strip()
            if course:
                result[course] = _split(row.get("skill_ids", ""))
    return result


@lru_cache(maxsize=4)
def _name_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for skill_id, meta in load_skill_catalog().items():
        candidates = {meta.canonical_name, *meta.aliases, skill_id}
        for value in candidates:
            index[value.strip().lower()] = skill_id
    return index


def canonical_skill_ids_for_course(course: str) -> tuple[str, ...]:
    mapped = load_course_skill_map().get(course)
    if mapped:
        return tuple(x for x in mapped if x in load_skill_catalog())
    skill_id = _name_index().get((course or "").strip().lower())
    return (skill_id,) if skill_id else tuple()


def resolve_skill_ids(value: str) -> tuple[str, ...]:
    """Resolve a learner/profile skill string to canonical IDs."""
    text = (value or "").strip()
    if not text:
        return tuple()
    direct = canonical_skill_ids_for_course(text)
    if direct:
        return direct
    found = _name_index().get(text.lower())
    return (found,) if found else tuple()


def skill_display(skill_id: str) -> str:
    meta = load_skill_catalog().get(skill_id)
    return meta.canonical_name if meta else skill_id
