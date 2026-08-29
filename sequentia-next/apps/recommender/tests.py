import csv
import tempfile
from pathlib import Path

from django.test import TestCase

from apps.recommender.ml.feature_builder import build_query_text
from apps.recommender.ml.inference import get_engine
from apps.recommender.ml.loader import DataLoadError, build_course_corpora
from apps.recommender.ml.metadata import MetadataError, load_course_metadata


class MetadataLoadingTests(TestCase):
    def test_loads_all_80_courses_with_valid_difficulty(self):
        metadata = load_course_metadata()
        self.assertEqual(len(metadata), 80)
        for meta in metadata.values():
            self.assertIn(meta.difficulty, {"Beginner", "Intermediate", "Advanced"})

    def test_prerequisites_reference_known_courses(self):
        metadata = load_course_metadata()
        for meta in metadata.values():
            for prereq in meta.prerequisites:
                self.assertIn(prereq, metadata)

    def test_rejects_unknown_prerequisite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["course", "domain", "difficulty", "resource_type", "prerequisites"])
                writer.writerow(["Course A", "Web", "Beginner", "course", ""])
                writer.writerow(["Course B", "Web", "Intermediate", "course", "Nonexistent Course"])
            with self.assertRaises(MetadataError):
                load_course_metadata(path)

    def test_rejects_invalid_difficulty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["course", "domain", "difficulty", "resource_type", "prerequisites"])
                writer.writerow(["Course A", "Web", "Expert", "course", ""])
            with self.assertRaises(MetadataError):
                load_course_metadata(path)


class CourseCorpusTests(TestCase):
    def test_builds_one_corpus_entry_per_course(self):
        corpora = build_course_corpora()
        self.assertEqual(len(corpora), 80)

    def test_review_counts_are_positive_and_documents_nonempty(self):
        corpora = build_course_corpora()
        for corpus in corpora.values():
            self.assertGreater(corpus.review_count, 0)
            self.assertTrue(corpus.document.strip())

    def test_raises_when_reviews_and_metadata_disagree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mismatched.csv"
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["course", "domain", "difficulty", "resource_type", "prerequisites"])
                writer.writerow(["Totally Made Up Course", "Web", "Beginner", "course", ""])
            with self.assertRaises(DataLoadError):
                build_course_corpora(metadata_path=path)


class SemanticRelevanceTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = get_engine()

    def test_empty_query_returns_all_courses_at_zero(self):
        results = self.engine.semantic_relevance("")
        self.assertEqual(len(results), 80)
        self.assertTrue(all(score == 0.0 for _, score in results))

    def test_kubernetes_query_ranks_kubernetes_course_highly(self):
        results = self.engine.semantic_relevance("kubernetes container orchestration", top_n=5)
        top_courses = [course for course, _ in results]
        self.assertIn("Kubernetes Orchestration", top_courses)

    def test_ml_goal_ranks_ml_courses_above_unrelated_ones(self):
        query = build_query_text(
            goal="I want to become a machine learning engineer",
            interests="neural networks, deep learning",
        )
        results = dict(self.engine.semantic_relevance(query))
        self.assertGreater(
            results["Machine Learning Fundamentals"],
            results["HTML and CSS for Beginners"],
        )

    def test_scores_are_sorted_descending(self):
        results = self.engine.semantic_relevance("python programming", top_n=10)
        scores = [score for _, score in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
