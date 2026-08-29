
from __future__ import annotations

from apps.profiles.models import LearnerProfile


FOUNDATION_DOMAINS = {
    "Programming Foundations",
    "Math Foundations",
    "Developer Tools",
    "Databases",
}


DOMAIN_ADJACENCY: dict[str, set[str]] = {
    "Web Development": {"Databases"},
    "Mobile Development": {"Databases"},
    "Data Analytics": {"Databases", "Math Foundations"},
    "Machine Learning": {"Math Foundations", "Data Analytics", "Deep Learning", "MLOps"},
    "Deep Learning": {"Machine Learning", "MLOps", "Math Foundations"},
    "Data Engineering": {"Databases", "Cloud", "DevOps"},
    "DevOps": {"Cloud", "Developer Tools", "Systems"},
    "Cloud": {"DevOps"},
    "MLOps": {"Machine Learning", "DevOps", "Cloud"},
    "Security": set(),
    "Blockchain": {"Web Development"},
    "Systems": set(),
}


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
    haystack = f"{profile.target_role or ''} {profile.goal_text or ''}".lower()
    for keywords, domain in ROLE_DOMAIN_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return domain


    first_interest = profile.interests.values_list("label", flat=True).first()
    return first_interest or None


def relevant_domains(primary_domain: str | None) -> set[str] | None:
    if not primary_domain:
        return None
    return {primary_domain} | DOMAIN_ADJACENCY.get(primary_domain, set())
