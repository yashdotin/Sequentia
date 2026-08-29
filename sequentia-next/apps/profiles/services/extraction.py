"""
Extracts structured signals from a learner's free-text onboarding message.

No external LLM. Uses spaCy's dependency parser to find, per sentence, who's
doing what to which noun phrase — "I already know X" vs "I'm interested in Y"
vs "I want to become a Z" get handled as different intents, not one regex.
Noun-chunk candidates are then grounded against real course/domain vocabulary
via the domain-trained Word2Vec similarity (phrase_similarity.py) rather than
a hardcoded keyword list — a phrasing like "I love container orchestration"
now maps to Cloud/DevOps even though no keyword dict entry says so, because
the model learned kubernetes/docker/orchestration cluster together from the
review corpus itself.

Confidence discipline unchanged from the regex version: exact course-name
matches under a "known" cue → "known". Everything else the parser/similarity
matcher finds → "inferred". Nothing becomes "known" from a fuzzy match.
"""

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
    """
    Returns 'known' or 'interest' if any token in the sentence carries that
    lemma — scanning the whole sentence rather than just the syntactic ROOT,
    since intent verbs often show up as a conjunct ("know X and want Y") or
    an adjectival complement ("I'm interested in X", where ROOT is the copula
    "be" and "interested" is its acomp child, not the ROOT itself).

    A token negated via spaCy's `neg` dependency ("don't know", "not
    interested") is excluded — otherwise "I don't know React" would be read
    as known-skill evidence, the opposite of what was said.
    """
    def _is_negated(token) -> bool:
        # neg usually attaches to the token itself ("don't know"), but for
        # copula constructions ("I'm not interested") it attaches to the
        # copula ("'m") that governs the adjective, not the adjective itself.
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
            # Exact course-name mention detection uses whole-sentence substring
            # matching, not noun-chunk boundaries — spaCy's chunker splits
            # multi-word course names at prepositions ("SQL for Beginners" ->
            # "SQL" + "Beginners" as separate chunks), which would otherwise
            # miss the exact match. This is the one place precision matters
            # more than generalization: "known" is the highest-confidence tag.
            for course in course_names:
                simplified_course = re.sub(r"[^a-z0-9 ]", "", course.lower())
                if simplified_course and simplified_course in sent_simplified:
                    known.add(course)
            continue

        # intent == "interest": ground each noun-chunk candidate against real
        # domain vocabulary via Word2Vec similarity, so phrasing that doesn't
        # match any hardcoded keyword can still land on the right domain.
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
