
from __future__ import annotations


def build_query_text(goal: str = "", interests: str = "", known_areas: str = "") -> str:
    parts = [p.strip() for p in (goal, interests, known_areas) if p and p.strip()]
    return " ".join(parts)
