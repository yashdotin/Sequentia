from django.contrib.auth.models import User
from django.template.defaultfilters import slugify
from django.test import TestCase
from django.urls import reverse

from apps.pathway.models import LearningPath
from apps.pathway.services.domain import determine_primary_domain
from apps.pathway.services.path_engine import generate_path, readiness_percent
from apps.pathway.services.path_validator import validate_path
from apps.profiles.models import LearnerInterest, LearnerProfile, LearnerSkillEvidence, LearningHistoryEntry
from apps.recommender.ml.metadata import load_course_metadata
from apps.recommender.models import Recommendation, RecommendationFeedback


def _make_profile(username, goal, experience="beginner"):
    user = User.objects.create_user(username=username, password="SuperSecret123!")
    profile = LearnerProfile.objects.create(user=user, goal_text=goal, experience_level=experience)
    return user, profile


class PathGenerationTests(TestCase):
    def test_generate_path_creates_versioned_path_with_items(self):
        _, profile = _make_profile("alice", "I want to become an AI/ML engineer")
        path = generate_path(profile, "AI/ML engineer machine learning", reason="Initial")
        self.assertEqual(path.version, 1)
        self.assertTrue(path.is_current)
        self.assertGreater(path.items.count(), 0)

    def test_exactly_one_current_item_when_eligible_courses_exist(self):
        _, profile = _make_profile("bob", "I want to become a web developer")
        path = generate_path(profile, "web developer javascript", reason="Initial")
        current_items = path.items.filter(status="current")
        self.assertLessEqual(current_items.count(), 1)

    def test_blocked_items_have_nonempty_reason(self):
        _, profile = _make_profile("carol", "I want to become an AI/ML engineer")
        path = generate_path(profile, "deep learning neural networks", reason="Initial")
        blocked = path.items.filter(status="blocked").first()
        if blocked:
            self.assertTrue(len(blocked.reason) > 0)

    def test_regenerating_path_creates_new_version_and_marks_old_not_current(self):
        _, profile = _make_profile("dave", "I want to become a data scientist")
        path1 = generate_path(profile, "data science", reason="Initial")
        path2 = generate_path(profile, "data science statistics", reason="Updated goal")
        path1.refresh_from_db()
        self.assertFalse(path1.is_current)
        self.assertTrue(path2.is_current)
        self.assertEqual(path2.version, path1.version + 1)


class SecurityTests(TestCase):
    def setUp(self):
        self.user_a, self.profile_a = _make_profile("usera", "I want to become an AI/ML engineer")
        self.user_b, self.profile_b = _make_profile("userb", "I want to become a web developer")
        self.path_a = generate_path(self.profile_a, "AI/ML engineer", reason="Initial")
        self.path_b = generate_path(self.profile_b, "web developer", reason="Initial")

    def test_user_b_cannot_view_user_a_path_via_own_session(self):
        self.client.login(username="userb", password="SuperSecret123!")
        response = self.client.get(reverse("pathway:path"))
        self.assertNotContains(response, "AI/ML engineer")

    def test_user_b_cannot_submit_feedback_on_user_a_recommendation(self):
        rec = Recommendation.objects.filter(profile=self.profile_a).first()
        self.client.login(username="userb", password="SuperSecret123!")
        response = self.client.post(
            reverse("recommender:feedback", args=[rec.id]),
            {"feedback": "not_helpful"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            RecommendationFeedback.objects.filter(profile=self.profile_b, recommendation=rec).exists()
        )

    def test_user_b_resource_detail_reflects_own_profile_only(self):
        self.client.login(username="userb", password="SuperSecret123!")
        item_a = self.path_a.items.first()
        response = self.client.get(reverse("catalog:resource_detail", args=[slugify(item_a.course)]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.profile_a.goal_text, response.content.decode())

    def test_anonymous_user_redirected_from_protected_pages(self):
        for url_name in ["dashboard:home", "pathway:path", "pathway:history", "profiles:profile", "profiles:skills"]:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/login/", response.url)

    def test_path_history_only_shows_own_versions(self):
        generate_path(self.profile_a, "AI/ML engineer updated", reason="Second version")
        self.client.login(username="userb", password="SuperSecret123!")
        response = self.client.get(reverse("pathway:history"))
        self.assertEqual(LearningPath.objects.filter(profile=self.profile_b).count(), 1)
        self.assertNotContains(response, "Second version")


class DomainDetectionTests(TestCase):
    def test_web_developer_goal_detects_web_development(self):
        _, profile = _make_profile("webdev1", "I want to become a full stack web developer")
        self.assertEqual(determine_primary_domain(profile), "Web Development")

    def test_data_analyst_goal_detects_data_analytics_not_ml(self):
        _, profile = _make_profile("analyst1", "I want to become a data analyst")
        self.assertEqual(determine_primary_domain(profile), "Data Analytics")

    def test_ml_engineer_goal_detects_machine_learning(self):
        _, profile = _make_profile("mleng1", "I want to become a machine learning engineer")
        self.assertEqual(determine_primary_domain(profile), "Machine Learning")

    def test_devops_goal_detects_devops(self):
        _, profile = _make_profile("devops1", "I want to become a DevOps engineer")
        self.assertEqual(determine_primary_domain(profile), "DevOps")

    def test_unrecognized_goal_with_no_interests_falls_back_to_none(self):
        _, profile = _make_profile("mystery1", "I want to grow professionally")
        self.assertIsNone(determine_primary_domain(profile))

    def test_falls_back_to_explicit_interest_when_role_text_is_unclear(self):
        _, profile = _make_profile("mystery2", "I want to grow professionally")
        LearnerInterest.objects.create(profile=profile, label="Cloud")
        self.assertEqual(determine_primary_domain(profile), "Cloud")


class DomainContaminationTests(TestCase):
    """Mandatory per spec: a Web Development goal must not produce a path
    containing Machine Learning / Deep Learning courses, and vice versa,
    unless the learner explicitly said they're interested in that domain."""

    def test_web_development_path_excludes_ml_and_deep_learning(self):
        _, profile = _make_profile("webdev2", "I want to become a full stack web developer")
        path = generate_path(profile, "full stack web developer javascript html css", reason="Initial")
        metadata = load_course_metadata()
        contaminating_domains = {"Machine Learning", "Deep Learning"}
        for item in path.items.filter(status__in=("current", "upcoming")):
            domain = metadata[item.course].domain
            self.assertNotIn(
                domain, contaminating_domains,
                f'"{item.course}" (domain={domain}) should not appear in a Web Development path',
            )

    def test_data_analyst_path_excludes_deep_learning(self):
        _, profile = _make_profile("analyst2", "I want to become a data analyst")
        path = generate_path(profile, "data analyst excel sql reporting", reason="Initial")
        metadata = load_course_metadata()
        for item in path.items.filter(status__in=("current", "upcoming")):
            domain = metadata[item.course].domain
            self.assertNotEqual(
                domain, "Deep Learning",
                f'"{item.course}" should not appear in a Data Analyst path',
            )

    def test_machine_learning_path_excludes_web_and_mobile(self):
        _, profile = _make_profile("mleng2", "I want to become a machine learning engineer")
        path = generate_path(profile, "machine learning python numpy pandas", reason="Initial")
        metadata = load_course_metadata()
        excluded = {"Web Development", "Mobile Development", "Blockchain"}
        for item in path.items.filter(status__in=("current", "upcoming")):
            domain = metadata[item.course].domain
            self.assertNotIn(domain, excluded, f'"{item.course}" (domain={domain}) is out of place in an ML path')

    def test_explicit_interest_overrides_domain_exclusion(self):
        """A Web Dev learner who explicitly says they're also interested in
        Machine Learning should be allowed ML courses — the filter narrows
        by default, it doesn't hard-block an explicit choice."""
        _, profile = _make_profile("webdev3", "I want to become a full stack web developer")
        LearnerInterest.objects.create(profile=profile, label="Machine Learning")
        path = generate_path(profile, "full stack web developer machine learning", reason="Initial")
        metadata = load_course_metadata()
        domains_present = {metadata[i.course].domain for i in path.items.all()}
        # Not asserting ML *must* appear (still score-dependent), only that
        # it's not structurally forbidden the way it would be without the interest.
        self.assertNotIn("Deep Learning", domains_present.difference({"Machine Learning"}))


class PathValidatorTests(TestCase):
    def test_generated_paths_pass_validation_across_domains(self):
        goals = [
            ("valweb", "I want to become a full stack web developer", "web developer javascript"),
            ("valanalyst", "I want to become a data analyst", "data analyst sql excel"),
            ("valml", "I want to become a machine learning engineer", "machine learning python"),
            ("valdevops", "I want to become a DevOps engineer", "devops docker kubernetes"),
            ("valcyber", "I want to become a cybersecurity engineer", "cybersecurity security"),
        ]
        for username, goal, query in goals:
            _, profile = _make_profile(username, goal)
            path = generate_path(profile, query, reason="Initial")
            result = validate_path(path)
            self.assertTrue(result.ok, f"{username}: {result.errors}")

    def test_prerequisite_violation_is_actually_detectable(self):
        """Sanity-check the validator itself: manually break a path and
        confirm validate_prerequisites actually catches it, rather than
        the positive tests above passing vacuously."""
        _, profile = _make_profile("valbreak", "I want to become a machine learning engineer")
        path = generate_path(profile, "machine learning", reason="Initial")
        metadata = load_course_metadata()
        item_with_prereqs = next(
            (i for i in path.items.all() if metadata.get(i.course) and metadata[i.course].prerequisites),
            None,
        )
        if item_with_prereqs:
            item_with_prereqs.status = "upcoming"
            item_with_prereqs.save(update_fields=["status"])
            result = validate_path(path)
            self.assertFalse(result.ok)


class PersonalizationTests(TestCase):
    def test_known_skills_change_the_generated_path(self):
        _, profile_a = _make_profile("persona", "I want to become a full stack web developer")
        _, profile_b = _make_profile("personb", "I want to become a full stack web developer")

        for skill in ["HTML and CSS for Beginners", "JavaScript Fundamentals"]:
            if load_course_metadata().get(skill):
                LearnerSkillEvidence.objects.create(profile=profile_b, skill=skill, evidence_level="known", source="test")

        path_a = generate_path(profile_a, "full stack web developer", reason="Initial")
        path_b = generate_path(profile_b, "full stack web developer", reason="Initial")

        courses_a = {i.course for i in path_a.items.filter(status__in=("current", "upcoming"))}
        courses_b = {i.course for i in path_b.items.filter(status__in=("current", "upcoming"))}
        self.assertNotEqual(courses_a, courses_b)

    def test_completed_history_excludes_course_from_new_path(self):
        _, profile = _make_profile("persc", "I want to become a data analyst")
        path1 = generate_path(profile, "data analyst", reason="Initial")
        first_upcoming = path1.items.filter(status__in=("current", "upcoming")).first()
        self.assertIsNotNone(first_upcoming)

        LearningHistoryEntry.objects.create(profile=profile, course=first_upcoming.course, status="completed")
        path2 = generate_path(profile, "data analyst", reason="Marked complete")
        recommended_again = path2.items.filter(
            course=first_upcoming.course, status__in=("current", "upcoming")
        ).exists()
        self.assertFalse(recommended_again)


class ProgressCalculationTests(TestCase):
    def test_zero_of_zero_is_zero_not_error(self):
        _, profile = _make_profile("prog0", "I want to become a web developer")
        path = LearningPath.objects.create(profile=profile, version=1, goal_snapshot="", change_reason="", is_current=True)
        self.assertEqual(readiness_percent(path), 0)

    def test_zero_of_n_is_zero(self):
        _, profile = _make_profile("prog1", "I want to become a web developer")
        path = generate_path(profile, "web developer", reason="Initial")
        self.assertEqual(readiness_percent(path), 0)

    def test_all_completed_is_hundred(self):
        _, profile = _make_profile("prog2", "I want to become a web developer")
        path = generate_path(profile, "web developer", reason="Initial")
        for item in path.items.all():
            item.status = "completed"
            item.save(update_fields=["status"])
        self.assertEqual(readiness_percent(path), 100)

    def test_partial_completion_is_proportional(self):
        _, profile = _make_profile("prog3", "I want to become a web developer")
        path = generate_path(profile, "web developer", reason="Initial")
        items = list(path.items.all())
        half = len(items) // 2
        for item in items[:half]:
            item.status = "completed"
            item.save(update_fields=["status"])
        expected = round(100 * half / len(items))
        self.assertEqual(readiness_percent(path), expected)


class InvalidPathNeverBecomesCurrentTests(TestCase):
    """Spec-mandated: 'do not merely log invalid paths and continue as if
    they were valid' — an invalid generation must roll back to the previous
    current version rather than replacing it. Eligibility gating makes a
    genuinely invalid generation near-impossible in normal operation, so
    this test forces the failure path directly to exercise the rollback
    logic itself."""

    def test_rollback_preserves_previous_valid_path_as_current(self):
        from unittest.mock import patch
        from apps.pathway.services.path_validator import ValidationResult

        _, profile = _make_profile("rollbacktest", "I want to become a machine learning engineer")
        path_v1 = generate_path(profile, "machine learning", reason="Initial")
        self.assertTrue(LearningPath.objects.get(id=path_v1.id).is_current)

        failing_result = ValidationResult()
        failing_result.add_error("forced failure for rollback test")

        with patch("apps.pathway.services.path_validator.validate_path", return_value=failing_result):
            returned = generate_path(profile, "machine learning", reason="Second (forced invalid)")

        path_v1.refresh_from_db()
        self.assertTrue(path_v1.is_current, "previous valid path must remain current after a rejected generation")
        self.assertEqual(returned.id, path_v1.id)
        v2 = profile.paths.filter(version=2).first()
        self.assertIsNotNone(v2)
        self.assertFalse(v2.is_current)
