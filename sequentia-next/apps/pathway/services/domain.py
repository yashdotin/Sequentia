"""
Domain detection and cross-domain contamination control.

Replaces the old behavior where every learner's path was forced through the
same fixed stage order (Foundations -> Core Skills -> Machine Learning ->
Deep Learning -> Production & Data Systems -> Specialization) regardless of
their actual goal. A "Web Developer" goal used to still pull Machine Learning
and Deep Learning courses into the path every time, because those stages
existed unconditionally in STAGE_ORDER.

This module is intentionally a small, transparent, hand-curated lookup table
(same spirit as course_metadata_seed.csv) rather than a trained classifier —
domain names are a small fixed set of 16 real values from the catalog, and a
keyword table over that fixed vocabulary is inspectable and easy to correct,
where a black-box classifier would not be.
"""

from __future__ import annotations

from apps.profiles.models import LearnerProfile

# Domains that are prerequisite-ish / cross-cutting enough to always be
# eligible regardless of target domain (git, SQL, basic programming, math).
FOUNDATION_DOMAINS = {
    "Programming Foundations",
    "Math Foundations",
    "Developer Tools",
    "Databases",
}

# Legitimate cross-domain support (spec's own example: Full Stack ->
# Databases/Cloud/DevOps is fine; Full Stack -> Deep Learning is not).
# Curated by hand from the real 16 domains in course_metadata_seed.csv.
DOMAIN_ADJACENCY: dict[str, set[str]] = {
    "Web Development": {"Databases", "Cloud", "DevOps", "Developer Tools"},
    "Mobile Development": {"Databases", "Cloud", "Developer Tools"},
    "Data Analytics": {"Databases", "Math Foundations"},
    "Machine Learning": {"Math Foundations", "Data Analytics", "Deep Learning", "MLOps"},
    "Deep Learning": {"Machine Learning", "MLOps", "Math Foundations"},
    "Data Engineering": {"Databases", "Cloud", "DevOps"},
    "DevOps": {"Cloud", "Developer Tools", "Systems"},
    "Cloud": {"DevOps", "Systems"},
    "MLOps": {"Machine Learning", "DevOps", "Cloud"},
    "Security": {"Systems", "DevOps", "Cloud"},
    "Blockchain": {"Web Development", "Security"},
    "Systems": {"DevOps", "Cloud"},
}

# (keyword substrings, domain). Checked in order; first match wins. Keywords
# are lowercase substrings matched against "target_role + goal_text".
ROLE_DOMAIN_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("frontend", "front-end", "front end", "web develop", "full stack",
      "fullstack", "backend", "back-end", "back end", "web design", "web dev"), "Web Development"),
    (("mobile", "android", "ios app", "app develop", "flutter", "react native"), "Mobile Development"),
    (("data analyst", "data analytics", "business analyst", "bi analyst"), "Data Analytics"),
    (("data engineer",), "Data Engineering"),
    (("nlp", "computer vision", "deep learning", "neural network", "genai",
      "generative ai", "llm"), "Deep Learning"),
    (("machine learning", "ml engineer", "data scientist", "data science"), "Machine Learning"),
    (("mlops",), "MLOps"),
    (("devops", "site reliability", "sre "), "DevOps"),
    (("cloud engineer", "cloud architect", "aws", "azure", "gcp"), "Cloud"),
    (("cybersecurity", "cyber security", "security engineer", "security analyst",
      "penetration test", "pentest"), "Security"),
    (("blockchain", "web3", "smart contract"), "Blockchain"),
    (("systems engineer", "systems programm"), "Systems"),
]


def determine_primary_domain(profile: LearnerProfile) -> str | None:
    """
    Returns one of the 16 real catalog domains, or None if nothing could be
    determined (in which case the caller should NOT filter — an unknown
    domain is safer left unconstrained than guessed wrong).
    """
    haystack = f"{profile.target_role or ''} {profile.goal_text or ''}".lower()
    for keywords, domain in ROLE_DOMAIN_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return domain

    # Fall back to the learner's own explicit interest picks, if any.
    first_interest = profile.interests.values_list("label", flat=True).first()
    return first_interest or None


def relevant_domains(primary_domain: str | None) -> set[str] | None:
    """
    None means "unconstrained" — every domain stays eligible. This is the
    deliberate fallback when the domain genuinely can't be determined,
    rather than guessing and risking silently hiding a course the learner
    actually needs.
    """
    if not primary_domain:
        return None
    return {primary_domain} | DOMAIN_ADJACENCY.get(primary_domain, set())
