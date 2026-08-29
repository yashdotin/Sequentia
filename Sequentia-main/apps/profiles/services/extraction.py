
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import spacy

from apps.recommender.ml.metadata import load_course_metadata
from apps.recommender.ml.phrase_similarity import best_label_match

_KNOWN_LEMMAS = {"know", "complete", "finish", "learn", "master"}
_INTEREST_LEMMAS = {"interest", "explore", "love", "enjoy", "like", "curious"}
_TARGET_ROLE_CUES = re.compile(
    r"\bbecome\s+an?\s+([a-z][a-z /+-]{2,40}?)(?:\.|,|$| who| that| and)",
    re.IGNORECASE,
)
_GENERIC_CHUNKS = {"i", "it", "this", "that", "they", "he", "she", "we", "you"}


@lru_cache(maxsize=1)
def _get_nlp():
    return spacy.load("en_core_web_sm")


@dataclass
class ExtractionResult:
    target_role: str = ""
    known_skills: list[str] = field(default_factory=list)
    inferred_interests: list[str] = field(default_factory=list)


def _sentence_intent(sent) -> str | None:
    def _is_negated(token) -> bool:


        own_neg = any(child.dep_ == "neg" for child in token.children)
        head_neg = any(child.dep_ == "neg" for child in token.head.children)
        return own_neg or head_neg

    has_known = any(
        t.lemma_.lower() in _KNOWN_LEMMAS and not _is_negated(t) for t in sent
    )
    if has_known:
        return "known"
    has_interest = any(
        (t.lemma_.lower() in _INTEREST_LEMMAS or t.text.lower() == "interested")
        and not _is_negated(t)
        for t in sent
    )
    return "interest" if has_interest else None


def _candidate_chunks(sent) -> list[str]:
    return [
        nc.text.strip()
        for nc in sent.noun_chunks
        if nc.text.strip().lower() not in _GENERIC_CHUNKS and len(nc.text.strip()) > 1
    ]


def extract_from_text(text: str) -> ExtractionResult:
    text = (text or "").strip()
    result = ExtractionResult()
    if not text:
        return result

    role_match = _TARGET_ROLE_CUES.search(text)
    if role_match:
        result.target_role = role_match.group(1).strip().title()

    metadata = load_course_metadata()
    course_names = list(metadata.keys())
    domain_labels = sorted({m.domain for m in metadata.values()})

    nlp = _get_nlp()
    doc = nlp(text)

    known: set[str] = set()
    interests: set[str] = set()

    for sent in doc.sents:
        intent = _sentence_intent(sent)
        if not intent:
            continue

        sent_simplified = re.sub(r"[^a-z0-9 ]", "", sent.text.lower())

        if intent == "known":


            for course in course_names:
                simplified_course = re.sub(r"[^a-z0-9 ]", "", course.lower())
                if simplified_course and simplified_course in sent_simplified:
                    known.add(course)
            continue


        for chunk in _candidate_chunks(sent):
            domain_match = best_label_match(chunk, domain_labels)
            if domain_match:
                interests.add(domain_match)
            else:
                for domain in domain_labels:
                    if domain.lower() in chunk.lower() or chunk.lower() in domain.lower():
                        interests.add(domain)

    result.known_skills = sorted(known)
    result.inferred_interests = sorted(interests)
    return result
