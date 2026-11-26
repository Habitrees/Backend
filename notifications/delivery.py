from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import DatabaseError, transaction
from django.utils import timezone

from challenges.schedule import get_period
from .models import Notification, Reminder, ReminderDelivery


def deliver_reminders(now=None):
    now = (now or timezone.now()).replace(second=0, microsecond=0)
    result = {"delivered": 0, "failed": 0}
    reminders = Reminder.objects.filter(
        enabled=True, challenge__archived=False, challenge__owner__is_active=True,
        challenge__start_date__lte=now.date() + timedelta(days=1),
    ).select_related("challenge__owner__notification_preference")
    for reminder in reminders.iterator():
        challenge = reminder.challenge
        user = challenge.owner
        try:
            local = now.astimezone(ZoneInfo(challenge.timezone))
        except (ValueError, ZoneInfoNotFoundError):
            continue
        if not get_period(challenge, local.date()):
            continue
        if local.time() < reminder.local_time:
            continue
        if not getattr(getattr(user, "notification_preference", None), "in_app_enabled", True):
            continue

        delivery, _ = ReminderDelivery.objects.get_or_create(
            reminder=reminder, local_date=local.date(),
        )
        try:
            with transaction.atomic():
                delivery = ReminderDelivery.objects.select_for_update().get(pk=delivery.pk)
                if delivery.delivered_at:
                    continue
                Notification.objects.create(
                    user=user, title=challenge.title, message=reminder.message,
                )
                delivery.delivered_at = timezone.now()
                delivery.error = ""
                delivery.save(update_fields=["delivered_at", "error"])
            result["delivered"] += 1
        except DatabaseError:
            ReminderDelivery.objects.filter(
                pk=delivery.pk, delivered_at__isnull=True,
            ).update(error="notification_write_failed")
            result["failed"] += 1
    return result
