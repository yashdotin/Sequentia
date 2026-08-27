from django.db import models

from apps.profiles.models import LearnerProfile


class Recommendation(models.Model):
    profile = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="recommendations"
    )
    course = models.CharField(max_length=200)
    score = models.FloatField()
    explanation = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = ("profile", "course")

    def __str__(self):
        return f"{self.course} ({self.score:.3f}) for {self.profile.user.username}"


class RecommendationFeedback(models.Model):
    FEEDBACK_CHOICES = [("helpful", "Helpful"), ("not_helpful", "Not helpful")]
    REASON_CHOICES = [
        ("too_easy", "Too easy"),
        ("too_difficult", "Too difficult"),
        ("already_know", "Already know this"),
        ("not_relevant", "Not relevant"),
        ("wrong_direction", "Wrong direction"),
        ("prefer_project", "Prefer project"),
        ("prefer_course", "Prefer course"),
        ("prefer_resource", "Prefer article/resource"),
        ("other", "Other"),
    ]

    profile = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="recommendation_feedback"
    )
    recommendation = models.ForeignKey(
        Recommendation, on_delete=models.CASCADE, related_name="feedback"
    )
    feedback = models.CharField(max_length=20, choices=FEEDBACK_CHOICES)
    reason = models.CharField(max_length=30, choices=REASON_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.feedback} on {self.recommendation.course}"
