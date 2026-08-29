
from __future__ import annotations

from apps.recommender.services.scoring import CourseScore


def explain_recommendation(score: CourseScore) -> str:
    reasons = []

    if score.components["semantic_relevance"] > 0.5:
        reasons.append("closely matches your stated goal")
    elif score.components["semantic_relevance"] > 0.15:
        reasons.append("relates to your stated goal")

    if score.components["interest_alignment"] > 0:
        reasons.append(f"aligned with your interest in {score.meta.domain}")

    if score.missing_prerequisites:
        missing = ", ".join(score.missing_prerequisites)
        reasons.append(f"has unmet prerequisites ({missing})")
    else:
        reasons.append("has no unmet prerequisites")

    if score.components["skill_gap"] > 0.8:
        reasons.append("addresses a current gap in your profile")
    elif score.components["skill_gap"] < 0.2:
        reasons.append("you already have strong evidence in this area")

    if not reasons:
        reasons.append("a general fit based on your current profile")

    return "Recommended because it " + "; ".join(reasons) + "."


def explain_blocked(score: CourseScore) -> str:
    if not score.missing_prerequisites:
        return ""
    missing = " and ".join(score.missing_prerequisites)
    return f"{missing} {'is' if len(score.missing_prerequisites) == 1 else 'are'} insufficient right now."


def explain_order(current: CourseScore, later: CourseScore) -> str:
    if later.meta.course in current.meta.prerequisites:
        return (
            f"{later.meta.course} appears later because {current.meta.course} "
            f"is one of its prerequisites and your profile doesn't show strong "
            f"evidence there yet."
        )
    if later.missing_prerequisites:
        missing = ", ".join(later.missing_prerequisites)
        return (
            f"{later.meta.course} is placed later because it depends on {missing}, "
            f"which your current profile doesn't show sufficient evidence for."
        )
    return (
        f"{current.meta.course} is placed first because it currently scores higher "
        f"on relevance and readiness for your goal."
    )
