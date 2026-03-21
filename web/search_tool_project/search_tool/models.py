from django.contrib.auth.models import User
from django.db import models


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    path = models.TextField()
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ("user", "path")
        ordering = ["name"]


class IndexingStatus(models.Model):
    """Singleton (pk=1) — persists indexing state across server restarts."""
    folder = models.TextField(default="")
    running = models.BooleanField(default=False)
    done = models.IntegerField(default=0)
    total = models.IntegerField(default=0)
    current = models.CharField(max_length=500, default="")
    newly_indexed = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)
    error = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Statut indexation"
