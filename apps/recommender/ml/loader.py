
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from django.conf import settings

from .metadata import CourseMeta, MetadataError, load_course_metadata


class DataLoadError(Exception):
    pass


@dataclass(frozen=True)
class CourseCorpus:

    course: str
    review_count: int
    document: str
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
    df = load_review_dataframe(reviews_path)
    metadata = load_course_metadata(metadata_path)

    review_courses = set(df["Course"].unique())
    meta_courses = set(metadata.keys())

    only_in_reviews = review_courses - meta_courses
    if only_in_reviews:
        raise DataLoadError(
            "train.csv references course(s) with no metadata entry — stale "
            f"or missing metadata: {only_in_reviews}"
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


def courses_without_review_data(metadata_path: str | Path | None = None, reviews_path: str | Path | None = None) -> set[str]:
    metadata = load_course_metadata(metadata_path)
    df = load_review_dataframe(reviews_path)
    return set(metadata.keys()) - set(df["Course"].unique())
