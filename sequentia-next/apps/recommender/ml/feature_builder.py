"""
Turns learner-stated signals into the query text semantic_relevance() expects.

Kept deliberately small for Phase 3 — it only combines free-text fields that
already exist as plain strings. Phase 5 (learner profile models) will call this
with real profile data instead of raw strings.
"""

from __future__ import annotations


def build_query_text(goal: str = "", interests: str = "", known_areas: str = "") -> str:
    """
    Concatenates the learner's stated goal, interests, and known areas into one
    string for TF-IDF scoring. No weighting logic yet — that's a ranking-model
    decision for Phase 4, not a text-preparation one.
    """
    parts = [p.strip() for p in (goal, interests, known_areas) if p and p.strip()]
    return " ".join(parts)
