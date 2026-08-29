from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from apps.coach.services.coach import answer_question
from apps.coach.services.gemini_client import phrase_grounded_answer
from apps.pathway.services.path_engine import generate_path
from apps.profiles.models import LearnerProfile


def _make_profile(username, goal_text):
    user = User.objects.create_user(username=username, password="testpass123")
    profile = LearnerProfile.objects.create(user=user, goal_text=goal_text, experience_level="beginner")
    return profile


class GeminiClientFallbackTests(TestCase):
    @override_settings(GEMINI_API_KEY="")
    def test_returns_none_when_no_api_key_configured(self):
        result = phrase_grounded_answer("what's next?", "Some grounded facts.")
        self.assertIsNone(result)


class CoachAnswerQuestionTests(TestCase):
    @override_settings(GEMINI_API_KEY="")
    def test_falls_back_to_grounded_rule_based_answer_without_gemini(self):
        profile = _make_profile("coachfallback", "I want to become a backend developer")
        generate_path(profile, "backend developer", reason="Initial")
        answer = answer_question(profile, "what's next?")
        self.assertTrue(answer)
        self.assertNotIn("Ask me something", answer)

    @override_settings(GEMINI_API_KEY="")
    def test_never_returns_empty_for_an_empty_question(self):
        profile = _make_profile("coachempty", "I want to become a backend developer")
        generate_path(profile, "backend developer", reason="Initial")
        answer = answer_question(profile, "")
        self.assertTrue(answer)
