from django.conf import settings
from django.db import models


class LearnerProfile(models.Model):
    EXPERIENCE_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learner_profile"
    )
    goal_text = models.TextField(help_text="What the learner said they're trying to achieve.")
    target_role = models.CharField(max_length=200, blank=True)
    experience_level = models.CharField(
        max_length=20, choices=EXPERIENCE_CHOICES, default="beginner"
    )
    internship_mode = models.BooleanField(
        default=False,
        help_text="When on, path generation gives a slight tiebreak boost to courses tied to a curated portfolio project.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile({self.user.username})"


class LearnerInterest(models.Model):
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="interests")
    label = models.CharField(max_length=200)

    class Meta:
        unique_together = ("profile", "label")

    def __str__(self):
        return self.label


class LearnerSkillEvidence(models.Model):

    EVIDENCE_CHOICES = [
        ("known", "Known — learner explicitly stated this"),
        ("inferred", "Inferred — extracted from free text, not explicitly confirmed"),
        ("unknown", "Unknown — no evidence either way"),
    ]

    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="skills")
    skill = models.CharField(max_length=200, help_text="Course/topic name this evidence is about.")
    evidence_level = models.CharField(max_length=20, choices=EVIDENCE_CHOICES, default="unknown")
    source = models.CharField(
        max_length=50,
        default="onboarding_text",
        help_text="Where this evidence came from, e.g. onboarding_text, learning_history.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("profile", "skill")

    def __str__(self):
        return f"{self.skill} ({self.evidence_level})"


class LearningHistoryEntry(models.Model):
    STATUS_CHOICES = [
        ("completed", "Completed"),
        ("in_progress", "In progress"),
        ("skipped", "Skipped"),
        ("saved", "Saved"),
    ]

    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="history")
    course = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("profile", "course")
        verbose_name_plural = "learning history entries"

    def __str__(self):
        return f"{self.course}: {self.status}"
