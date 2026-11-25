from django.test import TestCase

# Create your tests here.

from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APITestCase

from challenges.models import Challenge

from .models import NotificationPreference


class NotificationAPITests(APITestCase):

    def create_user(self, phone, username):

        return get_user_model().objects.create_user(
            phone=phone,
            username=username,
            full_name="Test User",
            password="Strong-Test-Password-2026!",
            timezone="UTC",
            terms_version=settings.TERMS_VERSION,
            terms_accepted_at=timezone.now(),
            phone_verified_at=timezone.now(),
        )

    def setUp(self):

        self.user = self.create_user(
            "+989121234580",
            "reminder_user",
        )

        self.other_user = self.create_user(
            "+989121234581",
            "other_reminder_user",
        )

        self.client.force_authenticate(
            user=self.user
        )

        self.challenge = Challenge.objects.create(
            owner=self.user,
            title="Exercise",
            kind="time",
            polarity="positive",
            target_value=20,
            unit="minutes",
            frequency="daily",
            mode="strict",
            timezone="UTC",
            start_date=date(2026, 11, 25),
            duration_days=40,
        )

        self.reminder_url = "/api/reminders/"

        self.preference_url = (
            "/api/notification-preferences/"
        )

        self.payload = {
            "challenge": self.challenge.pk,
            "local_time": "09:00:00",
            "message": "Time to exercise",
            "enabled": True,
        }

    def test_create_reminder(self):

        response = self.client.post(
            self.reminder_url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        self.assertEqual(
            response.data["timezone"], "UTC"
        )

    def test_duplicate_reminder_rejected(self):

        response = self.client.post(
            self.reminder_url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        response = self.client.post(
            self.reminder_url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 400
        )

    def test_disable_reminder(self):

        response = self.client.post(
            self.reminder_url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        reminder_id = response.data["id"]

        response = self.client.patch(
            f"{self.reminder_url}{reminder_id}/",
            {"enabled": False},
            format="json",
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertFalse(
            response.data["enabled"]
        )

    def test_other_user_cannot_create_reminder(self):

        self.client.force_authenticate(
            user=self.other_user
        )

        response = self.client.post(
            self.reminder_url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 400
        )

    def test_other_user_cannot_access_reminder(self):

        response = self.client.post(
            self.reminder_url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code, 201
        )

        reminder_id = response.data["id"]

        self.client.force_authenticate(
            user=self.other_user
        )

        response = self.client.get(
            f"{self.reminder_url}{reminder_id}/"
        )

        self.assertEqual(
            response.status_code, 404
        )

    def test_default_preferences(self):

        response = self.client.get(
            self.preference_url
        )

        self.assertEqual(
            response.status_code, 200
        )

        self.assertTrue(
            response.data["in_app_enabled"]
        )

        self.assertFalse(
            response.data["telegram_reports_enabled"]
        )

        self.assertFalse(
            NotificationPreference.objects.filter(
                user=self.user
            ).exists()
        )

    def test_update_preferences(self):

        response = self.client.patch(
            self.preference_url,
            {
                "push_enabled": True,
                "telegram_reports_enabled": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, 200
        )

        preference = (
            NotificationPreference.objects.get(
                user=self.user
            )
        )

        self.assertTrue(
            preference.push_enabled
        )

        self.assertTrue(
            preference.telegram_reports_enabled
        )

        self.assertFalse(
            preference.email_reports_enabled
        )

    def test_authentication_required(self):

        self.client.force_authenticate(
            user=None
        )

        response = self.client.get(
            self.reminder_url
        )

        self.assertEqual(
            response.status_code, 401
        )

        response = self.client.get(
            self.preference_url
        )

        self.assertEqual(
            response.status_code, 401
        )
