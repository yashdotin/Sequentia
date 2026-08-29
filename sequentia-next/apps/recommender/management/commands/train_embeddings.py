import time

from django.core.management.base import BaseCommand

from apps.recommender.ml.embeddings import build_and_save
from apps.recommender.ml.loader import build_course_corpora


class Command(BaseCommand):
    help = (
        "Trains the Word2Vec + TF-IDF course embedding artifacts from train.csv "
        "and course_metadata_seed.csv, and saves them to data/artifacts/. "
        "Run this after editing either source file, or on first setup."
    )

    def handle(self, *args, **options):
        self.stdout.write("Loading train.csv and course_metadata_seed.csv...")
        corpora = build_course_corpora()
        self.stdout.write(f"Loaded {len(corpora)} courses. Training embeddings...")

        t0 = time.time()
        build_and_save(corpora)
        elapsed = time.time() - t0

        self.stdout.write(self.style.SUCCESS(f"Done in {elapsed:.1f}s. Artifacts saved to data/artifacts/."))
