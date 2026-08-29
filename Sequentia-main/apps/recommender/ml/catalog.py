"""Canonical catalog vocabulary for Sequentia.

This layer keeps the old application string fields compatible while making
canonical skill IDs the internal identity used by recommendation logic.
The CSV files are intentionally plain and hand-curated so the vocabulary is
inspectable and easy to correct.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
import re

from django.conf import settings


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower()).strip()


def _split(value: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in (value or "").split("|") if x.strip())


class CatalogError(Exception):
    pass


@lru_cache(maxsize=4)
def load_skill_catalog(path: str | Path | None = None) -> dict[str, dict]:
    path = Path(path or settings.DATA_DIR / "skill_seed.csv")
    if not path.exists():
        raise CatalogError(f"Skill catalog not found: {path}")
    rows: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"skill_id", "canonical_name", "aliases", "domain", "prerequisites", "related_skills", "applicable_roles"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise CatalogError(f"skill_seed.csv missing columns: {sorted(missing)}")
        for row in reader:
            sid = row["skill_id"].strip()
            if not sid or sid in rows:
                raise CatalogError(f"Duplicate/empty skill_id: {sid!r}")
            rows[sid] = {
                "skill_id": sid,
                "canonical_name": row["canonical_name"].strip(),
                "aliases": _split(row.get("aliases", "")),
                "domain": row["domain"].strip(),
                "description": row.get("description", "").strip(),
                "parent_skill": row.get("parent_skill", "").strip(),
                "prerequisites": _split(row.get("prerequisites", "")),
                "related_skills": _split(row.get("related_skills", "")),
                "applicable_roles": _split(row.get("applicable_roles", "")),
            }
        for sid, row in rows.items():
            candidates = (row["canonical_name"], sid, *row["aliases"])
            for candidate in candidates:
                key = _norm(candidate)
                if not key:
                    continue
                existing = aliases.get(key)
                if existing and existing != sid:
                    raise CatalogError(f"Alias collision: {candidate!r} maps to both {existing} and {sid}")
                aliases[key] = sid
        for sid, row in rows.items():
            for prereq in row["prerequisites"]:
                if prereq not in rows:
                    raise CatalogError(f"Skill {sid} has unknown prerequisite {prereq}")
            if row["parent_skill"] and row["parent_skill"] not in rows:
                raise CatalogError(f"Skill {sid} has unknown parent_skill {row['parent_skill']}")
    rows["__aliases__"] = aliases
    return rows


def canonical_skill_id(value: str | None) -> str | None:
    if not value:
        return None
    catalog = load_skill_catalog()
    return catalog.get("__aliases__", {}).get(_norm(value))


def canonical_skill_name(value: str | None) -> str | None:
    sid = canonical_skill_id(value)
    if not sid:
        return None
    return load_skill_catalog()[sid]["canonical_name"]


def skill_display(value: str) -> str:
    return canonical_skill_name(value) or value


def skills_for_course(meta) -> tuple[str, ...]:
    return tuple(meta.canonical_skill_ids)


def course_for_skill(skill_id: str, metadata: dict) -> list[str]:
    return [m.course for m in metadata.values() if skill_id in m.canonical_skill_ids]
