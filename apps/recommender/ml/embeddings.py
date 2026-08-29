
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from django.conf import settings
from gensim.models import Word2Vec
from joblib import dump, load
from scipy.sparse import csr_matrix, save_npz, load_npz
from sklearn.feature_extraction.text import TfidfVectorizer

from .loader import CourseCorpus

_TOKEN_PATTERN = re.compile(r"[a-zA-Z]+")

VECTOR_SIZE = 100
WORD2VEC_MIN_COUNT = 3
WORD2VEC_WINDOW = 5
WORD2VEC_EPOCHS = 10


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


@dataclass(frozen=True)
class CourseEmbeddingIndex:
    course_order: tuple[str, ...]
    vectorizer: TfidfVectorizer
    vocab_vectors: np.ndarray
    course_vectors: np.ndarray
    lexical_vectorizer: TfidfVectorizer
    lexical_matrix: csr_matrix

    def encode_query(self, text: str) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            return np.zeros(self.vocab_vectors.shape[1], dtype=np.float32)
        weights = self.vectorizer.transform([text]).toarray()[0]
        vector = weights @ self.vocab_vectors
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector


def _artifact_dir() -> Path:
    path = Path(settings.DATA_DIR) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_and_save(corpora: dict[str, CourseCorpus]) -> CourseEmbeddingIndex:
    course_order = tuple(corpora.keys())
    documents = [corpora[c].document for c in course_order]


    tokenized_docs = [_tokenize(doc) for doc in documents]
    w2v = Word2Vec(
        sentences=tokenized_docs,
        vector_size=VECTOR_SIZE,
        window=WORD2VEC_WINDOW,
        min_count=WORD2VEC_MIN_COUNT,
        workers=4,
        epochs=WORD2VEC_EPOCHS,
        sg=1,
    )


    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 1),
        sublinear_tf=True,
        min_df=2,
    )
    tfidf_matrix = vectorizer.fit_transform(documents)

    vocab_terms = vectorizer.get_feature_names_out()
    vocab_vectors = np.zeros((len(vocab_terms), VECTOR_SIZE), dtype=np.float32)
    for i, term in enumerate(vocab_terms):
        if term in w2v.wv:
            vocab_vectors[i] = w2v.wv[term]

    course_vectors = tfidf_matrix.toarray() @ vocab_vectors
    norms = np.linalg.norm(course_vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    course_vectors = course_vectors / norms


    lexical_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    lexical_matrix = lexical_vectorizer.fit_transform(documents)

    index = CourseEmbeddingIndex(
        course_order=course_order,
        vectorizer=vectorizer,
        vocab_vectors=vocab_vectors,
        course_vectors=course_vectors,
        lexical_vectorizer=lexical_vectorizer,
        lexical_matrix=lexical_matrix,
    )
    _save(index, w2v)
    return index


def _save(index: CourseEmbeddingIndex, w2v: Word2Vec) -> None:
    artifact_dir = _artifact_dir()
    w2v.save(str(artifact_dir / "word2vec.model"))
    dump(index.vectorizer, artifact_dir / "tfidf_vectorizer.joblib")
    dump(index.lexical_vectorizer, artifact_dir / "lexical_vectorizer.joblib")
    save_npz(artifact_dir / "lexical_matrix.npz", index.lexical_matrix)
    np.save(artifact_dir / "vocab_vectors.npy", index.vocab_vectors)
    np.save(artifact_dir / "course_vectors.npy", index.course_vectors)
    (artifact_dir / "course_order.json").write_text(json.dumps(list(index.course_order)))


def artifacts_exist() -> bool:
    artifact_dir = _artifact_dir()
    required = [
        "tfidf_vectorizer.joblib",
        "lexical_vectorizer.joblib",
        "lexical_matrix.npz",
        "vocab_vectors.npy",
        "course_vectors.npy",
        "course_order.json",
    ]
    return all((artifact_dir / name).exists() for name in required)


def load_embeddings() -> CourseEmbeddingIndex:
    artifact_dir = _artifact_dir()
    vectorizer = load(artifact_dir / "tfidf_vectorizer.joblib")
    lexical_vectorizer = load(artifact_dir / "lexical_vectorizer.joblib")
    lexical_matrix = load_npz(artifact_dir / "lexical_matrix.npz")
    vocab_vectors = np.load(artifact_dir / "vocab_vectors.npy")
    course_vectors = np.load(artifact_dir / "course_vectors.npy")
    course_order = tuple(json.loads((artifact_dir / "course_order.json").read_text()))
    return CourseEmbeddingIndex(
        course_order=course_order,
        vectorizer=vectorizer,
        vocab_vectors=vocab_vectors,
        course_vectors=course_vectors,
        lexical_vectorizer=lexical_vectorizer,
        lexical_matrix=lexical_matrix,
    )
