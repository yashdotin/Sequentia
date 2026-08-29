
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
    w2v = _get_word2vec()
    tokens = [t for t in _tokenize(text) if t in w2v.wv]
    if not tokens:
        return None
    vectors = np.array([w2v.wv[t] for t in tokens])
    vector = vectors.mean(axis=0)
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else None


def best_label_match(phrase: str, labels: list[str], threshold: float = 0.35) -> str | None:
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
