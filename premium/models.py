from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models


class Subscription(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="premium_subscription",
    )

    activated_at = models.DateTimeField(
        auto_now_add=True
    )

    source = models.CharField(
        max_length=30,
        default="habit_completion",
    )

    evidence = models.JSONField(
        default=dict
    )

    def __str__(self):
        return f"Premium - {self.user_id}"