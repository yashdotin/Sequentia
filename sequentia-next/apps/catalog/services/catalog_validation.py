"""Data-only catalog validation for the canonical Sequentia layer."""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from apps.catalog.services.projects import load_project_seed
from apps.recommender.ml.canonical import load_course_skill_map, load_role_catalog, load_skill_catalog
from apps.recommender.ml.metadata import load_course_metadata


@dataclass
class CatalogValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _find_cycles(skills) -> list[str]:
    graph = {sid: set(meta.prerequisites) for sid, meta in skills.items()}
    visiting, visited, cycles = set(), set(), []

    def dfs(node, path):
        if node in visiting:
            idx = path.index(node) if node in path else 0
            cycles.append(" -> ".join(path[idx:] + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, set()):
            if dep in graph:
                dfs(dep, path + [dep])
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        if node not in visited:
            dfs(node, [node])
    return cycles


def _domains_from_course_seed() -> set[str]:
    path = Path(settings.COURSE_METADATA_CSV)
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return {r.get("domain", "").strip() for r in csv.DictReader(handle) if r.get("domain", "").strip()}


def validate_catalog() -> CatalogValidationResult:
    result = CatalogValidationResult()
    skills = load_skill_catalog()
    roles = load_role_catalog()
    course_skill_map = load_course_skill_map()

    if not skills:
        result.error("data/skill_seed.csv is missing or contains no canonical skills")
    if not roles:
        result.error("data/role_seed.csv is missing or contains no supported roles")
    if not course_skill_map:
        result.error("data/course_skill_map.csv is missing or contains no course mappings")

    try:
        metadata = load_course_metadata()
    except Exception as exc:
        result.error(f"Unable to load course metadata: {exc}")
        metadata = {}

    try:
        projects = load_project_seed()
    except Exception as exc:
        result.error(f"Unable to load projects: {exc}")
        projects = []

    known_skill_ids = set(skills)
    known_role_names = {m.role_name.lower() for m in roles.values()}
    resources_by_skill = defaultdict(int)
    projects_by_skill = defaultdict(int)

    for sid, meta in skills.items():
        for dep in meta.prerequisites:
            if dep not in known_skill_ids:
                result.error(f"Skill {sid} references unknown prerequisite {dep}")
        for rel in meta.related_skills:
            if rel not in known_skill_ids:
                result.error(f"Skill {sid} references unknown related skill {rel}")
        if meta.parent_skill and meta.parent_skill not in known_skill_ids:
            result.error(f"Skill {sid} references unknown parent skill {meta.parent_skill}")
        for role in meta.applicable_roles:
            if role.lower() not in known_role_names:
                result.error(f"Skill {sid} references unsupported role {role}")

    for cycle in _find_cycles(skills):
        result.error(f"Skill dependency cycle: {cycle}")

    for role in roles.values():
        for sid in role.required_skill_ids:
            if sid not in known_skill_ids:
                result.error(f"Role {role.role_name} references unknown skill {sid}")

    for course, meta in metadata.items():
        ids = meta.canonical_skill_ids
        if not ids:
            result.error(f"Resource '{course}' has no canonical skill mapping")
        for sid in ids:
            if sid not in known_skill_ids:
                result.error(f"Resource '{course}' references unknown skill {sid}")
            else:
                resources_by_skill[sid] += 1
        for sid in meta.prerequisite_skill_ids:
            if sid not in known_skill_ids:
                result.error(f"Resource '{course}' has unknown prerequisite skill {sid}")
        for role in meta.target_roles:
            if role.lower() not in known_role_names:
                result.error(f"Resource '{course}' references unsupported role {role}")

    project_roles = defaultdict(int)
    for project in projects:
        project_skill_ids = set()
        for skill_name in project.skills:
            for sid in course_skill_map.get(skill_name, ()):
                project_skill_ids.add(sid)
        if not project_skill_ids:
            result.error(f"Project '{project.slug}' cannot resolve any canonical skills")
        for sid in project_skill_ids:
            projects_by_skill[sid] += 1
        for role in project.target_roles:
            project_roles[role.lower()] += 1
            if role.lower() not in known_role_names:
                result.error(f"Project '{project.slug}' references unsupported role {role}")

    for sid in sorted(known_skill_ids):
        if resources_by_skill[sid] == 0:
            result.warnings.append(f"Orphan skill: {sid} has no resource")
        if projects_by_skill[sid] == 0:
            result.warnings.append(f"Skill {sid} has no project relationship")

    for role in roles.values():
        matching_resources = sum(1 for m in metadata.values() if role.role_name.lower() in {x.lower() for x in m.target_roles})
        matching_projects = project_roles[role.role_name.lower()]
        if matching_resources == 0:
            result.warnings.append(f"Role {role.role_name} has no explicitly tagged resources")
        if matching_projects == 0:
            result.warnings.append(f"Role {role.role_name} has no project coverage yet")

    result.metrics = {
        "canonical_skills": len(skills),
        "resources": len(metadata),
        "projects": len(projects),
        "supported_roles": len(roles),
        "domains": len(_domains_from_course_seed()),
        "dependency_cycles": len(_find_cycles(skills)),
        "course_role_mappings": sum(bool(m.target_roles) for m in metadata.values()),
        "project_role_mappings": sum(len(p.target_roles) for p in projects),
    }
    return result
