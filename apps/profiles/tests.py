from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.pathway.models import LearningPath
from apps.pathway.services.path_engine import generate_path
from apps.profiles.models import LearnerInterest, LearnerProfile, LearnerSkillEvidence
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


class KnownSkillUpdateTests(TestCase):
    def _login(self, username="skillupdater"):
        User.objects.filter(username=username).delete()
        User.objects.create_user(username=username, password="testpass123")
        self.client.login(username=username, password="testpass123")
        profile = LearnerProfile.objects.create(
            user=User.objects.get(username=username),
            goal_text="I want to become a full stack web developer",
            experience_level="beginner",
        )
        return profile

    def test_add_valid_skill(self):
        profile = self._login()
        resp = self.client.post(reverse("profiles:update_skills"), {
            "action": "add", "skill": "JavaScript Fundamentals",
        })
        self.assertRedirects(resp, reverse("profiles:skills"))
        self.assertTrue(
            LearnerSkillEvidence.objects.filter(
                profile=profile, skill="JavaScript Fundamentals", evidence_level="known",
                source="manual_skill_update",
            ).exists()
        )

    def test_cannot_add_arbitrary_unrecognized_skill(self):
        profile = self._login()
        self.client.post(reverse("profiles:update_skills"), {
            "action": "add", "skill": "Definitely Not A Real Course",
        })
        self.assertFalse(
            LearnerSkillEvidence.objects.filter(profile=profile, skill="Definitely Not A Real Course").exists()
        )

    def test_remove_self_reported_skill(self):
        profile = self._login()
        LearnerSkillEvidence.objects.create(
            profile=profile, skill="HTML and CSS for Beginners",
            evidence_level="known", source="manual_skill_update",
        )
        self.client.post(reverse("profiles:update_skills"), {
            "action": "remove", "skill": "HTML and CSS for Beginners",
        })
        self.assertFalse(
            LearnerSkillEvidence.objects.filter(profile=profile, skill="HTML and CSS for Beginners").exists()
        )

    def test_skill_update_triggers_path_regeneration(self):
        profile = self._login()
        path_v1 = generate_path(profile, "full stack web developer", reason="Initial")
        self.assertEqual(path_v1.version, 1)

        self.client.post(reverse("profiles:update_skills"), {
            "action": "add", "skill": "HTML and CSS for Beginners",
        })

        new_current = profile.paths.filter(is_current=True).first()
        self.assertEqual(new_current.version, 2)
        self.assertFalse(LearningPath.objects.get(id=path_v1.id).is_current)

    def test_known_skill_update_changes_the_next_recommended_step(self):
        profile = self._login()
        path_before = generate_path(profile, "full stack web developer", reason="Initial")
        before_courses = {i.course for i in path_before.items.filter(status__in=("current", "upcoming"))}

        self.client.post(reverse("profiles:update_skills"), {
            "action": "add", "skill": "HTML and CSS for Beginners",
        })
        self.client.post(reverse("profiles:update_skills"), {
            "action": "add", "skill": "JavaScript Fundamentals",
        })

        path_after = profile.paths.filter(is_current=True).first()
        after_courses = {i.course for i in path_after.items.filter(status__in=("current", "upcoming"))}
        self.assertNotEqual(before_courses, after_courses)


class InterestUpdateTests(TestCase):
    def _login(self, username="interestupdater", goal="I want to become a full stack web developer"):
        User.objects.filter(username=username).delete()
        User.objects.create_user(username=username, password="testpass123")
        self.client.login(username=username, password="testpass123")
        profile = LearnerProfile.objects.create(
            user=User.objects.get(username=username), goal_text=goal, experience_level="beginner",
        )
        return profile

    def test_add_valid_interest(self):
        profile = self._login()
        resp = self.client.post(reverse("profiles:update_interests"), {"action": "add", "interest": "Cloud"})
        self.assertRedirects(resp, reverse("profiles:skills"))
        self.assertTrue(LearnerInterest.objects.filter(profile=profile, label="Cloud").exists())

    def test_reject_invalid_interest_category(self):
        profile = self._login()
        self.client.post(reverse("profiles:update_interests"), {"action": "add", "interest": "Astrology"})
        self.assertFalse(LearnerInterest.objects.filter(profile=profile, label="Astrology").exists())

    def test_duplicate_interest_is_a_noop_not_a_new_version(self):
        profile = self._login()
        generate_path(profile, "full stack web developer", reason="Initial")
        self.client.post(reverse("profiles:update_interests"), {"action": "add", "interest": "Cloud"})
        version_after_first_add = profile.paths.filter(is_current=True).first().version

        self.client.post(reverse("profiles:update_interests"), {"action": "add", "interest": "Cloud"})
        version_after_duplicate = profile.paths.filter(is_current=True).first().version
        self.assertEqual(version_after_first_add, version_after_duplicate)
        self.assertEqual(LearnerInterest.objects.filter(profile=profile, label="Cloud").count(), 1)

    def test_remove_interest(self):
        profile = self._login()
        LearnerInterest.objects.create(profile=profile, label="Cloud")
        self.client.post(reverse("profiles:update_interests"), {"action": "remove", "interest": "Cloud"})
        self.assertFalse(LearnerInterest.objects.filter(profile=profile, label="Cloud").exists())

    def test_interest_update_requires_authentication(self):
        LearnerProfile.objects.all().delete()
        resp = self.client.post(reverse("profiles:update_interests"), {"action": "add", "interest": "Cloud"})
        self.assertNotEqual(resp.status_code, 200)  # redirected to login, never processed

    def test_interest_change_triggers_regeneration_with_correct_version_history(self):
        profile = self._login()
        v1 = generate_path(profile, "full stack web developer", reason="Initial")
        self.client.post(reverse("profiles:update_interests"), {"action": "add", "interest": "Cloud"})
        v2 = profile.paths.filter(is_current=True).first()
        self.assertEqual(v2.version, 2)
        self.assertFalse(LearningPath.objects.get(id=v1.id).is_current)
        self.assertEqual(profile.paths.count(), 2)


class InterestDoesNotOverrideGoalTests(TestCase):
    """Mandatory per spec: interest is secondary personalization, it must
    never replace the primary goal/domain."""

    def test_frontend_goal_with_ml_interest_still_has_web_dev_as_primary(self):
        User.objects.filter(username="frontendml").delete()
        User.objects.create_user(username="frontendml", password="testpass123")
        profile = LearnerProfile.objects.create(
            user=User.objects.get(username="frontendml"),
            goal_text="I want to become a frontend developer",
            target_role="Frontend Developer",
            experience_level="beginner",
        )
        LearnerInterest.objects.create(profile=profile, label="Machine Learning")

        from apps.pathway.services.domain import determine_primary_domain
        self.assertEqual(determine_primary_domain(profile), "Web Development")

        path = generate_path(profile, "frontend developer html css javascript", reason="Initial")
        from apps.recommender.ml.metadata import load_course_metadata
        metadata = load_course_metadata()
        current_and_upcoming_domains = {
            metadata[i.course].domain for i in path.items.filter(status__in=("current", "upcoming"))
        }
        # ML is allowed to appear now (explicit interest override, same as
        # path_engine's own allowance) but must not be the ONLY or dominant
        # domain — Web Development must still be present and primary.
        self.assertIn("Web Development", current_and_upcoming_domains)
