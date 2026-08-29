"""
Loads and aggregates the raw review dataset (train.csv).

train.csv is review-level (109,776 rows: Index, Reviews, Course). For course-level
semantic relevance we aggregate every review belonging to a course into one
document per course, then vectorize at the course level (not the review level) —
that's what inference.py needs to score "how relevant is course X to this goal".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from django.conf import settings

from .metadata import CourseMeta, MetadataError, load_course_metadata


class DataLoadError(Exception):
    """Raised when train.csv is missing, malformed, or inconsistent with the seed."""


@dataclass(frozen=True)
class CourseCorpus:
    """One course, its aggregated review text, its review count, and its metadata."""

    course: str
    review_count: int
    document: str  # all reviews concatenated — the unit the TF-IDF vectorizer sees
    meta: CourseMeta


def load_review_dataframe(path: str | Path | None = None) -> pd.DataFrame:
    path = Path(path or settings.TRAIN_REVIEWS_CSV)
    if not path.exists():
        raise DataLoadError(f"Reviews CSV not found: {path}")

    df = pd.read_csv(path)
    required_cols = {"Index", "Reviews", "Course"}
    missing = required_cols - set(df.columns)
    if missing:
        raise DataLoadError(f"train.csv missing expected columns: {missing}")

    if df["Reviews"].isnull().any() or df["Course"].isnull().any():
        raise DataLoadError("train.csv contains null Reviews or Course values")

    return df


def build_course_corpora(
    reviews_path: str | Path | None = None,
    metadata_path: str | Path | None = None,
) -> dict[str, CourseCorpus]:
    """
    Returns {course_name: CourseCorpus}, one entry per course present in BOTH
    train.csv and the metadata seed. Raises if the two sources disagree on which
    courses exist — that mismatch means stale metadata, not something to paper over.
    """
    df = load_review_dataframe(reviews_path)
    metadata = load_course_metadata(metadata_path)

    review_courses = set(df["Course"].unique())
    meta_courses = set(metadata.keys())

    only_in_reviews = review_courses - meta_courses
    only_in_meta = meta_courses - review_courses
    if only_in_reviews or only_in_meta:
        raise DataLoadError(
            "train.csv and course_metadata_seed.csv disagree on course names. "
            f"In reviews but not metadata: {only_in_reviews or 'none'}. "
            f"In metadata but not reviews: {only_in_meta or 'none'}."
        )

    corpora: dict[str, CourseCorpus] = {}
    grouped = df.groupby("Course")["Reviews"].apply(lambda s: " ".join(s.tolist()))
    counts = df["Course"].value_counts()

    for course, document in grouped.items():
        corpora[course] = CourseCorpus(
            course=course,
            review_count=int(counts[course]),
            document=document,
            meta=metadata[course],
        )

    return corpora
