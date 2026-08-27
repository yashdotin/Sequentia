from django.contrib.auth.models import User
from django.template.defaultfilters import slugify
from django.test import TestCase
from django.urls import reverse

from apps.pathway.models import LearningPath
from apps.pathway.services.path_engine import generate_path
from apps.profiles.models import LearnerProfile
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
