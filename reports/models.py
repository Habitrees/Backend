from django.conf import settings
from django.db import models


class SmartReport(models.Model):
    class Delivery(models.TextChoices):
        PENDING = "pending"
        DELIVERED = "delivered"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    period = models.CharField(max_length=7)
    period_start = models.DateField()
    narrative = models.TextField()
    delivery_status = models.CharField(
        max_length=9, choices=Delivery.choices, default=Delivery.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "period", "period_start"], name="unique_smart_report_period",
        )]
