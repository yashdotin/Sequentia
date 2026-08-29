"""
The inference layer other code should actually call.

get_engine() loads precomputed embedding artifacts from disk (fast — no
training). If artifacts don't exist yet (first run on a fresh clone), it
trains once and saves them, so every subsequent process start is fast.
Explicit control: `python manage.py train_embeddings` retrains and
overwrites the artifacts on demand (e.g. after editing course_metadata_seed.csv).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from sklearn.metrics.pairwise import linear_kernel

from .embeddings import CourseEmbeddingIndex, artifacts_exist, build_and_save, load_embeddings
from .loader import CourseCorpus, build_course_corpora

# Weight on the lexical (exact/technical-term) side of the hybrid score vs.
# the Word2Vec (synonym/concept) side. Tuned by hand against real queries —
# see embeddings.py's module docstring for why pure Word2Vec-averaging alone
# under-ranked exact matches like "kubernetes" -> Kubernetes Orchestration.
LEXICAL_WEIGHT = 0.6


@dataclass(frozen=True)
class RecommenderEngine:
    corpora: dict[str, CourseCorpus]
    embeddings: CourseEmbeddingIndex

    def semantic_relevance(self, query_text: str, top_n: int | None = None) -> list[tuple[str, float]]:
        """
        Hybrid score: LEXICAL_WEIGHT * TF-IDF cosine (exact/technical-term
        precision) + (1 - LEXICAL_WEIGHT) * Word2Vec cosine (synonym/concept
        recall, trained on this project's own review corpus). Each side is
        max-normalized within the query before blending so neither dominates
        just because of its own score scale.

        Returns [(course_name, score), ...] sorted descending. Empty query
        returns all courses at 0.0 rather than raising.
        """
        query_text = (query_text or "").strip()
        if not query_text:
            return [(c, 0.0) for c in self.embeddings.course_order]

        lexical_query = self.embeddings.lexical_vectorizer.transform([query_text])
        lexical_scores = linear_kernel(lexical_query, self.embeddings.lexical_matrix)[0]
        if lexical_scores.max() > 0:
            lexical_scores = lexical_scores / lexical_scores.max()

        query_vector = self.embeddings.encode_query(query_text)
        w2v_scores = self.embeddings.course_vectors @ query_vector
        if w2v_scores.max() > 0:
            w2v_scores = w2v_scores / w2v_scores.max()

        combined = LEXICAL_WEIGHT * lexical_scores + (1 - LEXICAL_WEIGHT) * w2v_scores

        ranked = sorted(
            zip(self.embeddings.course_order, combined.tolist()),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return ranked[:top_n] if top_n else ranked

    def get_course(self, course_name: str) -> CourseCorpus | None:
        return self.corpora.get(course_name)

    @property
    def all_courses(self) -> tuple[str, ...]:
        return self.embeddings.course_order


@lru_cache(maxsize=1)
def get_engine() -> RecommenderEngine:
    """Process-wide singleton — corpora + embeddings loaded/built once."""
    corpora = build_course_corpora()
    if artifacts_exist():
        embeddings = load_embeddings()
    else:
        embeddings = build_and_save(corpora)
    return RecommenderEngine(corpora=corpora, embeddings=embeddings)
