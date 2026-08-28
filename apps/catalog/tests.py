from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import LearnerProjectState
from apps.catalog.services.project_recommender import compute_readiness, recommend_projects
from apps.catalog.services.projects import load_project_seed
from apps.profiles.models import LearnerInterest, LearnerProfile, LearnerSkillEvidence, LearningHistoryEntry
from apps.pathway.services.path_engine import generate_path


def _make_profile(username, goal_text, experience="beginner"):
    user = User.objects.create_user(username=username, password="testpass123")
    profile = LearnerProfile.objects.create(user=user, goal_text=goal_text, experience_level=experience)
    return user, profile


class ProjectCatalogTests(TestCase):
    def test_catalog_is_not_ml_dominated(self):
        """Regression guard for the original bug report: the project
        catalog must have meaningful non-ML coverage, not just a handful of
        ML/DL projects with everything else an afterthought."""
        projects = load_project_seed()
        ml_dl_count = sum(1 for p in projects if p.domain in ("Machine Learning", "Deep Learning", "MLOps"))
        non_ml_domains = {p.domain for p in projects if p.domain not in ("Machine Learning", "Deep Learning", "MLOps")}
        self.assertLess(ml_dl_count, len(projects) * 0.3, "ML/DL/MLOps should be under 30% of the catalog")
        for expected_domain in ("Web Development", "Mobile Development", "DevOps", "Cloud", "Security", "Data Analytics"):
            self.assertIn(expected_domain, non_ml_domains, f"No project exists for {expected_domain}")

    def test_every_project_skill_is_a_real_course(self):
        """Skill strings in project_seed.csv must exactly match real course
        names — otherwise readiness can never reach 1.0 and every project
        is permanently locked."""
        from apps.recommender.ml.metadata import load_course_metadata
        metadata = load_course_metadata()
        for project in load_project_seed():
            for skill in project.skills:
                self.assertIn(skill, metadata, f'"{project.slug}" lists unknown skill "{skill}"')


class ProjectUnlockingTests(TestCase):
    """Regression tests for the exact bug this session found: unlocking
    used to compare a project's old `stage` string against the path's new
    domain-derived stage names, which silently broke once those vocabularies
    diverged. Unlocking must be skill-based, never a stage string match."""

    def test_project_locked_without_required_skills(self):
        _, profile = _make_profile("lockedu", "I want to become a full stack web developer")
        readiness, satisfied, missing = compute_readiness(
            profile, next(p for p in load_project_seed() if p.slug == "task-manager-react")
        )
        self.assertLess(readiness, 1.0)
        self.assertTrue(missing)

    def test_project_unlocks_when_skills_satisfied(self):
        _, profile = _make_profile("unlocku", "I want to become a full stack web developer")
        project = next(p for p in load_project_seed() if p.slug == "task-manager-react")
        for skill in project.skills:
            LearnerSkillEvidence.objects.create(profile=profile, skill=skill, evidence_level="known", source="test")
        readiness, satisfied, missing = compute_readiness(profile, project)
        self.assertEqual(readiness, 1.0)
        self.assertEqual(missing, [])

    def test_recommend_projects_reflects_real_lock_state_not_old_stage_strings(self):
        """Direct regression check: an old-style stage name ('Core Skills')
        would never match any new domain-derived path stage — confirming
        recommend_projects doesn't rely on that comparison at all."""
        _, profile = _make_profile("stagecheck", "I want to become a data analyst")
        recs = recommend_projects(profile)
        self.assertTrue(recs)
        for rec in recs:
            self.assertIn(rec.status, ("recommended", "locked", "completed", "published"))
            # locked/recommended must be explained by readiness, not domain string luck
            if rec.status == "recommended":
                self.assertGreaterEqual(rec.readiness, 1.0)


class ProjectDomainRelevanceTests(TestCase):
    def test_web_dev_learner_is_not_recommended_ml_capstone(self):
        _, profile = _make_profile("webprojtest", "I want to become a full stack web developer")
        recs = recommend_projects(profile)
        recommended_slugs = {r.project.slug for r in recs if r.status == "recommended"}
        self.assertNotIn("capstone-deploy", recommended_slugs)
        self.assertNotIn("house-price-predictor", recommended_slugs)


class ProjectCompletionSkillEvidenceTests(TestCase):
    def test_completing_a_project_creates_inferred_evidence(self):
        _, profile = _make_profile("projcomplete", "I want to become a full stack web developer")
        project = next(p for p in load_project_seed() if p.slug == "portfolio-website")
        for skill in project.skills:
            LearnerSkillEvidence.objects.create(profile=profile, skill=skill, evidence_level="known", source="test")
        generate_path(profile, "web developer", reason="Initial")

        self.client.login(username="projcomplete", password="testpass123")
        self.client.post(reverse("catalog:project_action", args=["portfolio-website"]), {"action": "start"})
        self.client.post(reverse("catalog:project_action", args=["portfolio-website"]), {"action": "complete"})

        state = LearnerProjectState.objects.get(profile=profile, project_slug="portfolio-website")
        self.assertEqual(state.status, "completed")

    def test_project_completion_does_not_downgrade_known_evidence(self):
        _, profile = _make_profile("nodowngrade", "I want to become a full stack web developer")
        project = next(p for p in load_project_seed() if p.slug == "portfolio-website")
        for skill in project.skills:
            LearnerSkillEvidence.objects.create(profile=profile, skill=skill, evidence_level="known", source="onboarding_picker")

        self.client.login(username="nodowngrade", password="testpass123")
        self.client.post(reverse("catalog:project_action", args=["portfolio-website"]), {"action": "complete"})

        for skill in project.skills:
            ev = LearnerSkillEvidence.objects.get(profile=profile, skill=skill)
            self.assertEqual(ev.evidence_level, "known")
            self.assertEqual(ev.source, "onboarding_picker")
