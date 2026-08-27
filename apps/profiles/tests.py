from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.pathway.services.path_engine import generate_path
from apps.profiles.models import LearnerProfile
from apps.profiles.services.extraction import extract_from_text


class ExtractionTests(TestCase):
    def test_extracts_target_role_from_become_phrasing(self):
        result = extract_from_text("I want to become an AI/ML engineer.")
        self.assertIn("Ai/ml Engineer".lower(), result.target_role.lower())

    def test_known_cue_marks_exact_course_mention_as_known(self):
        result = extract_from_text("I already know Python for Absolute Beginners and want more.")
        self.assertIn("Python for Absolute Beginners", result.known_skills)

    def test_interest_phrase_without_exact_keyword_still_matches_domain(self):
        # No hardcoded keyword for this phrasing — must come from the
        # Word2Vec similarity match, not a lookup table.
        result = extract_from_text("I love container orchestration and deployment automation.")
        self.assertEqual(result.known_skills, [])
        self.assertIn("DevOps", result.inferred_interests)

    def test_direct_domain_mention_is_inferred_interest(self):
        result = extract_from_text("I'm interested in machine learning.")
        self.assertEqual(result.known_skills, [])
        self.assertIn("Machine Learning", result.inferred_interests)

    def test_negated_known_claim_is_not_marked_known(self):
        result = extract_from_text("I don't know React and I'm not interested in blockchain.")
        self.assertEqual(result.known_skills, [])
        self.assertNotIn("Blockchain", result.inferred_interests)

    def test_empty_text_returns_empty_result(self):
        result = extract_from_text("")
        self.assertEqual(result.target_role, "")
        self.assertEqual(result.known_skills, [])
        self.assertEqual(result.inferred_interests, [])


class OnboardingFlowTests(TestCase):
    def test_registered_user_without_profile_is_redirected_to_onboarding(self):
        User.objects.create_user(username="newlearner", password="SuperSecret123!")
        self.client.login(username="newlearner", password="SuperSecret123!")
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(response, reverse("profiles:onboarding"))

    def test_onboarding_creates_profile_and_generates_first_path(self):
        User.objects.create_user(username="newlearner2", password="SuperSecret123!")
        self.client.login(username="newlearner2", password="SuperSecret123!")
        response = self.client.post(
            reverse("profiles:onboarding"),
            {
                "destination_role": "AI/ML Engineer",
                "known_skills": "Python for Absolute Beginners",
                "interests": "Machine Learning",
                "experience_level": "intermediate",
                "extra_context": "",
            },
        )
        self.assertRedirects(response, reverse("pathway:path"))
        profile = LearnerProfile.objects.get(user__username="newlearner2")
        self.assertTrue(profile.paths.filter(is_current=True).exists())

    def test_user_with_profile_redirected_away_from_onboarding(self):
        user = User.objects.create_user(username="existing", password="SuperSecret123!")
        LearnerProfile.objects.create(user=user, goal_text="test goal")
        self.client.login(username="existing", password="SuperSecret123!")
        response = self.client.get(reverse("profiles:onboarding"))
        self.assertRedirects(response, reverse("pathway:path"))


class ProfileSecurityTests(TestCase):
    def test_profile_edit_only_affects_own_profile(self):
        user_a = User.objects.create_user(username="usera2", password="SuperSecret123!")
        profile_a = LearnerProfile.objects.create(user=user_a, goal_text="original goal")
        user_b = User.objects.create_user(username="userb2", password="SuperSecret123!")
        LearnerProfile.objects.create(user=user_b, goal_text="other goal")

        self.client.login(username="userb2", password="SuperSecret123!")
        self.client.post(
            reverse("profiles:profile"),
            {"goal_text": "changed by b", "target_role": "", "experience_level": "beginner"},
        )
        profile_a.refresh_from_db()
        self.assertEqual(profile_a.goal_text, "original goal")
