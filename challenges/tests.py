from django.test import TestCase

# Create your tests here.

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from .models import Challenge
from .services import calculate_success

class HabitLogLogicTests(SimpleTestCase):

    def test_positive_time_success(self):

        challenge = Challenge(
            kind="time",
            polarity="positive",
            target_value=20,
        )

        self.assertTrue(
            calculate_success(
                challenge,
                value=25,
            )
        )

    def test_positive_time_failure(self):

        challenge = Challenge(
            kind="time",
            polarity="positive",
            target_value=20,
        )

        self.assertFalse(
            calculate_success(
                challenge,
                value=10,
            )
        )

    def test_negative_count_success(self):

        challenge = Challenge(
            kind="count",
            polarity="negative",
            target_value=2,
        )

        self.assertTrue(
            calculate_success(
                challenge,
                value=1,
            )
        )

    def test_negative_binary_success(self):

        challenge = Challenge(
            kind="binary",
            polarity="negative",
        )

        self.assertTrue(
            calculate_success(
                challenge,
                performed=False,
            )
        )

    def test_negative_binary_failure(self):

        challenge = Challenge(
            kind="binary",
            polarity="negative",
        )

        self.assertFalse(
            calculate_success(
                challenge,
                performed=True,
            )
        )

    def test_binary_rejects_numeric_value(self):

        challenge = Challenge(
            kind="binary",
            polarity="positive",
        )

        with self.assertRaises(ValidationError):

            calculate_success(
                challenge,
                value=10,
            )


from datetime import date

from .streak import calculate_streak

class StreakLogicTests(SimpleTestCase):

    def setUp(self):

        self.challenge = Challenge(
            title="Test challenge",
            start_date=date(2026, 11, 1),
            duration_days=40,
            frequency="daily",
            mode="strict",
            timezone="UTC",
        )

    def test_strict_successive_days(self):

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
                date(2026, 11, 3),
            ],
            date(2026, 11, 3),
        )

        self.assertEqual(result["current_streak"], 3)
        self.assertEqual(result["best_streak"], 3)

    def test_strict_streak_reset(self):

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
            ],
            date(2026, 11, 4),
        )

        self.assertEqual(result["current_streak"], 0)
        self.assertEqual(result["best_streak"], 2)

    def test_today_is_not_failed_before_end(self):

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
            ],
            date(2026, 11, 3),
        )

        self.assertEqual(result["current_streak"], 2)

    def test_flexible_one_missed_day(self):

        self.challenge.mode = "flexible"

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
            ],
            date(2026, 11, 4),
        )

        self.assertEqual(result["current_streak"], 2)
        self.assertTrue(result["recovery_pending"])
        self.assertFalse(result["can_recover"])

        self.assertEqual(
            result["recoverable_date"],
            date(2026, 11, 3),
        )

    def test_flexible_two_missed_days(self):

        self.challenge.mode = "flexible"

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
            ],
            date(2026, 11, 5),
        )

        self.assertEqual(result["current_streak"], 0)
        self.assertEqual(result["best_streak"], 2)

        self.assertEqual(
            result["consecutive_failures"],
            2,
        )

    def test_flexible_recovered_day(self):

        self.challenge.mode = "flexible"

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
                date(2026, 11, 3),
                date(2026, 11, 4),
            ],
            date(2026, 11, 4),
        )

        self.assertEqual(result["current_streak"], 4)
        self.assertFalse(result["recovery_pending"])

    def test_flexible_can_recover_after_today_success(self):

        self.challenge.mode = "flexible"

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
                date(2026, 11, 4),
            ],
            date(2026, 11, 4),
        )

        self.assertTrue(result["can_recover"])

    def test_weekly_streak(self):

        self.challenge.frequency = "weekly"
        self.challenge.start_date = date(2026, 11, 2)

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 2),
                date(2026, 11, 9),
            ],
            date(2026, 11, 16),
        )

        self.assertEqual(result["current_streak"], 2)
        self.assertEqual(result["best_streak"], 2)

    def test_monthly_streak(self):

        self.challenge.frequency = "monthly"
        self.challenge.duration_days = 120

        result = calculate_streak(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 12, 1),
            ],
            date(2027, 1, 1),
        )

        self.assertEqual(result["current_streak"], 2)
        self.assertEqual(result["best_streak"], 2)



from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APITestCase

class StreakRecoveryAPITests(APITestCase):

    def setUp(self):

        self.user = get_user_model().objects.create_user(
            phone="+989121234567",
            username="streak_test",
            full_name="Streak Test",
            password="Strong-Test-Password-2026!",
            timezone="UTC",
            terms_version=settings.TERMS_VERSION,
            terms_accepted_at=timezone.now(),
            phone_verified_at=timezone.now(),
        )

        self.client.force_authenticate(
            user=self.user
        )

        self.today = timezone.localdate(
            timezone=ZoneInfo("UTC")
        )

        self.yesterday = self.today - timedelta(days=1)

        self.challenge = Challenge.objects.create(
            owner=self.user,
            title="Daily exercise",
            kind="time",
            polarity="positive",
            target_value=20,
            unit="minutes",
            frequency="daily",
            mode="flexible",
            timezone="UTC",
            start_date=self.yesterday,
            duration_days=40,
        )

        self.base_url = (
            f"/api/challenges/{self.challenge.pk}/"
        )

    def test_successful_recovery(self):

        response = self.client.put(
            f"{self.base_url}logs/{self.today}/",
            {"value": 25},
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            f"{self.base_url}recover/{self.yesterday}/",
            {"value": 25},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        self.assertIsNotNone(
            response.data["recovered_at"]
        )

        response = self.client.get(
            f"{self.base_url}streak/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["current_streak"], 2)
        self.assertEqual(response.data["best_streak"], 2)

        # Today's success cannot be undone after recovery.
        response = self.client.put(
            f"{self.base_url}logs/{self.today}/",
            {"value": 5},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_recovery_without_today_success(self):

        response = self.client.post(
            f"{self.base_url}recover/{self.yesterday}/",
            {"value": 25},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

from .progress import (
    calculate_progress,
    get_plant_stage,
    build_plant_data,
)

class PlantProgressTests(SimpleTestCase):

    def setUp(self):

        self.challenge = Challenge(
            title="Exercise",
            start_date=date(2026, 11, 1),
            duration_days=4,
            frequency="daily",
            mode="strict",
            timezone="UTC",
        )

    def test_progress_without_logs(self):

        result = calculate_progress(
            self.challenge,
            [],
            date(2026, 11, 1),
        )

        self.assertEqual(
            result["progress_percent"], 0
        )

    def test_half_progress(self):

        result = calculate_progress(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
            ],
            date(2026, 11, 2),
        )

        self.assertEqual(
            result["progress_percent"], 50
        )

    def test_plant_stages(self):

        cases = [
            (0, False, 1),
            (25, False, 2),
            (50, False, 3),
            (75, False, 4),
            (100, False, 4),
            (100, True, 5),
        ]

        for progress, completed, expected in cases:

            with self.subTest(progress=progress):

                stage, _ = get_plant_stage(
                    progress,
                    completed,
                )

                self.assertEqual(stage, expected)

    def test_completed_challenge(self):

        result = build_plant_data(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
                date(2026, 11, 3),
                date(2026, 11, 4),
            ],
            date(2026, 11, 5),
        )

        self.assertTrue(result["completed"])
        self.assertEqual(result["stage"], 5)
        self.assertEqual(
            result["progress_percent"], 100
        )

    def test_incomplete_challenge(self):

        result = build_plant_data(
            self.challenge,
            [
                date(2026, 11, 1),
                date(2026, 11, 2),
            ],
            date(2026, 11, 5),
        )

        self.assertFalse(result["completed"])

        self.assertEqual(
            result["status"],
            "ended_unsuccessful",
        )

    def test_weekly_progress(self):

        self.challenge.frequency = "weekly"

        self.challenge.start_date = date(
            2026, 11, 2
        )

        self.challenge.duration_days = 28

        result = calculate_progress(
            self.challenge,
            [
                date(2026, 11, 2),
                date(2026, 11, 9),
            ],
            date(2026, 11, 16),
        )

        self.assertEqual(
            result["total_periods"], 4
        )

        self.assertEqual(
            result["progress_percent"], 50
        )
from unittest.mock import patch
from .models import HabitLog

class GardenAPITests(APITestCase):

    def setUp(self):

        User = get_user_model()

        self.user = User.objects.create_user(
            phone="+989121234568",
            username="garden_user",
            full_name="Garden User",
            password="Test-Password-2026!",
            timezone="UTC",
            terms_version=settings.TERMS_VERSION,
            terms_accepted_at=timezone.now(),
            phone_verified_at=timezone.now(),
        )

        self.other_user = User.objects.create_user(
            phone="+989121234569",
            username="other_garden_user",
            full_name="Other User",
            password="Test-Password-2026!",
            timezone="UTC",
            terms_version=settings.TERMS_VERSION,
            terms_accepted_at=timezone.now(),
            phone_verified_at=timezone.now(),
        )

        self.client.force_authenticate(
            user=self.user
        )

        self.today = date(2026, 11, 25)

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
            start_date=self.today - timedelta(days=1),
            duration_days=1,
        )

        HabitLog.objects.create(
            challenge=self.challenge,
            period_start=self.challenge.start_date,
            value=25,
            success=True,
        )

    def test_completed_plant_in_garden(self):

        with patch(
            "challenges.services.get_local_today",
            return_value=self.today,
        ):

            response = self.client.get(
                "/api/garden/"
            )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.data["total_completed"], 1
        )

        self.assertEqual(
            response.data["completed"][0]["stage"],
            5,
        )

    def test_other_user_cannot_access_plant(self):

        self.client.force_authenticate(
            user=self.other_user
        )

        response = self.client.get(
            f"/api/challenges/{self.challenge.pk}/plant/"
        )

        self.assertEqual(
            response.status_code, 404
        )

        response = self.client.get(
            "/api/garden/"
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.data["total_completed"], 0
        )
from django.conf import settings
from django.utils import timezone