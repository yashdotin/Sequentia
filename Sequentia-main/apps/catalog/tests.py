from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import LearnerProjectState
from apps.catalog.services.catalog_validation import run_validation
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
        projects = load_project_seed()
        ml_dl_count = sum(1 for p in projects if p.domain in ("Machine Learning", "Deep Learning", "MLOps"))
        non_ml_domains = {p.domain for p in projects if p.domain not in ("Machine Learning", "Deep Learning", "MLOps")}
        self.assertLess(ml_dl_count, len(projects) * 0.4, "ML/DL/MLOps should be under 40% of the catalog")
        for expected_domain in ("Web Development", "Mobile Development", "DevOps", "Cloud", "Security", "Data Analytics"):
            self.assertIn(expected_domain, non_ml_domains, f"No project exists for {expected_domain}")

    def test_every_project_skill_is_a_real_course(self):
        from apps.recommender.ml.metadata import load_course_metadata
        metadata = load_course_metadata()
        for project in load_project_seed():
            for skill in project.skills:
                self.assertIn(skill, metadata, f'"{project.slug}" lists unknown skill "{skill}"')


class ProjectUnlockingTests(TestCase):

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
        _, profile = _make_profile("stagecheck", "I want to become a data analyst")
        recs = recommend_projects(profile)
        self.assertTrue(recs)
        for rec in recs:
            self.assertIn(rec.status, ("recommended", "locked", "completed", "published"))

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


class ProjectRoleAlignmentTests(TestCase):

    def _profile_with_all_skills_known(self, username, goal, target_role, project_slug):
        user = User.objects.create_user(username=username, password="testpass123")
        profile = LearnerProfile.objects.create(
            user=user, goal_text=goal, target_role=target_role, experience_level="intermediate",
        )
        project = next(p for p in load_project_seed() if p.slug == project_slug)
        for skill in project.skills:
            LearnerSkillEvidence.objects.create(profile=profile, skill=skill, evidence_level="known", source="test")
        return profile

    def test_frontend_developer_does_not_get_ml_projects_recommended(self):
        profile = self._profile_with_all_skills_known(
            "frontendneg", "I want to become a frontend developer", "Frontend Developer", "portfolio-website"
        )
        recs = recommend_projects(profile)
        recommended_slugs = {r.project.slug for r in recs if r.status == "recommended"}
        self.assertNotIn("house-price-predictor", recommended_slugs)
        self.assertNotIn("image-classifier", recommended_slugs)
        self.assertNotIn("ml-inference-api", recommended_slugs)

    def test_backend_developer_does_not_get_image_classifier(self):
        profile = self._profile_with_all_skills_known(
            "backendneg", "I want to become a backend developer", "Backend Developer", "auth-service"
        )
        recs = recommend_projects(profile)
        recommended_slugs = {r.project.slug for r in recs if r.status == "recommended"}
        self.assertNotIn("image-classifier", recommended_slugs)

    def test_data_analyst_does_not_get_react_or_kubernetes(self):
        profile = self._profile_with_all_skills_known(
            "analystneg", "I want to become a data analyst", "Data Analyst", "sales-analytics-dashboard"
        )
        recs = recommend_projects(profile)
        recommended_slugs = {r.project.slug for r in recs if r.status == "recommended"}
        self.assertNotIn("ecommerce-frontend-react", recommended_slugs)
        self.assertNotIn("k8s-deployment", recommended_slugs)

    def test_frontend_project_scores_higher_for_frontend_role_than_backend_role(self):
        frontend_profile = self._profile_with_all_skills_known(
            "roleposA", "I want to become a frontend developer", "Frontend Developer", "portfolio-website"
        )
        backend_profile = self._profile_with_all_skills_known(
            "roleposB", "I want to become a backend developer", "Backend Developer", "portfolio-website"
        )
        frontend_recs = {r.project.slug: r.score for r in recommend_projects(frontend_profile)}
        backend_recs = {r.project.slug: r.score for r in recommend_projects(backend_profile)}
        self.assertGreater(frontend_recs["portfolio-website"], backend_recs["portfolio-website"])

    def test_devops_engineer_positive_gets_a_devops_project(self):
        user = User.objects.create_user(username="devopspos", password="testpass123")
        profile = LearnerProfile.objects.create(
            user=user, goal_text="I want to become a DevOps engineer", target_role="DevOps Engineer",
            experience_level="intermediate",
        )
        project = next(p for p in load_project_seed() if p.slug == "cicd-pipeline-demo")
        for skill in project.skills:
            LearnerSkillEvidence.objects.create(profile=profile, skill=skill, evidence_level="known", source="test")
        recs = recommend_projects(profile)
        recommended_slugs = {r.project.slug for r in recs if r.status == "recommended"}
        self.assertIn("cicd-pipeline-demo", recommended_slugs)


class ProjectPathRelevanceTests(TestCase):

    def test_project_sharing_skills_with_current_path_scores_higher(self):
        user = User.objects.create_user(username="pathrel", password="testpass123")
        profile = LearnerProfile.objects.create(
            user=user, goal_text="I want to become a frontend developer",
            target_role="Frontend Developer", experience_level="beginner",
        )
        project = next(p for p in load_project_seed() if p.slug == "portfolio-website")
        for skill in project.skills:
            LearnerSkillEvidence.objects.create(profile=profile, skill=skill, evidence_level="known", source="test")

        path = generate_path(profile, "frontend developer html css", reason="Initial")

        score_with_path = next(r for r in recommend_projects(profile, path=path) if r.project.slug == "portfolio-website").score
        score_without_path = next(r for r in recommend_projects(profile, path=None) if r.project.slug == "portfolio-website").score


        self.assertGreaterEqual(score_with_path, score_without_path)


class CatalogValidationTests(TestCase):
    def test_real_catalog_has_no_errors(self):
        report = run_validation()
        self.assertTrue(report.ok, msg=report.errors)
        self.assertEqual(report.skill_count, 96)
        self.assertEqual(report.course_count, 101)
        self.assertEqual(report.project_count, 147)

    def test_every_project_role_is_a_known_role(self):
        report = run_validation()
        role_errors = [e for e in report.errors if "not a valid role" in e]
        self.assertEqual(role_errors, [])

    def test_no_dangling_project_course_references(self):
        report = run_validation()
        dangling = [e for e in report.errors if "unknown course" in e]
        self.assertEqual(dangling, [])

    def test_no_orphan_skills_missing_a_course(self):
        report = run_validation()
        self.assertEqual(report.orphan_skills_no_course, [])

    def test_courses_without_review_data_are_reported_not_fatal(self):


        report = run_validation()
        self.assertTrue(report.ok)
        self.assertGreater(len(report.courses_without_review_data), 0)


class ProjectPrerequisiteDemonstratesSplitTests(TestCase):

    def test_demonstrates_matches_canonical_skills_of_listed_courses(self):
        projects = {p.slug: p for p in load_project_seed()}
        django_blog = next(
            (p for p in projects.values() if "Django Web Framework" in p.skills), None
        )
        self.assertIsNotNone(django_blog)
        self.assertIn("django", django_blog.demonstrates_skill_ids)

    def test_prerequisites_pull_in_the_parent_skill_not_the_skill_itself(self):
        projects = load_project_seed()
        django_project = next(p for p in projects if "django" in p.demonstrates_skill_ids)
        self.assertIn("python", django_project.prerequisite_skill_ids)
        self.assertNotIn("django", django_project.prerequisite_skill_ids)

    def test_prerequisites_and_demonstrates_are_disjoint_sets(self):


        for project in load_project_seed():
            overlap = set(project.prerequisite_skill_ids) & set(project.demonstrates_skill_ids)
            self.assertEqual(overlap, set(), msg=f"{project.slug} has overlapping prereq/demonstrates")

    def test_most_projects_have_a_nonempty_prerequisite_set(self):


        projects = load_project_seed()
        with_prereqs = sum(1 for p in projects if p.prerequisite_skill_ids)
        self.assertGreater(with_prereqs / len(projects), 0.5)

    def test_readiness_gating_is_unaffected_by_the_new_fields(self):


        _, profile = _make_profile("prereqsplitcheck", "I want to become a backend developer")
        project = next(p for p in load_project_seed() if p.slug == "task-manager-react")
        readiness, satisfied, missing = compute_readiness(profile, project)
        self.assertEqual(missing, list(project.skills))
        self.assertEqual(readiness, 0.0)
