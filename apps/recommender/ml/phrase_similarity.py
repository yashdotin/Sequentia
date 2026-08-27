"""
Lightweight phrase-to-label similarity using the SAME Word2Vec model trained
on the review corpus (see embeddings.py) — reused here rather than duplicated,
so "kubernetes" being associated with "devops"/"orchestration" pays off in
extraction too, not just in course ranking.

Deliberately simple: average the in-vocabulary word vectors for a phrase, do
the same for each candidate label, cosine-compare. Good enough for matching
short noun-chunk phrases against ~15 domain labels and 80 course names —
doesn't need the TF-IDF weighting that full-document course ranking needs.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from django.conf import settings
from gensim.models import Word2Vec

from .embeddings import _tokenize


@lru_cache(maxsize=1)
def _get_word2vec() -> Word2Vec:
    path = settings.DATA_DIR / "artifacts" / "word2vec.model"
    if not path.exists():
        raise RuntimeError(
            "No trained embeddings found. Run `python manage.py train_embeddings` first."
        )
    return Word2Vec.load(str(path))


def phrase_vector(text: str) -> np.ndarray | None:
    """Average word vector for a short phrase. None if no tokens are in-vocabulary."""
    w2v = _get_word2vec()
    tokens = [t for t in _tokenize(text) if t in w2v.wv]
    if not tokens:
        return None
    vectors = np.array([w2v.wv[t] for t in tokens])
    vector = vectors.mean(axis=0)
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else None


def best_label_match(phrase: str, labels: list[str], threshold: float = 0.35) -> str | None:
    """
    Returns the label (e.g. a domain name) most similar to `phrase`, or None if
    nothing clears `threshold`. Threshold chosen empirically — see
    profiles/services/extraction.py tests for the phrasings it's tuned against.
    """
    phrase_vec = phrase_vector(phrase)
    if phrase_vec is None:
        return None

    best_label, best_score = None, threshold
    for label in labels:
        label_vec = phrase_vector(label)
        if label_vec is None:
            continue
        score = float(phrase_vec @ label_vec)
        if score > best_score:
            best_label, best_score = label, score
    return best_label
