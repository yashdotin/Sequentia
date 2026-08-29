from django.conf import settings
from django.db import models


class LearnerProjectState(models.Model):
    """
    Tracks a learner's progress on a curated project (see data/project_seed.csv,
    hand-curated the same way course_metadata_seed.csv is — not ML-generated).
    """

    STATUS_CHOICES = [
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("published", "Published"),
    ]

    profile = models.ForeignKey(
        "profiles.LearnerProfile", on_delete=models.CASCADE, related_name="project_states"
    )
    project_slug = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    github_url = models.URLField(blank=True)
    demo_url = models.URLField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("profile", "project_slug")

    def __str__(self):
        return f"{self.project_slug} ({self.status}) — {self.profile.user.username}"


class LearnerSavedResource(models.Model):
    profile = models.ForeignKey(
        "profiles.LearnerProfile", on_delete=models.CASCADE, related_name="saved_resources"
    )
    course = models.CharField(max_length=200)
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("profile", "course")
        ordering = ["-saved_at"]

    def __str__(self):
        return f"{self.course} saved by {self.profile.user.username}"
