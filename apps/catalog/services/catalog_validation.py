
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from apps.catalog.services.projects import ProjectMeta, load_project_seed
from apps.recommender.ml.metadata import CourseMeta, load_course_metadata
from apps.recommender.ml.skills import Skill, load_skill_vocabulary

MIN_PROJECTS_PER_ROLE = 10
MIN_COURSES_PER_DOMAIN = 3


@dataclass
class ValidationReport:
    skill_count: int = 0
    course_count: int = 0
    project_count: int = 0
    role_count: int = 0
    domain_count: int = 0

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


    orphan_skills_no_course: list[str] = field(default_factory=list)
    orphan_skills_no_project: list[str] = field(default_factory=list)
    thin_roles: dict[str, int] = field(default_factory=dict)
    thin_domains: dict[str, int] = field(default_factory=dict)
    projects_per_role: dict[str, int] = field(default_factory=dict)


    projects_with_distinct_prerequisites: int = 0


    courses_without_review_data: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_validation() -> ValidationReport:
    report = ValidationReport()

    skills = load_skill_vocabulary()
    courses = load_course_metadata()
    projects = load_project_seed()

    report.skill_count = len(skills)
    report.course_count = len(courses)
    report.project_count = len(projects)

    known_roles = _known_roles(skills)
    known_domains = {s.domain for s in skills.values()}
    report.role_count = len(known_roles)
    report.domain_count = len(known_domains)

    _check_orphan_skills(skills, courses, projects, report)
    _check_project_integrity(projects, courses, known_roles, report)
    _check_duplicate_slugs(projects, report)
    _check_coverage(skills, courses, projects, known_roles, report)

    report.projects_with_distinct_prerequisites = sum(
        1 for p in projects if set(p.prerequisite_skill_ids) - set(p.demonstrates_skill_ids)
    )

    try:
        from apps.recommender.ml.loader import courses_without_review_data
        no_reviews = sorted(courses_without_review_data())
        report.courses_without_review_data = no_reviews
        if no_reviews:
            report.warnings.append(
                f"{len(no_reviews)} course(s) have no train.csv review data yet, so they "
                f"won't appear in semantic course scoring (see courses_without_review_data)"
            )
    except Exception as exc:
        report.errors.append(f"Could not check review-data coverage: {exc}")

    return report


def _known_roles(skills: dict[str, Skill]) -> set[str]:
    roles: set[str] = set()
    for skill in skills.values():
        roles.update(skill.applicable_roles)
    return roles


def _check_orphan_skills(
    skills: dict[str, Skill],
    courses: dict[str, CourseMeta],
    projects: list[ProjectMeta],
    report: ValidationReport,
) -> None:
    skills_with_courses: set[str] = set()
    for course in courses.values():
        skills_with_courses.update(course.canonical_skill_ids)

    for skill_id in skills:
        if skill_id not in skills_with_courses:
            report.orphan_skills_no_course.append(skill_id)

    if report.orphan_skills_no_course:
        report.errors.append(
            f"{len(report.orphan_skills_no_course)} skill(s) have no course teaching them: "
            f"{', '.join(sorted(report.orphan_skills_no_course))}"
        )


    course_to_skills = {name: meta.canonical_skill_ids for name, meta in courses.items()}
    skills_with_projects: set[str] = set()
    for project in projects:
        for course_name in project.skills:
            skills_with_projects.update(course_to_skills.get(course_name, ()))

    for skill_id in skills:
        if skill_id not in skills_with_projects:
            report.orphan_skills_no_project.append(skill_id)

    if report.orphan_skills_no_project:
        report.warnings.append(
            f"{len(report.orphan_skills_no_project)} skill(s) are taught but never "
            f"required/demonstrated by any project (see section 15)"
        )


def _check_project_integrity(
    projects: list[ProjectMeta],
    courses: dict[str, CourseMeta],
    known_roles: set[str],
    report: ValidationReport,
) -> None:
    for project in projects:
        for course_name in project.skills:
            if course_name not in courses:
                report.errors.append(
                    f"Project '{project.slug}' references unknown course '{course_name}'"
                )
        for role in project.target_roles:
            if role not in known_roles:
                report.errors.append(
                    f"Project '{project.slug}' targets role '{role}' with no skill "
                    f"in the vocabulary mapped to it — not a valid role (section 17)"
                )
        if not project.target_roles:
            report.errors.append(f"Project '{project.slug}' has no target_roles")
        if not project.skills:
            report.errors.append(f"Project '{project.slug}' has no required skills")


def _check_duplicate_slugs(projects: list[ProjectMeta], report: ValidationReport) -> None:
    seen = Counter(p.slug for p in projects)
    for slug, count in seen.items():
        if count > 1:
            report.errors.append(f"Duplicate project slug '{slug}' ({count} occurrences)")


def _check_coverage(
    skills: dict[str, Skill],
    courses: dict[str, CourseMeta],
    projects: list[ProjectMeta],
    known_roles: set[str],
    report: ValidationReport,
) -> None:
    domain_course_counts = Counter(c.domain for c in courses.values())
    for domain, count in domain_course_counts.items():
        if count < MIN_COURSES_PER_DOMAIN:
            report.thin_domains[domain] = count

    role_project_counts: Counter[str] = Counter()
    for project in projects:
        for role in project.target_roles:
            role_project_counts[role] += 1
    report.projects_per_role = dict(role_project_counts)

    for role in known_roles:
        count = role_project_counts.get(role, 0)
        if count < MIN_PROJECTS_PER_ROLE:
            report.thin_roles[role] = count

    if report.thin_roles:
        report.warnings.append(
            f"{len(report.thin_roles)} role(s) below the {MIN_PROJECTS_PER_ROLE}-project "
            f"target from section 8 (see thin_roles for counts)"
        )
    if report.thin_domains:
        report.warnings.append(
            f"{len(report.thin_domains)} domain(s) below {MIN_COURSES_PER_DOMAIN} courses "
            f"(see thin_domains for counts)"
        )
