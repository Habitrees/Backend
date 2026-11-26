from datetime import datetime, time, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from rest_framework.test import APITestCase

from challenges.models import Challenge
from .delivery import deliver_reminders
from .models import Notification, Reminder, ReminderDelivery


class ReminderDeliveryTests(APITestCase):
    def test_local_date_retry_failure_and_user_isolation(self):
        now = datetime(2026, 10, 1, 22, 0, tzinfo=utc.utc)
        user, other = [
            get_user_model().objects.create(
                phone=f"+1555000000{n}", username=f"reminder{n}", full_name="Member",
                timezone="Asia/Tehran", terms_accepted_at=now,
            )
            for n in (1, 2)
        ]
        challenge = Challenge.objects.create(
            owner=user, title="Read", kind="binary", timezone=user.timezone,
            start_date=now.date(), duration_days=3,
        )
        Reminder.objects.create(challenge=challenge, local_time=time(1))
        with patch.object(Notification.objects, "create", side_effect=DatabaseError):
            self.assertEqual(deliver_reminders(now), {"delivered": 0, "failed": 1})
        self.assertEqual(ReminderDelivery.objects.get().error, "notification_write_failed")
        self.assertIsNone(ReminderDelivery.objects.get().delivered_at)
        self.assertEqual(deliver_reminders(now), {"delivered": 1, "failed": 0})
        self.assertEqual(deliver_reminders(now), {"delivered": 0, "failed": 0})
        self.assertEqual(ReminderDelivery.objects.get().local_date.day, 2)
        item = Notification.objects.get()
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get("/api/notifications/").data["count"], 0)
        self.assertEqual(self.client.post(f"/api/notifications/{item.pk}/read/").status_code, 404)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.post("/api/notifications/read-all/").data, {"updated": 1})
        self.assertIsNotNone(self.client.post(f"/api/notifications/{item.pk}/read/").data["read_at"])
