from __future__ import annotations

from apps.profiles.models import LearnerProfile
from apps.recommender.ml.metadata import load_course_metadata

STACK_SKILLS: dict[str, set[str]] = {
    "python": {"python", "python-automation", "django", "flask"},
    "javascript": {
        "javascript", "async-javascript", "typescript", "node",
        "react", "angular", "vue", "react-native",
    },
    "java": {"java", "spring-boot", "android"},
    "golang": {"golang"},
    "cpp": {"cpp"},
}

STACK_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("python", ("python", "django", "flask")),
    ("javascript", (
        "javascript", "js", "node.js", "node", "react", "angular", "vue",
        "typescript", "express", "mern", "mean",
    )),
    ("java", ("java", "spring boot", "spring")),
    ("golang", ("golang", "go language", "go backend")),
    ("cpp", ("c++", "c plus plus")),
]

ALL_STACK_SKILL_IDS: set[str] = set().union(*STACK_SKILLS.values())


def _stack_from_skill_ids(skill_ids: set[str]) -> str | None:
    counts = {
        stack: len(skill_ids & ids)
        for stack, ids in STACK_SKILLS.items()
        if skill_ids & ids
    }
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _stack_from_text(text: str) -> str | None:
    text = (text or "").lower()
    matched = [stack for stack, keywords in STACK_KEYWORDS if any(kw in text for kw in keywords)]
    if len(matched) == 1:
        return matched[0]
    return None


def detect_stack(profile: LearnerProfile) -> str | None:
    courses = load_course_metadata()

    known_courses = {
        e.skill for e in profile.skills.all() if e.evidence_level in ("known", "inferred")
    }
    known_courses.update(profile.history.filter(status="completed").values_list("course", flat=True))

    skill_ids: set[str] = set()
    for name in known_courses:
        meta = courses.get(name)
        if meta:
            skill_ids.update(meta.canonical_skill_ids)

    from_skills = _stack_from_skill_ids(skill_ids)
    if from_skills:
        return from_skills

    combined_text = f"{profile.goal_text} {profile.target_role}"
    return _stack_from_text(combined_text)


def stack_conflicts(canonical_skill_ids: tuple[str, ...], stack: str | None) -> bool:
    if not stack:
        return False
    course_skill_ids = set(canonical_skill_ids)
    if not (course_skill_ids & ALL_STACK_SKILL_IDS):
        return False
    return not (course_skill_ids & STACK_SKILLS[stack])
