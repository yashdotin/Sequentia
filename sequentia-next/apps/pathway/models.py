from django.db import models

from apps.profiles.models import LearnerProfile


class LearningPath(models.Model):
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="paths")
    version = models.PositiveIntegerField()
    goal_snapshot = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    change_reason = models.CharField(max_length=300, blank=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ["-version"]
        unique_together = ("profile", "version")

    def __str__(self):
        return f"Path v{self.version} for {self.profile.user.username}"


class LearningPathItem(models.Model):
    STATUS_CHOICES = [
        ("completed", "Completed"),
        ("current", "Current"),
        ("upcoming", "Upcoming"),
        ("blocked", "Blocked"),
    ]

    path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="items")
    course = models.CharField(max_length=200)
    stage = models.CharField(max_length=100)
    position = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    match_score = models.FloatField()
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"{self.course} ({self.status})"


class PathChangeEvent(models.Model):
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="path_changes")
    previous_version = models.PositiveIntegerField(null=True, blank=True)
    new_version = models.PositiveIntegerField()
    reason = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"v{self.previous_version} -> v{self.new_version}: {self.reason}"
