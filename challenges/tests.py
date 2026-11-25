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